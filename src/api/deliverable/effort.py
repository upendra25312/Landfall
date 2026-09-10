"""
estimate_effort (PRD E6.2) — person-days for the migration + resource loading.

    result = estimate_effort(servers, apps, dispositions, dq_confidence, spokes,
                             regulated, waves, schedule, cfg)

Deterministic. Assessment + landing-zone + per-app execution (by disposition) +
testing + cutover + hypercare, then PM / governance / contingency uplifts.

When a `schedule` (from `plan_waves` / `build_schedule`, E4.3) is supplied the
workstream person-days are spread across the programme calendar to produce a
month-by-month **resource-loading curve**, the **peak FTE**, and the average FTE
— the full E6.2 model. Without a schedule the parametric range still ships.
"""
from __future__ import annotations

from datetime import date, timedelta

from cost.config import load_config


def estimate_effort(server_count: int, app_count: int, dispositions: list[dict] | None,
                    dq_confidence: str = "Medium", spokes: int = 0, regulated: bool = False,
                    waves: int = 0, schedule: dict | None = None,
                    cfg: dict | None = None) -> dict:
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

    def _add(name, pd, basis, phase):
        lines.append({"workstream": name, "pd": round(pd, 1), "basis": basis, "phase": phase})

    _add("Mobilisation & setup", e.get("mobilisation_pd", 0), "fixed", "mobilise")
    _add("Assessment — servers", server_count * e.get("assessment_pd_per_server", 0),
         f"{server_count} servers x {e.get('assessment_pd_per_server')} PD", "mobilise")
    _add("Assessment — applications", app_count * e.get("assessment_pd_per_app", 0),
         f"{app_count} apps x {e.get('assessment_pd_per_app')} PD", "mobilise")

    lz_pd = e.get("landing_zone_pd", 0) + spokes * e.get("landing_zone_pd_per_spoke", 0)
    _add("Landing zone & foundation", lz_pd,
         f"{e.get('landing_zone_pd')} base + {spokes} spokes x {e.get('landing_zone_pd_per_spoke')}",
         "mobilise")
    if regulated:
        _add("Regulated-spoke controls", e.get("regulated_spoke_controls_pd", 0),
             "portfolio carries a regulated compliance scope", "mobilise")

    exec_map = e.get("execution_pd_per_app", {})
    exec_pd = sum(disp_counts.get(k, 0) * exec_map.get(k, exec_map.get("Rehost", 0))
                  for k in disp_counts)
    _add("Application execution (by disposition)", exec_pd,
         " + ".join(f"{n}x {k}@{exec_map.get(k, 0)}" for k, n in sorted(disp_counts.items())),
         "execute")
    _add("Rehost server execution", server_count * e.get("rehost_pd_per_server", 0),
         f"{server_count} servers x {e.get('rehost_pd_per_server')} PD", "execute")
    _add("Testing (functional + NFR)", app_count * e.get("testing_pd_per_app", 0),
         f"{app_count} apps x {e.get('testing_pd_per_app')} PD", "execute")
    if waves:
        _add("Wave cutover support", waves * e.get("cutover_pd_per_wave", 0),
             f"{waves} waves x {e.get('cutover_pd_per_wave')} PD", "cutover")
    _add("Hypercare", e.get("hypercare_pd_per_month", 0) * e.get("hypercare_months", 0),
         f"{e.get('hypercare_pd_per_month')} PD/month x {e.get('hypercare_months')} months",
         "hypercare")

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
    out = {
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

    loading = _resource_loading(lines, pm, gov, contingency, schedule,
                               int(e.get("working_days_per_month", 21) or 21))
    if loading:
        out["resource_loading"] = loading
    return out


# --------------------------------------------------------------------------
# E6.2 resource loading — spread the workstream PD across the programme calendar
# --------------------------------------------------------------------------
def _d(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _months(start: date, end: date) -> list[tuple[date, date, str]]:
    """[(month_start, next_month_start, 'YYYY-MM'), …] covering [start, end]."""
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        ms = date(y, m, 1)
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((ms, date(y2, m2, 1), f"{y:04d}-{m:02d}"))
        y, m = y2, m2
    return out


def _overlap_days(w0: date, w1: date, m0: date, m1: date) -> int:
    lo, hi = max(w0, m0), min(w1, m1)
    return max(0, (hi - lo).days)


def _spread(pd: float, w0: date, w1: date, buckets: dict, months: list) -> None:
    """Distribute `pd` over [w0, w1) proportional to each month's day-overlap."""
    if pd <= 0 or w1 <= w0:
        return
    weights = [(_overlap_days(w0, w1, m0, m1), key) for m0, m1, key in months]
    total = sum(w for w, _ in weights)
    if total <= 0:
        return
    for w, key in weights:
        if w:
            buckets[key] = buckets.get(key, 0.0) + pd * w / total


def _resource_loading(lines: list[dict], pm: float, gov: float, contingency: float,
                      schedule: dict | None, wd_per_month: int) -> dict | None:
    if not schedule:
        return None
    start, end = _d(schedule.get("start")), _d(schedule.get("end"))
    if not (start and end and end > start):
        return None
    wave_ready = _d(schedule.get("wave_execution_start")) or start
    swaves = list(schedule.get("waves", []) or [])

    months = _months(start, end)
    by_phase: dict[str, dict] = {}       # workstream label -> {month: pd}

    def _bucket(label):
        return by_phase.setdefault(label, {})

    # mobilise-phase work: programme start -> first wave execution
    for ln in lines:
        if ln["phase"] == "mobilise":
            _spread(ln["pd"], start, wave_ready, _bucket(ln["workstream"]), months)

    total_srv = sum(int(w.get("servers") or 0) for w in swaves) or 1
    last_soak = max((_d(w.get("soak_end")) for w in swaves), default=end) or end

    for ln in lines:
        if ln["phase"] not in ("execute", "cutover"):
            continue
        b = _bucket(ln["workstream"])
        if not swaves:
            _spread(ln["pd"], wave_ready, last_soak, b, months)
            continue
        for w in swaves:
            srv = int(w.get("servers") or 0)
            share = ln["pd"] * (srv / total_srv if total_srv else 1.0 / len(swaves))
            if ln["phase"] == "cutover":
                gl = _d(w.get("go_live")) or wave_ready
                _spread(share, gl - timedelta(weeks=1), gl + timedelta(weeks=1), b, months)
            else:
                _spread(share, _d(w.get("exec_start")) or wave_ready,
                        _d(w.get("soak_end")) or last_soak, b, months)

    for ln in lines:
        if ln["phase"] == "hypercare":
            _spread(ln["pd"], last_soak, end, _bucket(ln["workstream"]), months)

    # PM / governance / contingency — flat across the whole programme
    for label, pd in (("Project management", pm), ("Governance & assurance", gov),
                      ("Contingency", contingency)):
        if pd:
            _spread(pd, start, end, _bucket(label), months)

    curve = []
    for m0, m1, key in months:
        bd = {label: round(mp[key], 1) for label, mp in by_phase.items() if mp.get(key, 0) > 0.05}
        mpd = round(sum(bd.values()), 1)
        curve.append({"month": key, "pd": mpd,
                      "fte": round(mpd / wd_per_month, 2) if wd_per_month else None,
                      "by_workstream": dict(sorted(bd.items(), key=lambda kv: -kv[1]))})

    ftes = [c["fte"] for c in curve if c["fte"] is not None]
    peak = max(ftes) if ftes else None
    active = [f for f in ftes if f > 0]
    peak_month = next((c["month"] for c in curve if c["fte"] == peak), None) if peak else None
    return {
        "period": "month",
        "working_days_per_month": wd_per_month,
        "months": len(months),
        "curve": curve,
        "peak_fte": peak,
        "peak_month": peak_month,
        "avg_fte": round(sum(active) / len(active), 2) if active else None,
        "basis": (f"workstream person-days spread across the E4.3 schedule "
                  f"({start} … {end}); execution weighted by servers/wave; "
                  f"PM + governance + contingency level-loaded; FTE = PD ÷ {wd_per_month} working days/month"),
    }
