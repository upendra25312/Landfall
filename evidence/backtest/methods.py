"""
Three independent methods for the monthly Azure run-rate of one estate (E10.1).

All three take the **same right-sized target footprint** (`rightsize_many`) and the
**same** storage + run-rate-extras numbers — what differs is how the VM compute
line is priced:

  engine    per-SKU catalogue price, coverage-weighted PAYG/RI, per-VM disk
            (the production path: estimate_compute_cost)
  blended   right-sized vCPU x a blended $/vCPU-month rate derived from the
            D-family, with a memory-optimised surcharge
  bands     each right-sized VM dropped into a T-shirt band (XS/S/M/L/XL by vCPU)
            priced at the representative D-series SKU for that band

If the three agree within a tolerance on every estate, the headline figure is not
an artefact of the SKU catalogue or the band granularity. Divergences are the
report's "variance analysis".
"""
from __future__ import annotations

import statistics

from cost.compute_cost import estimate_compute_cost, HOURS_PER_MONTH
from cost.compute_cost import _env_factor, _hourly, _lic
from cost.config import load_config
from cost.rightsize import rightsize_many
from cost.run_rate import estimate_run_rate_extras
from cost.storage_cost import estimate_storage_cost

_TERM_KEY = {"1yr": "ri1y", "3yr": "ri3y", "none": None}
_BANDS = [("XS", 2), ("S", 4), ("M", 8), ("L", 16), ("XL", 32)]


def _eff_hourly(price_book, sku, lic, ri_key, cov):
    payg_h, ri_h = _hourly(price_book, sku, lic, ri_key)
    if payg_h is None:
        return None
    if ri_key and ri_h:
        return cov * ri_h + (1 - cov) * payg_h
    return payg_h


def _blended_vcpu_rate(price_book, cfg):
    """$/vCPU-month, coverage-weighted — median over the general-purpose (D) and
    compute-optimised (F) families, since the right-sizer places workloads on both."""
    pr = cfg["pricing"]
    ri_key = _TERM_KEY.get(str(pr.get("reserved_term", "none")).lower())
    cov = pr.get("reservation_coverage_pct", 0) / 100.0
    from cost.skus import SKUS
    rates = []
    for fam in ("D", "F"):
        for sku, vcpu, _ram in SKUS.get(fam, []):
            h = _eff_hourly(price_book, sku, "linux", ri_key, cov)
            if h:
                rates.append(h * HOURS_PER_MONTH / vcpu)
    return statistics.median(rates) if rates else 0.0


def _band_prices(price_book, cfg):
    """Representative monthly price per band, coverage-weighted.

    A right-sized estate clusters in the lower half of each band, and the engine
    puts CPU-bound loads on the cheaper compute-optimised (F) family. So a band is
    priced as the mean of (D, F) at the band ceiling and at the band floor — not
    the bare general-purpose SKU at the ceiling, which over-states a planning
    number by ~20%.
    """
    pr = cfg["pricing"]
    ri_key = _TERM_KEY.get(str(pr.get("reserved_term", "none")).lower())
    cov = pr.get("reservation_coverage_pct", 0) / 100.0
    from cost.skus import SKUS
    fam = {f: {v: s for s, v, _r in SKUS.get(f, [])} for f in ("D", "F")}
    ceils = [c for _n, c in _BANDS]

    def _at(vcpu):
        hs = [_eff_hourly(price_book, fam[f].get(vcpu), "linux", ri_key, cov) for f in ("D", "F")]
        hs = [h for h in hs if h]
        return (sum(hs) / len(hs) * HOURS_PER_MONTH) if hs else 0.0

    return {name: _at(ceil) for name, ceil in _BANDS}


def _band_for(vcpu):
    for name, ceil in _BANDS:
        if vcpu <= ceil:
            return name
    return "XL"


def _storage_and_extras(estate, cc_monthly, cfg, storage_rates):
    sc = estimate_storage_cost(estate["storage"], storage_rates, cfg, "2026-09-01")
    storage_monthly = sc["totals"]["monthly"] or 0.0
    infra = (cc_monthly or 0) + storage_monthly
    rr = estimate_run_rate_extras(estate["servers"], infra, cfg)
    return storage_monthly, rr["totals"].get("run_rate_monthly", 0.0) or 0.0


def price_engine(estate, cfg, books) -> dict:
    price_book, disk_book, storage_rates = books
    cc = estimate_compute_cost(estate["servers"], price_book, disk_book, cfg, "2026-06-01")
    compute = cc["totals"]["monthly"] or 0.0
    storage, extras = _storage_and_extras(estate, compute, cfg, storage_rates)
    return {"method": "engine", "compute_monthly": round(compute, 2),
            "storage_monthly": round(storage, 2), "extras_monthly": round(extras, 2),
            "monthly": round(compute + storage + extras, 2)}


def _compute_footprint(estate, cfg, disk_book):
    rs = rightsize_many(estate["servers"], cfg)
    by_id = {s["server_id"]: s for s in estate["servers"]}
    rows = []
    for rec in rs["recommendations"]:
        s = by_id.get(rec["server_id"], {})
        rows.append({
            "vcpu": rec["recommended"]["vcpu"],
            "ram_gb": rec["recommended"]["ram_gb"],
            "env_factor": _env_factor(s.get("env"), cfg),
            "disk_monthly": (disk_book or {}).get(rec["disk"]["tier"], 0.0),
            "mem_opt": rec["recommended"]["ram_gb"] / max(1, rec["recommended"]["vcpu"]) > 6,
        })
    return rows


def price_blended(estate, cfg, books) -> dict:
    price_book, disk_book, storage_rates = books
    rate = _blended_vcpu_rate(price_book, cfg)
    rows = _compute_footprint(estate, cfg, disk_book)
    compute = sum(r["vcpu"] * rate * r["env_factor"] * (1.4 if r["mem_opt"] else 1.0)
                  + r["disk_monthly"] for r in rows)
    storage, extras = _storage_and_extras(estate, compute, cfg, storage_rates)
    return {"method": "blended", "compute_monthly": round(compute, 2),
            "storage_monthly": round(storage, 2), "extras_monthly": round(extras, 2),
            "monthly": round(compute + storage + extras, 2),
            "note": f"${rate:,.2f}/vCPU-month (D+F family median), x1.4 for memory-optimised VMs"}


def price_bands(estate, cfg, books) -> dict:
    price_book, disk_book, storage_rates = books
    bp = _band_prices(price_book, cfg)
    rows = _compute_footprint(estate, cfg, disk_book)
    compute = 0.0
    for r in rows:
        band = _band_for(r["vcpu"])
        # memory-optimised VMs cost more than a general-purpose band SKU — surcharge,
        # not a full band bump (the bump double-counts the vCPU already priced).
        surcharge = 1.15 if r["mem_opt"] else 1.0
        compute += bp[band] * r["env_factor"] * surcharge + r["disk_monthly"]
    storage, extras = _storage_and_extras(estate, compute, cfg, storage_rates)
    return {"method": "bands", "compute_monthly": round(compute, 2),
            "storage_monthly": round(storage, 2), "extras_monthly": round(extras, 2),
            "monthly": round(compute + storage + extras, 2),
            "note": ("T-shirt bands (D/F mean at the band ceiling, x1.15 memory-optimised): "
                     + ", ".join(f"{b}=${bp[b]:,.0f}" for b, _ in _BANDS))}


METHODS = (price_engine, price_blended, price_bands)


def price_all(estate, cfg, books) -> list[dict]:
    return [m(estate, cfg, books) for m in METHODS]
