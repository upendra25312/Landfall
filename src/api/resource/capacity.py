"""
Capacity, Constraint Feedback & Skill-Gap Analysis (PRD E15C.1, E15C.8, E15C.11, E15C.12, E15C.13).

Strict separation of Demand (calculated by Landfall) vs Capacity (user-supplied).
If capacity is unsupplied, reports 'NOT PROVIDED' / 'UNKNOWN' with zero hallucination.
Flags 'RESOURCE-CONSTRAINED SCHEDULE' without silently rewriting waves.
"""
from __future__ import annotations

from typing import Any

from resource.model import ROLES_BY_TITLE, STANDARD_ROLES


def analyze_capacity_and_constraints(
    demand: dict[str, Any],
    capacity_input: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Evaluates resource demand against user-supplied capacity.

    Args:
        demand: The output dict from `derive_resource_demand`.
        capacity_input: Optional user-supplied mapping of {role_title: available_fte}.
                        E.g. {"Lead Cloud Architect": 1.0, "Infrastructure / Migration Engineer": 3.0}

    Returns:
        Structured capacity evaluation, constraint warnings, demand vs capacity table,
        capacity heatmap, and skill gap analysis.
    """
    has_capacity_input = bool(capacity_input)
    capacity_map = capacity_input or {}

    role_demand_avg = demand.get("role_demand", {}).get("by_role_avg_fte", {})
    monthly_schedule = demand.get("monthly_schedule", {})
    month_keys = monthly_schedule.get("month_keys", [])
    role_month_fte = monthly_schedule.get("role_month_fte", {})
    wave_loading = demand.get("wave_loading", [])

    # --------------------------------------------------------------------------
    # 1. Demand vs Capacity Summary Table (E15C.12)
    # --------------------------------------------------------------------------
    demand_vs_capacity_rows: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []

    for r_def in STANDARD_ROLES:
        title = r_def.title
        req_avg_fte = role_demand_avg.get(title, 0.0)

        # Peak required FTE across all months for this role
        month_ftes = [role_month_fte.get(title, {}).get(m, 0.0) for m in month_keys]
        peak_req_fte = max(month_ftes) if month_ftes else req_avg_fte

        # Active months when required_fte > 0
        active_months = [m for m in month_keys if role_month_fte.get(title, {}).get(m, 0.0) > 0.05]
        when_needed = f"{active_months[0]} – {active_months[-1]}" if active_months else "None"

        # Affected waves
        affected_waves = [w["wave"] for w in wave_loading if title in w.get("critical_roles", [])] or ["All"]

        if title in capacity_map and capacity_map[title] is not None:
            avail_fte = float(capacity_map[title])
            variance = round(avail_fte - peak_req_fte, 2)
            utilization = round((peak_req_fte / avail_fte) * 100, 1) if avail_fte > 0 else 999.0
            avail_display = avail_fte
            gap_display = variance
            util_display = utilization
        else:
            avail_fte = None
            variance = None
            utilization = None
            avail_display = "NOT PROVIDED"
            gap_display = "UNKNOWN"
            util_display = "UNKNOWN"

        row = {
            "role": title,
            "category": r_def.category,
            "required_avg_fte": req_avg_fte,
            "required_peak_fte": peak_req_fte,
            "available_fte": avail_fte,
            "available_display": avail_display,
            "variance": variance,
            "gap_display": gap_display,
            "utilization_pct": utilization,
            "utilization_display": util_display,
            "when_needed": when_needed,
            "affected_waves": affected_waves,
        }
        demand_vs_capacity_rows.append(row)

    # --------------------------------------------------------------------------
    # 2. Resource-Constraint Detection (E15C.8)
    # --------------------------------------------------------------------------
    is_constrained = False
    bottleneck_months: set[str] = set()

    if has_capacity_input:
        for m_key in month_keys:
            for r_title, avail in capacity_map.items():
                if avail is None:
                    continue
                req = role_month_fte.get(r_title, {}).get(m_key, 0.0)
                if req > float(avail) + 0.01:
                    is_constrained = True
                    bottleneck_months.add(m_key)
                    deficit = round(req - float(avail), 2)
                    constraints.append({
                        "period": m_key,
                        "role": r_title,
                        "required_fte": req,
                        "available_fte": float(avail),
                        "deficit_fte": deficit,
                        "utilization_pct": round((req / float(avail)) * 100, 1) if float(avail) > 0 else 999.0,
                        "recommendation": f"Augment {r_title} by +{deficit} FTE during {m_key} or stagger wave cutovers."
                    })

    status_flag = "RESOURCE-CONSTRAINED SCHEDULE" if is_constrained else (
        "CAPACITY SATISFIED" if has_capacity_input else "CAPACITY NOT PROVIDED"
    )

    # --------------------------------------------------------------------------
    # 3. Capacity Heatmap (E15C.11)
    # --------------------------------------------------------------------------
    heatmap: list[dict[str, Any]] = []
    for r_def in STANDARD_ROLES:
        title = r_def.title
        month_cells = []
        avail = capacity_map.get(title) if has_capacity_input else None

        for m_key in month_keys:
            req = role_month_fte.get(title, {}).get(m_key, 0.0)
            if avail is not None and float(avail) > 0:
                util = round((req / float(avail)) * 100, 1)
                if util > 105.0:
                    status = "OVER_ALLOCATED"
                elif util >= 75.0:
                    status = "OPTIMAL"
                elif util > 0.0:
                    status = "UNDER_ALLOCATED"
                else:
                    status = "IDLE"
            elif avail == 0.0 and req > 0:
                util = 999.0
                status = "OVER_ALLOCATED"
            else:
                util = None
                status = "UNASSESSED" if req > 0 else "IDLE"

            month_cells.append({
                "month": m_key,
                "required_fte": req,
                "available_fte": float(avail) if avail is not None else None,
                "utilization_pct": util,
                "status": status,
            })

        heatmap.append({
            "role": title,
            "category": r_def.category,
            "monthly_utilization": month_cells,
        })

    # --------------------------------------------------------------------------
    # 4. Skill-Gap Analysis (E15C.13)
    # --------------------------------------------------------------------------
    skill_gaps: list[dict[str, Any]] = []
    if has_capacity_input:
        for row in demand_vs_capacity_rows:
            var = row.get("variance")
            if var is not None and var < -0.01:
                r_title = row["role"]
                r_def = ROLES_BY_TITLE.get(r_title)
                skills = r_def.skills if r_def else ["Cloud Migration"]
                primary_skill = skills[0]
                gap_fte = abs(var)

                skill_gaps.append({
                    "role": r_title,
                    "required_skill": primary_skill,
                    "all_skills": skills,
                    "required_fte": row["required_peak_fte"],
                    "available_fte": row["available_fte"],
                    "gap_fte": gap_fte,
                    "when_needed": row["when_needed"],
                    "affected_waves": row["affected_waves"],
                    "recommendation": f"Procure {gap_fte} FTE {r_title} ({primary_skill}) via partner/contractor by {row['when_needed']}."
                })

    return {
        "has_capacity_input": has_capacity_input,
        "status": status_flag,
        "is_constrained": is_constrained,
        "bottleneck_months": sorted(bottleneck_months),
        "constraints_count": len(constraints),
        "constraints": constraints,
        "demand_vs_capacity": demand_vs_capacity_rows,
        "capacity_heatmap": heatmap,
        "skill_gaps": skill_gaps,
        "notice": (
            "No resource capacity was supplied; all available FTE and gaps are UNKNOWN. "
            "To evaluate constraints, provide customer/partner available FTE per role."
            if not has_capacity_input else (
                "Schedule is resource-constrained. Adjust team capacity or wave pacing."
                if is_constrained else "Supplied capacity satisfies peak demand across all project phases."
            )
        ),
    }
