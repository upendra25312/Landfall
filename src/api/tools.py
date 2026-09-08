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
import time
import urllib.parse
import urllib.request

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from sqlguard import safe_select as _safe_select, signature as _sql_signature
from engagement import normalize_engagement as _norm_engagement, DEFAULT_ENGAGEMENT as _DEFAULT_ENGAGEMENT
from engagement_sql import set_engagement as _set_engagement

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


_SQL_RESUME_HINTS = (
    "is not currently available",   # 40613 - serverless auto-pause resuming
    "40613", "40197", "40501", "49918", "49919", "49920", "4060",
    "login timeout", "connection timeout", "server was not found",
)


def _sql_connect(attempts: int = 4, backoff_s: float = 8.0):
    """mssql-python connection with an Entra token from the workload identity.

    The database is Azure SQL serverless with auto-pause on (cost), so the first
    call after an idle period fails while it resumes (~30-60 s). Retry a few times
    on the transient resume/timeout errors before giving up."""
    import mssql_python

    server = os.environ["AZURE_SQL_SERVER_FQDN"]
    database = os.environ["AZURE_SQL_DATABASE"]
    last: Exception | None = None
    for i in range(attempts):
        try:
            return mssql_python.connect(
                f"Server={server};Database={database};Encrypt=yes;",
                token_provider=_cred,
            )
        except Exception as exc:                                # noqa: BLE001
            msg = str(exc).lower()
            if i == attempts - 1 or not any(h in msg for h in _SQL_RESUME_HINTS):
                raise
            last = exc
            logging.info("sql connect retry %d/%d (database resuming)", i + 1, attempts - 1)
            time.sleep(backoff_s * (i + 1))
    raise last  # unreachable


# ==========================================================================
# query_inventory
# ==========================================================================
SCHEMA_HINT = """Tables (Azure SQL, schema dbo). All columns nullable - client data has gaps.
app_id / server_id are soft links (not FK-enforced); rows may reference missing keys.
Every table also has source_file and ingested_at (ignore unless asked about provenance).

servers(server_id, hostname, env /* prod|nonprod|dev|dr */, os_name, os_version,
        os_eol_date, vcpu, ram_gb, provisioned_disk_gb, used_disk_gb,
        cpu_avg_pct, cpu_peak_pct, cpu_p95_pct, ram_avg_pct, ram_p95_pct /* 30-day rollups; p95 = right-sizing signal */,
        disk_iops_avg, disk_iops_peak, net_in_gb_30d, net_out_gb_30d /* 30-day totals */,
        cluster, datacenter, powerstate /* poweredOn|poweredOff */,
        app_id /* -> applications.app_id */, notes)
applications(app_id, app_name, business_owner, criticality /* 1 high..4 */, users,
        tech_stack, db_engine, internet_facing /* bit */,
        compliance_scope /* e.g. PCI-DSS, HIPAA, GDPR, SOX; 'None' or NULL if unscoped */,
        disposition, complexity /* S|M|L|XL */, wave)
dependencies(dep_id, src_id, dst_id, port, protocol, direction /* inbound|outbound */,
        confidence /* high|medium|low */,
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

QUERY_TIMEOUT_S = int(os.environ.get("QUERY_TIMEOUT_S", "20"))


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
        body = req.get_json() or {}
    except ValueError:
        body = {}
    question = (body.get("question") or "").strip()
    if not question:
        return _json({"error": "body must be {\"engagement\": \"<customer>/<project>\", \"question\": \"...\"}"}, 400)
    raw_eng = body.get("engagement") or req.params.get("engagement") or _DEFAULT_ENGAGEMENT
    try:
        engagement = _norm_engagement(raw_eng)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)

    sig = _sql_signature(question)
    try:
        sql = _sql_for(question)
    except ValueError as exc:
        logging.warning("query_inventory rejected q=%s: %s", sig["q_hash"], exc)
        return _json({"error": f"could not build a safe query ({exc})", "sql": ""}, 400)
    except Exception as exc:                                   # noqa: BLE001
        logging.error("query_inventory text-to-SQL failed q=%s: %s", sig["q_hash"],
                      type(exc).__name__)
        return _json({"error": "text-to-SQL failed"}, 502)

    sig = _sql_signature(question, sql)
    logging.info("query_inventory eng=%s q=%s shape=%s tables=%s", engagement,
                 sig["q_hash"], sig.get("shape"), ",".join(sig.get("tables", [])))
    try:
        conn = _sql_connect()
        try:
            cur = conn.cursor()
            try:
                cur.timeout = QUERY_TIMEOUT_S
            except Exception:                                  # noqa: BLE001
                pass
            _set_engagement(cur, engagement)   # RLS: scope every table to this engagement
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            fetched = cur.fetchmany(MAX_ROWS + 1)
        finally:
            conn.close()
    except Exception as exc:                                   # noqa: BLE001
        logging.error("query_inventory query failed q=%s: %s", sig["q_hash"],
                      type(exc).__name__)
        return _json({"error": "query failed", "sql": sql}, 502)

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


# vm_rightsize moved to cost/functions.py (deterministic, RAM-aware, config-driven).


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
