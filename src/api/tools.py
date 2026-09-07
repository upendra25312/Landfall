"""
Agent tool endpoints - three anonymous HTTP functions the Foundry Migration Estimator
calls as OpenAPI tools. Registered as a blueprint from function_app.py.

  POST /api/query_inventory       natural language -> read-only SELECT -> rows + SQL
  POST /api/vm_rightsize          servers -> Azure VM SKU + disk tier (documented heuristic)
  GET  /api/azure_retail_prices   cached proxy over prices.azure.com

query_inventory is the only one that touches client data. It runs SELECT-only against a
read-only DB user (schema.sql grants db_datareader to the workload identity) and caps rows.
See DEPLOY.md "Harden query_inventory" for putting Entra auth in front of it.

App settings used:
  FOUNDRY_PROJECT_ENDPOINT      (already set - shared with function_app.py)
  AZURE_OPENAI_CHAT_DEPLOYMENT  gpt-4o deployment name, for text-to-SQL
  AZURE_SQL_SERVER_FQDN         <server>.database.windows.net
  AZURE_SQL_DATABASE            database name
"""
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

bp = func.Blueprint()

_cred = DefaultAzureCredential()
_state: dict = {}

MAX_ROWS = 200

# --------------------------------------------------------------------------
# shared clients (lazy)
# --------------------------------------------------------------------------
def _chat():
    if "chat" not in _state:
        proj = AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=_cred
        )
        _state["chat"] = proj.get_openai_client()
    return _state["chat"]


def _sql_connect():
    """mssql-python connection with an Entra token from the workload identity."""
    import mssql_python

    server = os.environ["AZURE_SQL_SERVER_FQDN"]
    database = os.environ["AZURE_SQL_DATABASE"]
    return mssql_python.connect(
        f"Server={server};Database={database};Encrypt=yes;",
        token_provider=_cred,
    )


# ==========================================================================
# query_inventory
# ==========================================================================
SCHEMA_HINT = """Tables (Azure SQL, schema dbo). All columns nullable - client data has gaps.
app_id / server_id are soft links (not FK-enforced); rows may reference missing keys.
Every table also has source_file and ingested_at (ignore unless asked about provenance).

servers(server_id, hostname, env /* prod|nonprod|dev|dr */, os_name, os_version,
        os_eol_date, vcpu, ram_gb, provisioned_disk_gb, used_disk_gb,
        cpu_avg_pct, cpu_peak_pct, ram_avg_pct /* 30-day rollups */,
        disk_iops_avg, disk_iops_peak, net_in_gb_30d, net_out_gb_30d /* 30-day totals */,
        cluster, datacenter, powerstate, app_id /* -> applications.app_id */, notes)
applications(app_id, app_name, business_owner, criticality /* 1 high..4 */, users,
        tech_stack, db_engine, internet_facing /* bit */, compliance_scope,
        disposition, complexity /* S|M|L|XL */, wave)
dependencies(dep_id, src_id, dst_id, port, protocol, direction, confidence,
        bytes_30d_gb, flows_30d, last_seen /* observed over the 30-day window */)
storage(storage_id, server_id /* -> servers.server_id */, type /* block|file|object|db */,
        size_gb, iops, target_service)
performance(perf_id, server_id, sample_date, cpu_avg_pct, cpu_peak_pct, cpu_p95_pct,
        mem_avg_pct, mem_peak_pct, mem_p95_pct, disk_iops_avg, disk_iops_peak,
        disk_read_iops_avg, disk_write_iops_avg, disk_throughput_mbps_avg,
        net_in_gb, net_out_gb, net_in_peak_mbps, net_out_peak_mbps)
        /* one row per server per day; ~30-day window; only monitored servers */
"""

_SQL_SYSTEM = (
    "You translate a question into ONE T-SQL SELECT statement for Azure SQL and nothing "
    "else. Rules: a single SELECT (a leading WITH CTE is allowed); read-only, never "
    "INSERT/UPDATE/DELETE/DDL; no semicolons; use TOP when the user wants examples; "
    "prefer COUNT/SUM/AVG for 'how many' / 'total' questions; return only the SQL, no "
    "markdown fences, no explanation.\n\n" + SCHEMA_HINT
)

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|exec|execute|merge|grant|revoke|"
    r"truncate|into|backup|restore|sp_\w*|xp_\w*)\b",
    re.IGNORECASE,
)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _safe_select(sql: str) -> str:
    """Raise ValueError unless sql is a single read-only SELECT/WITH."""
    s = _strip_fences(sql).rstrip(";").strip()
    if not re.match(r"^\s*(select|with)\b", s, re.IGNORECASE):
        raise ValueError("not a SELECT")
    if ";" in s:
        raise ValueError("multiple statements")
    if _FORBIDDEN.search(s):
        raise ValueError("write/DDL keyword present")
    return s


def _sql_for(question: str) -> str:
    resp = _chat().chat.completions.create(
        model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        temperature=0,
        messages=[
            {"role": "system", "content": _SQL_SYSTEM},
            {"role": "user", "content": question},
        ],
    )
    return _safe_select(resp.choices[0].message.content or "")


@bp.route(route="query_inventory", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def query_inventory(req: func.HttpRequest) -> func.HttpResponse:
    try:
        question = (req.get_json().get("question") or "").strip()
    except ValueError:
        question = ""
    if not question:
        return _json({"error": "body must be {\"question\": \"...\"}"}, 400)

    try:
        sql = _sql_for(question)
    except ValueError as exc:
        logging.warning("unsafe SQL for %r: %s", question, exc)
        return _json({"error": f"could not build a safe query ({exc})", "sql": ""}, 400)
    except Exception:
        logging.exception("text-to-SQL failed")
        return _json({"error": "text-to-SQL failed"}, 502)

    try:
        conn = _sql_connect()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            fetched = cur.fetchmany(MAX_ROWS + 1)
        finally:
            conn.close()
    except Exception as exc:
        logging.exception("query failed")
        return _json({"error": f"query failed: {exc}", "sql": sql}, 502)

    truncated = len(fetched) > MAX_ROWS
    rows = [[_cell(v) for v in r] for r in fetched[:MAX_ROWS]]
    return _json(
        {
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    )


def _cell(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


# ==========================================================================
# vm_rightsize
# ==========================================================================
# vCPU -> RAM GiB per family (Azure v5). Keys are the sizes we will map to.
_SKU_TABLE = {
    "Dsv5": [(2, 8, "Standard_D2s_v5"), (4, 16, "Standard_D4s_v5"), (8, 32, "Standard_D8s_v5"),
             (16, 64, "Standard_D16s_v5"), (32, 128, "Standard_D32s_v5"), (64, 256, "Standard_D64s_v5")],
    "Esv5": [(2, 16, "Standard_E2s_v5"), (4, 32, "Standard_E4s_v5"), (8, 64, "Standard_E8s_v5"),
             (16, 128, "Standard_E16s_v5"), (32, 256, "Standard_E32s_v5"), (64, 512, "Standard_E64s_v5")],
    "Fsv2": [(2, 4, "Standard_F2s_v2"), (4, 8, "Standard_F4s_v2"), (8, 16, "Standard_F8s_v2"),
             (16, 32, "Standard_F16s_v2"), (32, 64, "Standard_F32s_v2"), (64, 128, "Standard_F64s_v2")],
}
_HEURISTIC = (
    "family by RAM/vCPU ratio (<=2 Fsv2, <=5 Dsv5, else Esv5); if cpu_peak_pct present, "
    "size vCPU so peak load leaves ~25% headroom; if absent, assume oversized, map one "
    "size down, confidence=low; disk tier by used_disk_gb (<=128 P10, <=512 P20, "
    "<=1024 P30, else P40)."
)


def _disk_tier(used_gb):
    g = used_gb or 0
    return "P10" if g <= 128 else "P20" if g <= 512 else "P30" if g <= 1024 else "P40"


def _rightsize_one(s: dict) -> dict:
    sid = s.get("server_id")
    vcpu = float(s.get("vcpu") or 0) or 2.0
    ram = float(s.get("ram_gb") or 0) or vcpu * 4
    peak = s.get("cpu_peak_pct")
    ratio = ram / vcpu if vcpu else 4
    family = "Fsv2" if ratio <= 2 else "Dsv5" if ratio <= 5 else "Esv5"

    if peak is not None:
        needed = max(1.0, vcpu * (float(peak) / 100.0) / 0.75)
        confidence, basis = "medium", f"sized to {peak}% peak with 25% headroom"
    else:
        needed = vcpu / 2.0
        confidence, basis = "low", "no utilisation data - assumed oversized, mapped one size down"

    table = _SKU_TABLE[family]
    pick = next((row for row in table if row[0] >= needed), table[-1])
    return {
        "server_id": sid,
        "sku": pick[2],
        "family": family,
        "vcpu": pick[0],
        "ram_gb": pick[1],
        "disk_tier": _disk_tier(s.get("used_disk_gb")),
        "confidence": confidence,
        "basis": basis,
    }


@bp.route(route="vm_rightsize", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def vm_rightsize(req: func.HttpRequest) -> func.HttpResponse:
    try:
        servers = req.get_json().get("servers") or []
    except ValueError:
        servers = []
    if not isinstance(servers, list) or not servers:
        return _json({"error": "body must be {\"servers\": [ {server_id, vcpu, ram_gb, ...} ]}"}, 400)
    recs = [_rightsize_one(s) for s in servers[:500]]
    return _json({"recommendations": recs, "heuristic": _HEURISTIC})


# ==========================================================================
# azure_retail_prices
# ==========================================================================
_PRICES_URL = "https://prices.azure.com/api/retail/prices"
_CACHE_TTL = 6 * 3600
_KEEP = (
    "armSkuName", "skuName", "productName", "meterName", "armRegionName",
    "retailPrice", "unitOfMeasure", "type", "reservationTerm", "effectiveStartDate",
)


def _price_filter(p: dict) -> str:
    clauses = []
    if p.get("arm_sku_name"):
        clauses.append(f"armSkuName eq '{p['arm_sku_name']}'")
    if p.get("sku_name"):
        clauses.append(f"contains(skuName, '{p['sku_name']}')")
    if p.get("arm_region_name"):
        clauses.append(f"armRegionName eq '{p['arm_region_name']}'")
    if p.get("service_name"):
        clauses.append(f"serviceName eq '{p['service_name']}'")
    if p.get("price_type"):
        clauses.append(f"priceType eq '{p['price_type']}'")
    return " and ".join(clauses)


@bp.route(route="azure_retail_prices", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def azure_retail_prices(req: func.HttpRequest) -> func.HttpResponse:
    p = {k: req.params.get(k) for k in
         ("arm_sku_name", "sku_name", "arm_region_name", "service_name", "price_type")}
    if req.method == "POST":
        try:
            p.update({k: v for k, v in (req.get_json() or {}).items() if v})
        except ValueError:
            pass
    odata = _price_filter(p)
    if not odata:
        return _json({"error": "give at least one of arm_sku_name, sku_name, arm_region_name, service_name"}, 400)

    hit = _state.get(odata)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        items = hit[1]
    else:
        try:
            items = _fetch_prices(odata)
        except Exception as exc:
            logging.exception("retail prices fetch failed")
            return _json({"error": f"price API error: {exc}", "filter": odata}, 502)
        _state[odata] = (time.time(), items)

    return _json({"filter": odata, "count": len(items), "items": items})


def _fetch_prices(odata: str, max_pages: int = 3) -> list:
    url = f"{_PRICES_URL}?currencyCode=USD&$filter={urllib.parse.quote(odata)}"
    out: list = []
    for _ in range(max_pages):
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        out.extend({k: it.get(k) for k in _KEEP} for it in data.get("Items", []))
        url = data.get("NextPageLink")
        if not url:
            break
    return out


# --------------------------------------------------------------------------
def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, default=str), status_code=status, mimetype="application/json"
    )
