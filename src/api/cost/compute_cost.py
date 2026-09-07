"""
Monthly Azure compute cost for a set of on-prem servers (PRD E2.2).

    result = estimate_compute_cost(servers, price_book, disk_book, cfg)

Deterministic. Right-sizes each server (cost.rightsize), then prices the
recommended SKU: PAYG, reserved (1yr/3yr), Azure Hybrid Benefit, dev/test, and a
per-environment scale factor — all from estimation_config.json. Returns a
line-item bill of materials plus a low / expected / high range that carries the
right-sizer's own uncertainty (range.low SKU at RI → high SKU at PAYG).

The price data is injected (a PriceBook / DiskBook) so this module has no network
dependency; `cost.pricing` builds those from prices.azure.com.
"""
from __future__ import annotations

from .config import load_config
from .rightsize import rightsize_many

HOURS_PER_MONTH = 730
_TERM_KEY = {"1yr": "ri1y", "3yr": "ri3y", "none": None}


def _lic(os_name: str | None, ahb_windows: bool) -> tuple[str, bool]:
    is_win = "windows" in (os_name or "").lower()
    if is_win and ahb_windows:
        return "linux", True          # AHB: pay the no-licence (Linux) rate
    return ("windows" if is_win else "linux"), False


def _env_factor(env: str | None, cfg: dict) -> float:
    up = cfg["uplift"]
    e = (env or "").lower()
    if e in ("nonprod", "non-prod", "dev", "test", "uat", "qa"):
        f = up["nonprod_of_prod_pct"] / 100.0
        if cfg["pricing"].get("dev_test_pricing_nonprod"):
            f *= 1 - up.get("dev_test_discount_pct", 0) / 100.0
        return f
    if e in ("dr", "disaster-recovery"):
        return up["dr_of_prod_pct"] / 100.0
    return 1.0


def _hourly(price_book: dict, sku: str, lic: str, key: str | None):
    entry = (price_book.get(sku) or {}).get(lic) or {}
    payg = entry.get("payg")
    if payg is None:
        return None, None
    ri = entry.get(key) if key else None
    return payg, ri


def estimate_compute_cost(
    servers: list[dict],
    price_book: dict,
    disk_book: dict | None = None,
    cfg: dict | None = None,
    price_date: str | None = None,
) -> dict:
    cfg = cfg or load_config()
    disk_book = disk_book or {}
    pr = cfg["pricing"]
    term = str(pr.get("reserved_term", "none")).lower()
    ri_key = _TERM_KEY.get(term)
    cov = pr.get("reservation_coverage_pct", 0) / 100.0
    ahb = bool(pr.get("azure_hybrid_benefit_windows"))

    by_id = {s.get("server_id"): s for s in servers}
    rs = rightsize_many(servers, cfg)

    lines: list[dict] = []
    missing: set[str] = set()

    for rec in rs["recommendations"]:
        s = by_id.get(rec["server_id"], {})
        env = s.get("env")
        lic, ahb_applied = _lic(s.get("os_name"), ahb)
        factor = _env_factor(env, cfg)

        sku = rec["recommended"]["sku"]
        payg_h, ri_h = _hourly(price_book, sku, lic, ri_key)
        if payg_h is None:
            missing.add(sku)

        def _compute(_sku, use_ri):
            ph, rh = _hourly(price_book, _sku, lic, ri_key)
            if ph is None:
                return None
            h = (rh if (use_ri and rh) else ph)
            return h * HOURS_PER_MONTH * factor

        payg_m = _compute(sku, False)
        ri_m = _compute(sku, True)
        if payg_h is None:
            eff_m = None
        elif ri_key and ri_h:
            eff_m = (cov * ri_h + (1 - cov) * payg_h) * HOURS_PER_MONTH * factor
        else:
            eff_m = payg_h * HOURS_PER_MONTH * factor

        disk_m = disk_book.get(rec["disk"]["tier"], 0.0)

        low_c = _compute(rec["range"]["low"], True)
        high_c = _compute(rec["range"]["high"], False)

        lines.append({
            "server_id": rec["server_id"],
            "env": env,
            "os": "windows" if lic == "windows" or ahb_applied else "linux",
            "sku": sku,
            "ahb_applied": ahb_applied,
            "env_factor": round(factor, 3),
            "compute_payg_monthly": _round(payg_m),
            "compute_ri_monthly": _round(ri_m),
            "compute_effective_monthly": _round(eff_m),
            "disk_tier": rec["disk"]["tier"],
            "disk_monthly": _round(disk_m),
            "total_monthly": _round((eff_m or 0) + disk_m),
            "low_monthly": _round((low_c or eff_m or 0) + disk_m),
            "high_monthly": _round((high_c or eff_m or 0) + disk_m),
            "confidence": rec["confidence"],
        })

    def _sum(k):
        return round(sum(x[k] or 0 for x in lines), 2)

    by_env: dict[str, dict] = {}
    for x in lines:
        e = by_env.setdefault(x["env"] or "unknown",
                              {"servers": 0, "effective_monthly": 0.0, "total_monthly": 0.0})
        e["servers"] += 1
        e["effective_monthly"] = round(e["effective_monthly"] + (x["compute_effective_monthly"] or 0), 2)
        e["total_monthly"] = round(e["total_monthly"] + x["total_monthly"], 2)

    monthly = _sum("total_monthly")
    return {
        "currency": pr.get("currency", "USD"),
        "region": pr.get("region"),
        "price_date": price_date,
        "reserved_term": term,
        "reservation_coverage_pct": pr.get("reservation_coverage_pct", 0),
        "assumptions": [
            f"{HOURS_PER_MONTH} hours/month, region {pr.get('region')}, prices as of {price_date or 'n/a'}",
            (f"{pr.get('reservation_coverage_pct', 0)}% of steady-state on {term} reserved instances"
             if ri_key else "pay-as-you-go only (no reserved-instance assumption)"),
            ("Azure Hybrid Benefit applied to Windows servers" if ahb
             else "no Azure Hybrid Benefit"),
            "one managed disk per VM sized to provisioned capacity; file shares, DB and "
            "object storage are priced separately (estimate_storage_cost)",
            (f"no retail price found for {len(missing)} SKU(s): {', '.join(sorted(missing))}"
             if missing else "all recommended SKUs priced"),
        ],
        "line_items": lines,
        "by_environment": by_env,
        "totals": {
            "compute_payg_monthly": _sum("compute_payg_monthly"),
            "compute_ri_monthly": _sum("compute_ri_monthly"),
            "compute_effective_monthly": _sum("compute_effective_monthly"),
            "storage_monthly": _sum("disk_monthly"),
            "monthly": monthly,
            "annual": round(monthly * 12, 2),
            "range": {
                "low_monthly": _sum("low_monthly"),
                "expected_monthly": monthly,
                "high_monthly": _sum("high_monthly"),
            },
        },
        "missing_prices": sorted(missing),
        "rightsize_summary": rs["summary"],
        "config": {"source": cfg.get("_source"), "pricing": pr, "uplift": cfg["uplift"]},
    }


def _round(v):
    return None if v is None else round(v, 2)
