"""
Deterministic VM right-sizer (PRD E2.1, closes audit FIN-1 / FIN-2).

Rules, all driven by estimation_config.json ["rightsize"]:
  * Size against BOTH dimensions: vcpu_need and ram_need, independently. The SKU is
    the smallest that meets both; the output says which one bound it. (A 128 GB box
    can never be mapped to a 32 GB SKU.)
  * With utilisation data (p95 by default, falling back peak -> avg): scale the
    current allocation by observed_util / target_util, floored at
    min_*_retain_pct of current.
  * Without utilisation data: scale by no_perf_data.{cpu,ram}_scale_pct (default
    100 = keep as-is — no blind haircut) and mark confidence "low".
  * Report a low / expected / high range using headroom_band_pct.

Pure functions — no Azure, no I/O.
"""
from __future__ import annotations

from .config import load_config
from .skus import CATALOG_VERSION, disk_tier, family_for, pick_sku


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_PEAK_TO_P95 = 0.75   # rough proxy when only an absolute 30-day peak is available


def _util_fraction(server: dict, kind: str, metric: str):
    """Observed utilisation as a fraction (0..1+), or None. kind = 'cpu' | 'ram'.

    Right-sizing keys off p95 (sustained-busy), then average. An absolute peak is
    used only if nothing else exists, discounted by _PEAK_TO_P95 — sizing to a raw
    30-day maximum systematically over-provisions.
    """
    order = {
        "p95": [f"{kind}_p95_pct", f"{kind}_avg_pct", f"{kind}_peak_pct"],
        "peak": [f"{kind}_peak_pct", f"{kind}_p95_pct", f"{kind}_avg_pct"],
        "avg": [f"{kind}_avg_pct", f"{kind}_p95_pct", f"{kind}_peak_pct"],
    }.get(metric, [f"{kind}_p95_pct", f"{kind}_avg_pct", f"{kind}_peak_pct"])
    aliases = {
        f"{kind}_p95_pct": [f"{kind}_p95_pct", "mem_p95_pct" if kind == "ram" else None],
        f"{kind}_peak_pct": [f"{kind}_peak_pct", "mem_peak_pct" if kind == "ram" else None],
        f"{kind}_avg_pct": [f"{kind}_avg_pct", "mem_avg_pct" if kind == "ram" else None],
    }
    for col in order:
        for real in (a for a in aliases.get(col, [col]) if a):
            v = _num(server.get(real))
            if v is not None:
                frac = v / 100.0
                if real.endswith("_peak_pct") and metric != "peak":
                    return frac * _PEAK_TO_P95, f"{real}x{_PEAK_TO_P95}"
                return frac, real
    return None, None


def rightsize_one(server: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    rs = cfg["rightsize"]
    metric = rs.get("utilisation_metric", "p95")

    vcpu = _num(server.get("vcpu")) or 2.0
    ram = _num(server.get("ram_gb")) or vcpu * 4

    cpu_frac, cpu_src = _util_fraction(server, "cpu", metric)
    ram_frac, ram_src = _util_fraction(server, "ram", metric)
    has_cpu = cpu_frac is not None

    if has_cpu:
        cpu_need = vcpu * cpu_frac / (rs["cpu_target_utilisation_pct"] / 100.0)
        cpu_need = max(cpu_need, vcpu * rs["min_vcpu_retain_pct"] / 100.0)
        if ram_frac is not None:
            ram_need = ram * ram_frac / (rs["ram_target_utilisation_pct"] / 100.0)
            confidence = "high"
        else:
            ram_need = ram * 0.85          # only CPU known -> stay conservative on RAM
            confidence = "medium"
        ram_need = max(ram_need, ram * rs["min_ram_retain_pct"] / 100.0)
        basis = (f"sized to {metric} utilisation "
                 f"(CPU {cpu_frac * 100:.0f}% from {cpu_src}"
                 + (f", RAM {ram_frac * 100:.0f}% from {ram_src}" if ram_frac is not None else ", RAM not observed")
                 + f") at {rs['cpu_target_utilisation_pct']}/{rs['ram_target_utilisation_pct']}% targets")
    else:
        np = rs["no_perf_data"]
        cpu_need = vcpu * np["cpu_scale_pct"] / 100.0
        ram_need = ram * np["ram_scale_pct"] / 100.0
        confidence = np.get("confidence", "low")
        basis = (f"no utilisation data — kept at {np['cpu_scale_pct']}% vCPU / "
                 f"{np['ram_scale_pct']}% RAM of current (no blind reduction); "
                 f"confirm in discovery")

    cpu_need = max(cpu_need, float(rs["vcpu_floor"]))
    ram_need = max(ram_need, float(rs["ram_floor_gb"]))

    family = family_for(ram_need / cpu_need if cpu_need else 4)
    sku, fam, sku_v, sku_r, capped = pick_sku(family, cpu_need, ram_need)
    bound_by = "ram" if (ram_need / sku_r) >= (cpu_need / sku_v) else "cpu"

    band = rs["headroom_band_pct"] / 100.0
    lo = pick_sku(family, cpu_need * (1 - band), ram_need * (1 - band))[0]
    hi = pick_sku(family, cpu_need * (1 + band), ram_need * (1 + band))[0]

    disk = disk_tier(
        # keep the provisioned size on migration unless storage is being right-sized
        _num(server.get("provisioned_disk_gb")) or _num(server.get("used_disk_gb")),
        _num(server.get("disk_iops_peak")),
    )

    return {
        "server_id": server.get("server_id"),
        "current": {"vcpu": int(vcpu), "ram_gb": round(ram, 1)},
        "recommended": {
            "sku": sku, "family": fam, "vcpu": sku_v, "ram_gb": sku_r,
            "bound_by": bound_by, "at_catalog_ceiling": capped,
        },
        "range": {"low": lo, "expected": sku, "high": hi},
        "need": {"vcpu": round(cpu_need, 2), "ram_gb": round(ram_need, 1)},
        "disk": disk,
        "utilisation_used": (
            None if not has_cpu else
            {"metric": metric, "cpu_pct": round(cpu_frac * 100, 1),
             "ram_pct": round(ram_frac * 100, 1) if ram_frac is not None else None}
        ),
        "confidence": confidence,
        "basis": basis,
        "delta": {"vcpu": sku_v - int(vcpu), "ram_gb": round(sku_r - ram, 1)},
    }


def rightsize_many(servers: list[dict], cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    recs = [rightsize_one(s, cfg) for s in servers]
    downsized = sum(1 for r in recs if r["delta"]["vcpu"] < 0)
    return {
        "recommendations": recs,
        "summary": {
            "servers": len(recs),
            "downsized": downsized,
            "at_ceiling": sum(1 for r in recs if r["recommended"]["at_catalog_ceiling"]),
            "low_confidence": sum(1 for r in recs if r["confidence"] == "low"),
            "current_vcpu": sum(r["current"]["vcpu"] for r in recs),
            "recommended_vcpu": sum(r["recommended"]["vcpu"] for r in recs),
        },
        "config": {
            "source": cfg.get("_source"),
            "rightsize": cfg["rightsize"],
        },
        "catalog_version": CATALOG_VERSION,
    }
