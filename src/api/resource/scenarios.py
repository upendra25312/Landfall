"""
Resource Scenarios Generator (PRD E15C.7).

Generates Conservative, Expected, and Accelerated resource scenarios with explicit mathematical
assumptions governing throughput, duration, peak FTE, total person-days, and contingency.
"""
from __future__ import annotations

import copy
from typing import Any

from cost.config import load_config
from resource.engine import derive_resource_demand


def generate_resource_scenarios(
    server_count: int,
    app_count: int,
    dispositions: list[dict] | None = None,
    dq_confidence: str = "Medium",
    spokes: int = 0,
    regulated: bool = False,
    waves: int = 0,
    schedule: dict | None = None,
    wave_plan: dict | None = None,
    engagement_id: str = "_default_/_default_",
    cfg: dict | None = None,
) -> dict[str, Any]:
    """
    Generates three deterministic scenarios: Conservative, Expected, Accelerated.
    All deltas derive from explicit parameters:
      - Throughput (servers / week)
      - Parallel execution lanes
      - Wave prep & soak durations
      - Contingency rate
    """
    base_cfg = cfg or load_config()

    # 1. Expected Scenario (baseline)
    expected_cfg = copy.deepcopy(base_cfg)
    expected_demand = derive_resource_demand(
        server_count=server_count,
        app_count=app_count,
        dispositions=dispositions,
        dq_confidence=dq_confidence,
        spokes=spokes,
        regulated=regulated,
        waves=waves,
        schedule=schedule,
        wave_plan=wave_plan,
        engagement_id=engagement_id,
        cfg=expected_cfg,
    )

    # 2. Conservative Scenario (Low velocity, extended soak, higher contingency, single lane)
    conservative_cfg = copy.deepcopy(base_cfg)
    sched_c = conservative_cfg.setdefault("schedule", {})
    base_tput = float(sched_c.get("throughput_servers_per_week", 12) or 12)
    sched_c["throughput_servers_per_week"] = max(4.0, round(base_tput * 0.67))  # e.g. 8 srv/wk
    sched_c["wave_prep_weeks"] = int(sched_c.get("wave_prep_weeks", 2) or 2) + 1
    sched_c["wave_soak_weeks"] = int(sched_c.get("wave_soak_weeks", 1) or 1) + 1
    sched_c["parallel_waves"] = 1
    conservative_cfg.setdefault("effort", {})["contingency_pct"] = 20  # High safety buffer

    # Re-calculate schedule for conservative if schedule was present
    cons_schedule = None
    if schedule:
        from waves.schedule import build_schedule
        if wave_plan:
            cons_schedule = build_schedule(wave_plan, cfg=conservative_cfg, start_date=schedule.get("start"))

    conservative_demand = derive_resource_demand(
        server_count=server_count,
        app_count=app_count,
        dispositions=dispositions,
        dq_confidence=dq_confidence,
        spokes=spokes,
        regulated=regulated,
        waves=waves,
        schedule=cons_schedule,
        wave_plan=wave_plan,
        engagement_id=engagement_id,
        cfg=conservative_cfg,
    )

    # 3. Accelerated Scenario (High velocity, parallel lanes, streamlined prep/soak, lower contingency)
    accelerated_cfg = copy.deepcopy(base_cfg)
    sched_a = accelerated_cfg.setdefault("schedule", {})
    sched_a["throughput_servers_per_week"] = round(base_tput * 2.0)  # e.g. 24 srv/wk
    sched_a["wave_prep_weeks"] = max(1, int(sched_a.get("wave_prep_weeks", 2) or 2) - 1)
    sched_a["wave_soak_weeks"] = 1
    sched_a["parallel_waves"] = max(2, int(sched_a.get("parallel_waves", 1) or 1) + 1)
    accelerated_cfg.setdefault("effort", {})["contingency_pct"] = 8   # Highly automated factory

    accel_schedule = None
    if schedule:
        from waves.schedule import build_schedule
        if wave_plan:
            accel_schedule = build_schedule(wave_plan, cfg=accelerated_cfg, start_date=schedule.get("start"))

    accelerated_demand = derive_resource_demand(
        server_count=server_count,
        app_count=app_count,
        dispositions=dispositions,
        dq_confidence=dq_confidence,
        spokes=spokes,
        regulated=regulated,
        waves=waves,
        schedule=accel_schedule,
        wave_plan=wave_plan,
        engagement_id=engagement_id,
        cfg=accelerated_cfg,
    )

    def _scenario_summary(name: str, d: dict, tput: float, lanes: int, cont: int, desc: str) -> dict[str, Any]:
        tot = d["totals"]
        return {
            "scenario": name,
            "description": desc,
            "assumptions": {
                "throughput_servers_per_week": tput,
                "parallel_waves": lanes,
                "contingency_pct": cont,
            },
            "duration_months": tot["total_months"],
            "person_days": tot["total_person_days"],
            "total_hours": tot["total_hours"],
            "peak_fte": tot["peak_fte"],
            "peak_month": tot["peak_month"],
            "avg_fte": tot["avg_fte"],
            "demand": d,
        }

    scenarios = {
        "conservative": _scenario_summary(
            "Conservative",
            conservative_demand,
            sched_c["throughput_servers_per_week"],
            sched_c["parallel_waves"],
            conservative_cfg["effort"]["contingency_pct"],
            "Risk-averse pace, single-lane execution, extended soak windows, 20% contingency buffer."
        ),
        "expected": _scenario_summary(
            "Expected",
            expected_demand,
            base_tput,
            base_cfg.get("schedule", {}).get("parallel_waves", 1),
            expected_demand["totals"].get("contingency_pct") or base_cfg.get("effort", {}).get("contingency_by_confidence", {}).get(dq_confidence, 12),
            "Balanced migration velocity, standard prep/soak intervals, baseline contingency."
        ),
        "accelerated": _scenario_summary(
            "Accelerated",
            accelerated_demand,
            sched_a["throughput_servers_per_week"],
            sched_a["parallel_waves"],
            accelerated_cfg["effort"]["contingency_pct"],
            "High-throughput parallel migration lanes, automated factory tooling, condensed 8% contingency."
        ),
    }

    comparison_table = [
        {
            "scenario": s["scenario"],
            "duration_months": s["duration_months"],
            "peak_fte": s["peak_fte"],
            "avg_fte": s["avg_fte"],
            "person_days": s["person_days"],
            "throughput_wk": s["assumptions"]["throughput_servers_per_week"],
            "contingency_pct": s["assumptions"]["contingency_pct"],
        }
        for s in scenarios.values()
    ]

    return {
        "scenarios": scenarios,
        "comparison": comparison_table,
        "default": "expected",
    }
