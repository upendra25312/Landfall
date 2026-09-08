"""
Run the full Landfall tool chain deterministically (no network) and assemble the
estimate package — the substrate for the E7.2 full-estimate scenarios.
"""
from __future__ import annotations

from cost.compute_cost import estimate_compute_cost
from cost.config import load_config
from cost.rightsize import rightsize_many
from cost.run_rate import estimate_run_rate_extras
from cost.storage_cost import estimate_storage_cost
from lz.design import design_landing_zone
from waves.disposition import score_dispositions
from waves.plan import plan_waves
from deliverable.assemble import assemble_estimate

from fixtures import price_book, disk_book, storage_rates, load

PRICE_DATE = "2026-06-01"


def _summary(servers: list[dict], apps: list[dict]) -> dict:
    def _f(s, k):
        try:
            return float(s.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0
    on = [s for s in servers if (s.get("powerstate") or "").lower() != "poweredoff"]
    by_env: dict[str, int] = {}
    for s in servers:
        by_env[s.get("env") or "?"] = by_env.get(s.get("env") or "?", 0) + 1
    eol = sum(1 for s in servers if (s.get("os_eol_date") or "") and s["os_eol_date"] < "2026-09-08")
    return {
        "servers": len(servers), "servers_powered_on": len(on), "applications": len(apps),
        "total_vcpu": int(sum(_f(s, "vcpu") for s in servers)),
        "total_ram_gb": int(sum(_f(s, "ram_gb") for s in servers)),
        "provisioned_disk_tb": round(sum(_f(s, "provisioned_disk_gb") for s in servers) / 1000, 1),
        "used_disk_tb": round(sum(_f(s, "used_disk_gb") for s in servers) / 1000, 1),
        "by_env": by_env, "eol_servers": eol,
        "no_perf_data_servers": sum(1 for s in servers if not (s.get("cpu_p95_pct") or "")),
    }


def run(servers=None, apps=None, deps=None, storage=None, overrides=None,
        dq_confidence="Medium"):
    servers = servers if servers is not None else load("servers")
    apps = apps if apps is not None else load("applications")
    deps = deps if deps is not None else load("dependencies")
    storage = storage if storage is not None else load("storage")
    cfg = load_config(overrides=overrides)

    roll: dict[str, dict] = {}
    for s in servers:
        aid = s.get("app_id")
        if aid:
            r = roll.setdefault(aid, {"servers": 0, "eol_servers": 0})
            r["servers"] += 1
            if (s.get("os_eol_date") or "") and s["os_eol_date"] < "2026-09-08":
                r["eol_servers"] += 1

    rs = rightsize_many(servers, cfg)  # noqa: F841 (kept for parity / future asserts)
    cc = estimate_compute_cost(servers, price_book(), disk_book(), cfg, PRICE_DATE)
    sc = estimate_storage_cost(storage, storage_rates(), cfg, "2026-09-01")
    infra = (cc["totals"]["monthly"] or 0) + (sc["totals"]["monthly"] or 0)
    rr = estimate_run_rate_extras(servers, infra, cfg)
    lz = design_landing_zone(apps, {"total_servers": len(servers)}, cfg)
    disp = score_dispositions(apps, roll, cfg)
    wav = plan_waves(apps, servers, deps, cfg)

    package = assemble_estimate({
        "inventory_summary": _summary(servers, apps),
        "data_quality": {"confidence": dq_confidence, "findings": []},
        "generated_on": "2026-09-08",
        "compute_cost": cc, "storage_cost": sc, "run_rate_extras": rr,
        "landing_zone": lz, "dispositions": disp, "waves": wav,
    }, cfg)
    return package


def figure(package: dict, key: str):
    for f in package["figures"]:
        if f["key"] == key:
            return f["value"]
    return None
