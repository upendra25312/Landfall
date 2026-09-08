"""
estimate_effort (PRD E6.2, basic parametric model) — person-days for the migration.

    result = estimate_effort(servers, apps, dispositions, dq_confidence, spokes, regulated, cfg)

Deterministic. Assessment + landing-zone + per-app execution (by disposition) +
testing + cutover + hypercare, then PM / governance / contingency uplifts. The
full model (wave-by-wave resource loading, peak FTE, the loading curve) is a later
cycle — this gives the deliverable a defensible range now.
"""
from __future__ import annotations

from cost.config import load_config


def estimate_effort(server_count: int, app_count: int, dispositions: list[dict] | None,
                    dq_confidence: str = "Medium", spokes: int = 0, regulated: bool = False,
                    waves: int = 0, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    e = cfg["effort"]
    rate = cfg["rates"].get("blended_day_rate", 0)

    disp_counts: dict[str, int] = {}
    for d in (dispositions or []):
        k = d.get("disposition", "Rehost")
        disp_counts[k] = disp_counts.get(k, 0) + 1
    if not disp_counts and app_count:
        disp_counts = {"Rehost": app_count}

    lines: list[dict] = []

    def _add(name, pd, basis):
        lines.append({"workstream": name, "pd": round(pd, 1), "basis": basis})

    _add("Mobilisation & setup", e.get("mobilisation_pd", 0), "fixed")
    _add("Assessment — servers", server_count * e.get("assessment_pd_per_server", 0),
         f"{server_count} servers x {e.get('assessment_pd_per_server')} PD")
    _add("Assessment — applications", app_count * e.get("assessment_pd_per_app", 0),
         f"{app_count} apps x {e.get('assessment_pd_per_app')} PD")

    lz_pd = e.get("landing_zone_pd", 0) + spokes * e.get("landing_zone_pd_per_spoke", 0)
    _add("Landing zone & foundation", lz_pd,
         f"{e.get('landing_zone_pd')} base + {spokes} spokes x {e.get('landing_zone_pd_per_spoke')}")
    if regulated:
        _add("Regulated-spoke controls", e.get("regulated_spoke_controls_pd", 0),
             "portfolio carries a regulated compliance scope")

    exec_map = e.get("execution_pd_per_app", {})
    exec_pd = sum(disp_counts.get(k, 0) * exec_map.get(k, exec_map.get("Rehost", 0))
                  for k in disp_counts)
    _add("Application execution (by disposition)", exec_pd,
         " + ".join(f"{n}x {k}@{exec_map.get(k, 0)}" for k, n in sorted(disp_counts.items())))
    _add("Rehost server execution", server_count * e.get("rehost_pd_per_server", 0),
         f"{server_count} servers x {e.get('rehost_pd_per_server')} PD")
    _add("Testing (functional + NFR)", app_count * e.get("testing_pd_per_app", 0),
         f"{app_count} apps x {e.get('testing_pd_per_app')} PD")
    if waves:
        _add("Wave cutover support", waves * e.get("cutover_pd_per_wave", 0),
             f"{waves} waves x {e.get('cutover_pd_per_wave')} PD")
    _add("Hypercare", e.get("hypercare_pd_per_month", 0) * e.get("hypercare_months", 0),
         f"{e.get('hypercare_pd_per_month')} PD/month x {e.get('hypercare_months')} months")

    delivery = sum(x["pd"] for x in lines)
    pm = delivery * e.get("pm_pct", 0) / 100.0
    gov = delivery * e.get("governance_pct", 0) / 100.0
    base = delivery + pm + gov

    cont_pct = e.get("contingency_pct")
    if cont_pct is None:
        cont_pct = e.get("contingency_by_confidence", {}).get(dq_confidence, 12)
    contingency = base * cont_pct / 100.0
    eac = base + contingency

    band = 0.15  # +/- range on the point estimate
    return {
        "workstreams": lines,
        "delivery_subtotal_pd": round(delivery, 1),
        "pm_pd": round(pm, 1),
        "governance_pd": round(gov, 1),
        "base_pd": round(base, 1),
        "contingency_pct": cont_pct,
        "contingency_pd": round(contingency, 1),
        "estimate_at_completion_pd": round(eac, 1),
        "range_pd": {"low": round(eac * (1 - band)), "expected": round(eac),
                     "high": round(eac * (1 + band))},
        "blended_day_rate": rate,
        "services_cost": {
            "currency": cfg["rates"].get("currency", "USD"),
            "expected": round(eac * rate),
            "low": round(eac * (1 - band) * rate),
            "high": round(eac * (1 + band) * rate),
        },
        "disposition_counts": dict(sorted(disp_counts.items())),
        "basis": (f"contingency {cont_pct}% (data-quality confidence: {dq_confidence}); "
                  f"PM {e.get('pm_pct')}% + governance {e.get('governance_pct')}% on delivery; "
                  f"point estimate +/-{int(band * 100)}%"),
    }
