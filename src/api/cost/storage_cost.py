"""
Monthly Azure cost for the dbo.storage table — file shares, DB volumes, object
storage (PRD E2.3).

    result = estimate_storage_cost(rows, rates, cfg)

Deterministic. Classifies each volume from its `type` + `target_service`, applies a
USD/GB-month rate (from estimation_config.json ["storage"] or an injected rate book),
and returns a line-item bill with a low / expected / high range.

Kept DISJOINT from estimate_compute_cost: that tool already prices one managed disk
per VM (`type='block'`), so block volumes are EXCLUDED here and only reported, unless
cfg["storage"]["price_block_from_storage_table"] is set — in which case the caller
should run estimate_compute_cost with disk pricing suppressed to avoid double-count.

No network — `rates` is injected; `cost.pricing.fetch_storagebook` builds it.
"""
from __future__ import annotations

from .config import load_config

# (category, USD/GB-month) — the category also selects a min-provision floor.
_FILE_CATEGORIES = ("files_premium", "files_standard_hot",
                    "anf_standard", "anf_premium", "anf_ultra")
_DB_CATEGORIES = ("db_sql_mi", "db_sql_hyperscale", "db_flex_postgresql",
                  "db_flex_mysql", "db_oracle")
_OBJECT_CATEGORIES = ("blob_hot_lrs", "blob_cool_lrs")


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify(row: dict) -> tuple[str, str]:
    """(bucket, category) for a storage row. bucket = file|db|object|block."""
    typ = (row.get("type") or "").strip().lower()
    svc = (row.get("target_service") or "").strip().lower()

    if typ == "file":
        if "netapp" in svc or "anf" in svc:
            if "ultra" in svc:
                return "file", "anf_ultra"
            if "standard" in svc:
                return "file", "anf_standard"
            return "file", "anf_premium"
        if "standard" in svc:
            return "file", "files_standard_hot"
        return "file", "files_premium"

    if typ == "db":
        if "managed instance" in svc or "sql mi" in svc or "sql managed" in svc:
            return "db", "db_sql_mi"
        if "hyperscale" in svc:
            return "db", "db_sql_hyperscale"
        if "postgres" in svc:
            return "db", "db_flex_postgresql"
        if "mysql" in svc or "mariadb" in svc:
            return "db", "db_flex_mysql"
        if "oracle" in svc:
            return "db", "db_oracle"
        return "db", "db_sql_mi"

    if typ == "object" or "blob" in svc:
        return "object", ("blob_cool_lrs" if "cool" in svc or "archive" in svc
                          else "blob_hot_lrs")

    # block / managed disk / anything else
    return "block", "managed_premium_ssd_v2"


def _billable_gb(bucket: str, category: str, size_gb: float, st: dict) -> tuple[float, str]:
    floors = st.get("min_provision_gb", {})
    if bucket == "db":
        head = st.get("db_growth_headroom_pct", 0) / 100.0
        return round(size_gb * (1 + head), 1), (
            f"data {size_gb:g} GB + {st.get('db_growth_headroom_pct', 0):g}% provisioning headroom"
            if head else f"provisioned {size_gb:g} GB")
    floor = floors.get(category)
    if floor and size_gb < floor:
        return float(floor), f"provisioned {size_gb:g} GB billed at the {floor:g} GB {category} floor"
    return round(size_gb, 1), f"provisioned {size_gb:g} GB"


def estimate_storage_cost(
    rows: list[dict],
    rates: dict | None = None,
    cfg: dict | None = None,
    price_date: str | None = None,
) -> dict:
    cfg = cfg or load_config()
    st = cfg["storage"]
    rate_book = dict(st.get("rates_usd_gb_month", {}))
    if rates:
        rate_book.update({k: v for k, v in rates.items() if v is not None})
    band = st.get("rate_band_pct", 0) / 100.0
    price_block = bool(st.get("price_block_from_storage_table"))

    lines: list[dict] = []
    excluded_block_gb = 0.0
    excluded_block_n = 0
    missing: set[str] = set()

    for r in rows:
        size = _num(r.get("size_gb"))
        bucket, category = classify(r)

        if bucket == "block" and not price_block:
            excluded_block_n += 1
            excluded_block_gb += size or 0.0
            continue
        if size is None or size <= 0:
            missing.add(f"{r.get('storage_id')}: no size_gb")
            continue

        rate = rate_book.get(category)
        if rate is None:
            missing.add(f"no rate for category '{category}'")
            continue

        billable, basis = _billable_gb(bucket, category, size, st)
        monthly = billable * rate
        lines.append({
            "storage_id": r.get("storage_id"),
            "server_id": r.get("server_id"),
            "type": r.get("type"),
            "target_service": r.get("target_service"),
            "category": category,
            "size_gb": round(size, 1),
            "billable_gb": billable,
            "rate_usd_gb_month": round(rate, 5),
            "monthly": round(monthly, 2),
            "low_monthly": round(monthly * (1 - band), 2),
            "high_monthly": round(monthly * (1 + band), 2),
            "basis": basis,
        })

    def _bsum(items, k):
        return round(sum(x[k] for x in items), 2)

    by_type: dict[str, dict] = {}
    for x in lines:
        b = "object" if x["category"] in _OBJECT_CATEGORIES else (
            "db" if x["category"] in _DB_CATEGORIES else
            "file" if x["category"] in _FILE_CATEGORIES else "block")
        e = by_type.setdefault(b, {"volumes": 0, "size_gb": 0.0, "monthly": 0.0})
        e["volumes"] += 1
        e["size_gb"] = round(e["size_gb"] + x["size_gb"], 1)
        e["monthly"] = round(e["monthly"] + x["monthly"], 2)

    monthly = _bsum(lines, "monthly")
    caveats = [
        f"list rates as of {price_date or 'n/a'}; USD/GB-month per category "
        f"(source: {'injected rate book + ' if rates else ''}estimation_config.json)",
        "DB lines are the STORAGE component of a managed/PaaS database only — the "
        "database compute (vCores) and licensing are a replatform decision, sized separately",
    ]
    if excluded_block_n and not price_block:
        caveats.append(
            f"{excluded_block_n} block volume(s) ({excluded_block_gb:,.0f} GB) excluded — "
            "priced by estimate_compute_cost (one managed disk per VM). Set "
            "storage.price_block_from_storage_table to itemise them here instead.")
    if missing:
        caveats.append(f"{len(missing)} row(s) not costed: {'; '.join(sorted(missing)[:5])}"
                       + (" ..." if len(missing) > 5 else ""))

    return {
        "currency": cfg["pricing"].get("currency", "USD"),
        "region": cfg["pricing"].get("region"),
        "price_date": price_date,
        "line_items": lines,
        "by_type": by_type,
        "excluded": {
            "block_volumes": excluded_block_n,
            "block_gb": round(excluded_block_gb, 1),
            "note": ("priced by estimate_compute_cost" if not price_block
                     else "priced here (price_block_from_storage_table=true)"),
        },
        "totals": {
            "file_monthly": _bsum([x for x in lines if x["category"] in _FILE_CATEGORIES], "monthly"),
            "db_monthly": _bsum([x for x in lines if x["category"] in _DB_CATEGORIES], "monthly"),
            "object_monthly": _bsum([x for x in lines if x["category"] in _OBJECT_CATEGORIES], "monthly"),
            "monthly": monthly,
            "annual": round(monthly * 12, 2),
            "range": {
                "low_monthly": _bsum(lines, "low_monthly"),
                "expected_monthly": monthly,
                "high_monthly": _bsum(lines, "high_monthly"),
            },
        },
        "not_costed": sorted(missing),
        "caveats": caveats,
        "config": {"source": cfg.get("_source"), "storage": st},
    }
