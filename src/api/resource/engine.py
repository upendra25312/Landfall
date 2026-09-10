"""
Deterministic Resource-Demand Engine (PRD E15C.1, E15C.3, E15C.4, E15C.5).

Derives authoritative role-level resource demand from migration scope, 6R disposition mix,
landing zone topology, and wave schedule. Reconciles mathematically with the Phase 1 effort engine.
Never allocates arbitrary FTE or invents named resources.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from cost.config import load_config
from deliverable.effort import estimate_effort
from resource.model import (
    ROLES_BY_TITLE,
    STANDARD_ROLES,
    DeliveryModel,
    PlanningMode,
    ResourceRequirementRow,
)

# Standard role mapping fractions per workstream (sum of weights == 1.0 for each workstream)
WORKSTREAM_ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "Mobilisation & setup": {
        "Migration Programme Manager": 0.50,
        "Lead Cloud Architect": 0.50,
    },
    "Assessment — servers": {
        "Lead Cloud Architect": 0.60,
        "Infrastructure / Migration Engineer": 0.40,
    },
    "Assessment — applications": {
        "Lead Cloud Architect": 0.40,
        "Application Owner / SME": 0.40,
        "Database Administrator (DBA)": 0.20,
    },
    "Landing zone & foundation": {
        "Lead Cloud Architect": 0.40,
        "Network Engineer": 0.35,
        "Security & Compliance Lead": 0.25,
    },
    "Regulated-spoke controls": {
        "Security & Compliance Lead": 0.60,
        "Network Engineer": 0.40,
    },
    "Application execution (by disposition)": {
        "Infrastructure / Migration Engineer": 0.50,
        "Database Administrator (DBA)": 0.30,
        "Application Owner / SME": 0.20,
    },
    "Rehost server execution": {
        "Infrastructure / Migration Engineer": 0.85,
        "Lead Cloud Architect": 0.15,
    },
    "Testing (functional + NFR)": {
        "Test Lead": 0.50,
        "Application Owner / SME": 0.35,
        "Infrastructure / Migration Engineer": 0.15,
    },
    "Wave cutover support": {
        "Infrastructure / Migration Engineer": 0.40,
        "Database Administrator (DBA)": 0.25,
        "Migration Programme Manager": 0.20,
        "Application Owner / SME": 0.15,
    },
    "Hypercare": {
        "Infrastructure / Migration Engineer": 0.50,
        "DevOps & Operations Lead": 0.30,
        "Database Administrator (DBA)": 0.20,
    },
    "Project management": {
        "Migration Programme Manager": 0.85,
        "Change Manager": 0.15,
    },
    "Governance & assurance": {
        "Lead Cloud Architect": 0.40,
        "Security & Compliance Lead": 0.30,
        "FinOps Analyst": 0.30,
    },
    "Contingency": {
        "Infrastructure / Migration Engineer": 0.40,
        "Database Administrator (DBA)": 0.20,
        "Lead Cloud Architect": 0.20,
        "Migration Programme Manager": 0.10,
        "Security & Compliance Lead": 0.10,
    },
}

# Mapping of workstream to MEG lifecycle phase
WORKSTREAM_TO_MEG_PHASE: dict[str, str] = {
    "Mobilisation & setup": "Strategy",
    "Assessment — servers": "Plan",
    "Assessment — applications": "Plan",
    "Landing zone & foundation": "Ready",
    "Regulated-spoke controls": "Ready",
    "Application execution (by disposition)": "Adopt",
    "Rehost server execution": "Adopt",
    "Testing (functional + NFR)": "Adopt",
    "Wave cutover support": "Adopt",
    "Hypercare": "Manage",
    "Project management": "Govern",
    "Governance & assurance": "Govern",
    "Contingency": "Govern",
}


def _d(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _months_between(start: date, end: date) -> list[tuple[date, date, str]]:
    """Generates monthly intervals covering [start, end]."""
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        ms = date(y, m, 1)
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((ms, date(y2, m2, 1), f"{y:04d}-{m:02d}"))
        y, m = y2, m2
    return out


def derive_resource_demand(
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
    planning_mode: PlanningMode = PlanningMode.ROLE_BASED,
) -> dict[str, Any]:
    """
    Derives deterministic resource demand across roles, phases, waves, and time periods.
    Guarantees 100% mathematical reconciliation with `deliverable.effort.estimate_effort`.
    """
    cfg = cfg or load_config()
    effort_result = estimate_effort(
        server_count=server_count,
        app_count=app_count,
        dispositions=dispositions,
        dq_confidence=dq_confidence,
        spokes=spokes,
        regulated=regulated,
        waves=waves,
        schedule=schedule,
        cfg=cfg,
    )

    wd_per_month = int(cfg.get("effort", {}).get("working_days_per_month", 21) or 21)
    hours_per_day = float(cfg.get("effort", {}).get("hours_per_day", 8.0) or 8.0)

    # Workstream PD items from effort_result
    workstream_pds: dict[str, float] = {}
    for item in effort_result.get("workstreams", []):
        workstream_pds[item["workstream"]] = item["pd"]

    pm_pd = effort_result.get("pm_pd", 0.0)
    gov_pd = effort_result.get("governance_pd", 0.0)
    cont_pd = effort_result.get("contingency_pd", 0.0)
    total_eac_pd = effort_result.get("estimate_at_completion_pd", 0.0)

    workstream_pds["Project management"] = pm_pd
    workstream_pds["Governance & assurance"] = gov_pd
    workstream_pds["Contingency"] = cont_pd

    # Derive role-level total PD by applying weights to each workstream
    role_total_pd: dict[str, float] = {r.title: 0.0 for r in STANDARD_ROLES}
    role_workstream_pd: dict[str, dict[str, float]] = {r.title: {} for r in STANDARD_ROLES}

    for ws_name, pd in workstream_pds.items():
        weights = WORKSTREAM_ROLE_WEIGHTS.get(ws_name, {"Infrastructure / Migration Engineer": 1.0})
        for role_title, w in weights.items():
            if role_title not in role_total_pd:
                role_total_pd[role_title] = 0.0
                role_workstream_pd[role_title] = {}
            allocated = round(pd * w, 2)
            role_total_pd[role_title] = round(role_total_pd[role_title] + allocated, 2)
            role_workstream_pd[role_title][ws_name] = allocated

    # Adjust rounding residual so sum of role PD matches total_eac_pd exactly
    sum_roles = sum(role_total_pd.values())
    residual = round(total_eac_pd - sum_roles, 2)
    if abs(residual) > 0.001 and "Infrastructure / Migration Engineer" in role_total_pd:
        role_total_pd["Infrastructure / Migration Engineer"] = round(
            role_total_pd["Infrastructure / Migration Engineer"] + residual, 2
        )

    # --------------------------------------------------------------------------
    # Time Distribution & Calendars (E15C.5)
    # --------------------------------------------------------------------------
    has_dated_schedule = False
    start_date: date | None = None
    end_date: date | None = None
    month_keys: list[str] = []
    month_intervals: list[tuple[date, date, str]] = []

    if schedule:
        start_date = _d(schedule.get("start"))
        end_date = _d(schedule.get("end"))
        if start_date and end_date and end_date > start_date:
            has_dated_schedule = True
            month_intervals = _months_between(start_date, end_date)
            month_keys = [k for _, _, k in month_intervals]

    if not has_dated_schedule:
        # Relative calendar: Month 1, Month 2, ... based on estimated total duration
        total_weeks = 24  # default ~6 months
        if schedule and schedule.get("total_weeks"):
            total_weeks = max(4, int(round(schedule.get("total_weeks"))))
        months_count = max(1, (total_weeks + 3) // 4)
        month_keys = [f"Month {m}" for m in range(1, months_count + 1)]

    # Distribute workstream PD across months using schedule timing or uniform relative distribution
    # workstream -> {month_key: pd}
    ws_month_pd: dict[str, dict[str, float]] = {ws: {m: 0.0 for m in month_keys} for ws in workstream_pds}

    rl = effort_result.get("resource_loading")
    if rl and has_dated_schedule:
        # Use existing E6.2 resource-loading curve workstream spreads
        for curve_point in rl.get("curve", []):
            m_key = curve_point["month"]
            if m_key in month_keys:
                by_ws = curve_point.get("by_workstream", {})
                for ws, ws_pd in by_ws.items():
                    if ws in ws_month_pd:
                        ws_month_pd[ws][m_key] = ws_pd
    else:
        # Deterministic relative distribution across relative months
        total_months = len(month_keys)
        for ws, pd in workstream_pds.items():
            phase = WORKSTREAM_TO_MEG_PHASE.get(ws, "Adopt")
            if total_months == 1:
                ws_month_pd[ws][month_keys[0]] = pd
                continue

            if phase in ("Strategy", "Plan"):
                # Early months (first 25-33% of project)
                span = max(1, total_months // 3)
                share = round(pd / span, 2)
                for i in range(span):
                    ws_month_pd[ws][month_keys[i]] = share
            elif phase == "Ready":
                # First half
                start_m = min(1, total_months - 1)
                span = max(1, total_months // 2)
                share = round(pd / span, 2)
                for i in range(start_m, min(total_months, start_m + span)):
                    ws_month_pd[ws][month_keys[i]] = share
            elif phase == "Adopt":
                # Mid to late months
                start_m = min(1, total_months - 1)
                end_m = max(start_m + 1, total_months - 1)
                span = max(1, end_m - start_m)
                share = round(pd / span, 2)
                for i in range(start_m, end_m):
                    ws_month_pd[ws][month_keys[i]] = share
            elif phase == "Manage":
                # Last 25%
                span = max(1, total_months // 4)
                start_m = max(0, total_months - span)
                share = round(pd / span, 2)
                for i in range(start_m, total_months):
                    ws_month_pd[ws][month_keys[i]] = share
            else:  # Govern / flat uplifts (PM, Governance, Contingency)
                share = round(pd / total_months, 2)
                for m in month_keys:
                    ws_month_pd[ws][m] = share

    # Compute role x month PD and required FTE
    # role -> {month_key: pd}
    role_month_pd: dict[str, dict[str, float]] = {r.title: {m: 0.0 for m in month_keys} for r in STANDARD_ROLES}
    role_month_fte: dict[str, dict[str, float]] = {r.title: {m: 0.0 for m in month_keys} for r in STANDARD_ROLES}

    for ws, m_dist in ws_month_pd.items():
        weights = WORKSTREAM_ROLE_WEIGHTS.get(ws, {"Infrastructure / Migration Engineer": 1.0})
        for m_key, pd in m_dist.items():
            for role_title, w in weights.items():
                if role_title in role_month_pd:
                    alloc = round(pd * w, 2)
                    role_month_pd[role_title][m_key] = round(role_month_pd[role_title][m_key] + alloc, 2)

    for role_title in role_month_pd:
        for m_key, pd in role_month_pd[role_title].items():
            fte = round(pd / wd_per_month, 2) if wd_per_month else 0.0
            role_month_fte[role_title][m_key] = fte

    # Monthly total FTE across all roles
    monthly_totals: list[dict[str, Any]] = []
    all_ftes: list[float] = []
    for m_key in month_keys:
        tot_pd = round(sum(role_month_pd[r][m_key] for r in role_month_pd), 1)
        tot_fte = round(sum(role_month_fte[r][m_key] for r in role_month_fte), 2)
        all_ftes.append(tot_fte)
        monthly_totals.append({
            "month": m_key,
            "total_pd": tot_pd,
            "total_fte": tot_fte,
            "by_role_fte": {r: role_month_fte[r][m_key] for r in role_month_fte if role_month_fte[r][m_key] > 0}
        })

    peak_fte = max(all_ftes) if all_ftes else 0.0
    active_ftes = [f for f in all_ftes if f > 0]
    avg_fte = round(sum(active_ftes) / len(active_ftes), 2) if active_ftes else 0.0
    peak_month = next((m["month"] for m in monthly_totals if m["total_fte"] == peak_fte), None)

    # --------------------------------------------------------------------------
    # Wave Loading Breakdown (E15C.4 / E15C.8)
    # --------------------------------------------------------------------------
    wave_loading: list[dict[str, Any]] = []
    swaves = list(wave_plan.get("waves", []) if wave_plan else (schedule.get("waves", []) if schedule else []))
    total_srv = sum(int(w.get("servers") or w.get("server_count") or 0) for w in swaves) or server_count or 1

    for w_idx, w in enumerate(swaves, 1):
        w_name = str(w.get("wave") or f"Wave {w_idx}")
        w_srv = int(w.get("servers") or w.get("server_count") or 0)
        w_apps = int(w.get("apps") or w.get("app_count") or 0)
        w_ratio = (w_srv / total_srv) if total_srv else (1.0 / len(swaves))

        # Adopt workstream PD allocated to this wave
        adopt_pd = (
            workstream_pds.get("Application execution (by disposition)", 0.0) +
            workstream_pds.get("Rehost server execution", 0.0) +
            workstream_pds.get("Testing (functional + NFR)", 0.0) +
            workstream_pds.get("Wave cutover support", 0.0)
        ) * w_ratio

        wave_loading.append({
            "wave": w_name,
            "kind": w.get("kind", "app"),
            "servers": w_srv,
            "apps": w_apps,
            "pd": round(adopt_pd, 1),
            "share_pct": round(w_ratio * 100, 1),
            "critical_roles": ["Infrastructure / Migration Engineer", "Database Administrator (DBA)", "Application Owner / SME"]
        })

    # --------------------------------------------------------------------------
    # Role x Phase Matrix (E15C.4 / E15C.9)
    # --------------------------------------------------------------------------
    phases = ["Strategy", "Plan", "Ready", "Adopt", "Govern", "Manage"]
    role_phase_pd: dict[str, dict[str, float]] = {r.title: {p: 0.0 for p in phases} for r in STANDARD_ROLES}

    for ws, pd in workstream_pds.items():
        phase = WORKSTREAM_TO_MEG_PHASE.get(ws, "Govern")
        weights = WORKSTREAM_ROLE_WEIGHTS.get(ws, {"Infrastructure / Migration Engineer": 1.0})
        for role_title, w in weights.items():
            if role_title in role_phase_pd and phase in role_phase_pd[role_title]:
                role_phase_pd[role_title][phase] = round(role_phase_pd[role_title][phase] + pd * w, 1)

    # --------------------------------------------------------------------------
    # Structured Requirement Rows Generation (E15C.3)
    # --------------------------------------------------------------------------
    requirement_rows: list[dict[str, Any]] = []
    for ws_name, pd in workstream_pds.items():
        if pd <= 0.01:
            continue
        phase = WORKSTREAM_TO_MEG_PHASE.get(ws_name, "Govern")
        weights = WORKSTREAM_ROLE_WEIGHTS.get(ws_name, {"Infrastructure / Migration Engineer": 1.0})

        for role_title, w in weights.items():
            role_pd = round(pd * w, 2)
            if role_pd <= 0.01:
                continue
            r_def = ROLES_BY_TITLE.get(role_title)
            primary_skill = r_def.skills[0] if r_def and r_def.skills else "Migration Delivery"
            deliv_model = r_def.default_delivery_model.value if r_def else DeliveryModel.ONSHORE.value

            hours = round(role_pd * hours_per_day, 1)
            req_fte = round(role_pd / (wd_per_month * (len(month_keys) or 1)), 2)

            row = ResourceRequirementRow(
                engagement=engagement_id,
                workstream=ws_name,
                phase=phase,
                wave="All" if phase in ("Strategy", "Govern", "Manage") else "Wave Pipeline",
                activity=f"Execute {ws_name.lower()} deliverable",
                role=role_title,
                skill=primary_skill,
                delivery_location="Remote / Hybrid",
                delivery_model=deliv_model,
                start_date=month_keys[0] if month_keys else "Month 1",
                end_date=month_keys[-1] if month_keys else "Month N",
                effort_hours=hours,
                working_days=role_pd,
                hours_per_day=hours_per_day,
                required_fte=req_fte,
                available_fte=None,       # Authoritative: capacity ONLY from user input
                utilization_pct=None,     # Authoritative: UNKNOWN when capacity unsupplied
                rate=None,                # Rate configured separately in commercial module
                cost=None,
                dependency="Preceding lifecycle phase signoff",
                notes=f"Derived deterministically from {server_count} servers, {app_count} apps, {dq_confidence} DQ",
                confidence=dq_confidence,
                source="Landfall Deterministic Engine (E15C.4)",
            )
            requirement_rows.append(row.to_dict())

    return {
        "planning_mode": planning_mode.value,
        "engagement_id": engagement_id,
        "parameters": {
            "server_count": server_count,
            "app_count": app_count,
            "spokes": spokes,
            "regulated": regulated,
            "waves": len(swaves) if swaves else waves,
            "dq_confidence": dq_confidence,
            "working_days_per_month": wd_per_month,
            "hours_per_day": hours_per_day,
        },
        "totals": {
            "delivery_subtotal_pd": effort_result.get("delivery_subtotal_pd", 0.0),
            "pm_pd": pm_pd,
            "governance_pd": gov_pd,
            "contingency_pd": cont_pd,
            "total_person_days": total_eac_pd,
            "total_hours": round(total_eac_pd * hours_per_day, 1),
            "peak_fte": peak_fte,
            "peak_month": peak_month,
            "avg_fte": avg_fte,
            "total_months": len(month_keys),
        },
        "role_demand": {
            "by_role_pd": role_total_pd,
            "by_role_hours": {r: round(pd * hours_per_day, 1) for r, pd in role_total_pd.items()},
            "by_role_avg_fte": {r: round(pd / (wd_per_month * len(month_keys)), 2) for r, pd in role_total_pd.items()} if month_keys else {},
        },
        "monthly_schedule": {
            "has_dated_schedule": has_dated_schedule,
            "month_keys": month_keys,
            "role_month_pd": role_month_pd,
            "role_month_fte": role_month_fte,
            "monthly_totals": monthly_totals,
        },
        "wave_loading": wave_loading,
        "role_phase_matrix": role_phase_pd,
        "requirements": requirement_rows,
        "reconciliation": {
            "effort_at_completion_pd": total_eac_pd,
            "sum_role_pd": round(sum(role_total_pd.values()), 2),
            "variance": round(total_eac_pd - sum(role_total_pd.values()), 4),
            "reconciled": abs(total_eac_pd - sum(role_total_pd.values())) < 0.01,
        },
    }
