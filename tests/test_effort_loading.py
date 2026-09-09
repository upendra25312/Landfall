"""C29 / E6.2 (full) — estimate_effort resource-loading curve + peak FTE."""
from cost.config import load_config
from deliverable.effort import estimate_effort
from waves.plan import plan_waves


def _cfg(**over):
    return load_config(overrides=over or None)


def _schedule():
    apps = [{"app_id": f"a{i}", "criticality": 3} for i in range(8)]
    servers = [{"server_id": f"s{i}-{j}", "app_id": f"a{i}"} for i in range(8) for j in range(12)]
    return plan_waves(apps, servers, [], _cfg(), start_date="2026-01-05")["schedule"]


def test_no_schedule_still_returns_the_parametric_range():
    r = estimate_effort(96, 8, None, "Medium", spokes=4, waves=3, cfg=_cfg())
    assert r["estimate_at_completion_pd"] > 0
    assert "resource_loading" not in r


def test_schedule_produces_a_monthly_curve_and_peak_fte():
    sched = _schedule()
    r = estimate_effort(96, 8, None, "Medium", spokes=4, waves=len(sched["waves"]),
                        schedule=sched, cfg=_cfg())
    rl = r["resource_loading"]
    assert rl["period"] == "month"
    assert rl["months"] == len(rl["curve"]) >= 3
    assert rl["peak_fte"] >= rl["avg_fte"] > 0
    # the curve's total person-days reconcile with the EAC (within rounding)
    curve_pd = sum(c["pd"] for c in rl["curve"])
    assert abs(curve_pd - r["estimate_at_completion_pd"]) / r["estimate_at_completion_pd"] < 0.05
    # every populated month attributes its FTE to named workstreams
    for c in rl["curve"]:
        if c["pd"] > 0:
            assert c["by_workstream"]
            assert abs(sum(c["by_workstream"].values()) - c["pd"]) < 0.2


def test_peak_month_is_on_the_curve():
    sched = _schedule()
    r = estimate_effort(96, 8, None, "Low", spokes=4, waves=len(sched["waves"]),
                        schedule=sched, cfg=_cfg())
    rl = r["resource_loading"]
    hit = next(c for c in rl["curve"] if c["month"] == rl["peak_month"])
    assert hit["fte"] == rl["peak_fte"]


def test_deterministic():
    sched = _schedule()
    a = estimate_effort(96, 8, None, "Medium", schedule=sched, cfg=_cfg())
    b = estimate_effort(96, 8, None, "Medium", schedule=sched, cfg=_cfg())
    assert a == b
