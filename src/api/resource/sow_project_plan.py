"""
SOW Resource Section & Project Plan Generator (PRD E15C.15, E15C.16).

Generates:
  1. An SOW-ready resource narrative with roles, responsibilities, estimated effort,
     staffing assumptions, customer dependencies, and partner responsibilities.
  2. A 12-column project plan aligned with MEG lifecycle phases and migration waves,
     using dated milestones or relative weeks.
"""
from __future__ import annotations

from typing import Any

from resource.model import STANDARD_ROLES

ROLE_RESPONSIBILITIES: dict[str, str] = {
    "Migration Programme Manager": "Overall migration timeline delivery, status reporting, risk mitigation, and executive escalation.",
    "Lead Cloud Architect": "Target ALZ topology, 6R disposition decisions, technical review board leadership, and pattern signoff.",
    "Infrastructure / Migration Engineer": "Server replication configuration, test failover execution, cutover rehearsals, and cutover synchronization.",
    "Network Engineer": "Hybrid routing, ExpressRoute/VPN, DNS resolution, Azure Firewall rules, and network security group management.",
    "Security & Compliance Lead": "Identity RBAC, Key Vault provisioning, policy enforcement, Defender for Cloud security score, and audit evidence.",
    "Database Administrator (DBA)": "Database migration service setup, schema conversion, data synchronization, and post-cutover data verification.",
    "Application Owner / SME": "Application architecture guidance, user acceptance testing (UAT), cutover signoff, and business sanity testing.",
    "Test Lead": "Test strategy formulation, functional & non-functional test plan execution, defect triage, and dress rehearsal management.",
    "DevOps & Operations Lead": "CI/CD deployment automation, Log Analytics configuration, backup policy attachment, and operations handover.",
    "FinOps Analyst": "Azure cost tracking, reservation recommendations, tagging policy compliance, and post-migration billing reviews.",
    "Change Manager": "Change Advisory Board (CAB) approval submissions, communication blasts, blackout schedule coordination, and user training.",
}

ROLE_CUSTOMER_DEPENDENCIES: dict[str, str] = {
    "Migration Programme Manager": "Access to business stakeholders, project steering committee attendance, and timely escalation resolution.",
    "Lead Cloud Architect": "Access to enterprise architecture guidelines, compliance policies, and existing target landing zone documentation.",
    "Infrastructure / Migration Engineer": "Local admin / root access on source VMs, hypervisor read permissions, and Azure tenant Contributor access.",
    "Network Engineer": "On-premises firewall rule changes, routing changes, and IP subnet reservations provided within SLA.",
    "Security & Compliance Lead": "Security review team engagement, Entra ID Global Admin consent for app registrations, and Key Vault access.",
    "Database Administrator (DBA)": "Source database sa/sysadmin credentials, native backup storage access, and schema DDL scripts.",
    "Application Owner / SME": "Nomination of qualified business testers and prompt execution of UAT scripts during cutover windows.",
    "Test Lead": "Availability of test environments, realistic test data sets, and business user availability for dress rehearsals.",
    "DevOps & Operations Lead": "Access to enterprise monitoring and IT service management (ITSM) ticketing tools for integration.",
    "FinOps Analyst": "Access to Microsoft Cost Management / Billing accounts and enterprise agreement pricing visibility.",
    "Change Manager": "CAB meeting scheduling and executive signoff on planned maintenance windows.",
}


def build_sow_resource_section(
    demand: dict[str, Any],
    commercial: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Generates an SOW-ready resource narrative reconciling to the deterministic effort model.
    """
    totals = demand.get("totals", {})
    role_pds = demand.get("role_demand", {}).get("by_role_pd", {})
    role_hours = demand.get("role_demand", {}).get("by_role_hours", {})
    month_keys = demand.get("monthly_schedule", {}).get("month_keys", [])
    delivery_period = f"{month_keys[0]} – {month_keys[-1]}" if month_keys else "Throughout Engagement"

    roles_summary = []
    for r_def in STANDARD_ROLES:
        title = r_def.title
        pd = role_pds.get(title, 0.0)
        hrs = role_hours.get(title, 0.0)
        roles_summary.append({
            "role": title,
            "category": r_def.category,
            "responsibilities": ROLE_RESPONSIBILITIES.get(title, r_def.description),
            "estimated_pd": pd,
            "estimated_hours": hrs,
            "delivery_period": delivery_period,
            "location": "Remote / Onshore / Nearshore Hybrid",
            "delivery_model": r_def.default_delivery_model.value,
            "customer_dependencies": ROLE_CUSTOMER_DEPENDENCIES.get(title, "Timely SME feedback and access permissions."),
        })

    staffing_assumptions = [
        f"Total migration effort is estimated at {totals.get('total_person_days')} person-days ({totals.get('total_hours')} hours) over {totals.get('total_months')} months.",
        f"Team profile scales to a peak of {totals.get('peak_fte')} FTE in {totals.get('peak_month') or 'Peak Wave'}, averaging {totals.get('avg_fte')} FTE.",
        "Work is performed remotely during standard business hours (8 hours/day, 21 days/month), with planned off-hours cutover support for wave go-lives.",
        "Customer provides dedicated Application Owners / SMEs and Change Management leadership throughout wave execution.",
        "Partner/Consulting provides core engineering, architecture, program management, testing, and DBA expertise.",
    ]

    customer_responsibilities = [
        "Provide dedicated Application SMEs for discovery interviews, disposition signoff, and user acceptance testing (UAT).",
        "Grant necessary administrative privileges on source VMs, virtualization platforms, and target Azure subscriptions within 5 business days of project kickoff.",
        "Submit and champion Change Advisory Board (CAB) tickets for production maintenance windows.",
        "Provision and validate on-premises network routes and firewall rule changes for hybrid connectivity.",
        "Perform timely functional and business sign-off testing within agreed wave soak periods.",
    ]

    partner_responsibilities = [
        "Design and implement the Azure Landing Zone topology per Cloud Adoption Framework (CAF) best practices.",
        "Configure automated replication appliances, migration projects, and test failover infrastructure.",
        "Author and execute cutover runbooks for each scheduled migration wave.",
        "Provide hypercare operational transition and operational handover documentation.",
        "Deliver weekly program status reporting including critical path progress, RAID log, and burn-down charts.",
    ]

    exclusions = [
        "Refactoring or rewriting legacy application code beyond basic configuration updates and connection string changes.",
        "Hardware decommissioning or physical removal of servers from customer data centers.",
        "Third-party software license procurement or renewal costs.",
        "Remediation of pre-existing software bugs or architectural flaws unrelated to cloud migration.",
    ]

    return {
        "delivery_period": delivery_period,
        "total_person_days": totals.get("total_person_days"),
        "total_hours": totals.get("total_hours"),
        "peak_fte": totals.get("peak_fte"),
        "average_fte": totals.get("avg_fte"),
        "roles": roles_summary,
        "staffing_assumptions": staffing_assumptions,
        "customer_responsibilities": customer_responsibilities,
        "partner_responsibilities": partner_responsibilities,
        "exclusions": exclusions,
    }


def build_project_plan(
    demand: dict[str, Any],
    schedule: dict | None = None,
) -> list[dict[str, Any]]:
    """
    Generates a 12-column project plan aligned with MEG lifecycle phases and migration waves (E15C.16).
    Columns: ID, Phase, Workstream, Task, Start, Finish, Duration, Dependency, Owner Role, Wave, Status, Milestone.
    """
    tasks: list[dict[str, Any]] = []
    task_counter = 1

    def _add_task(phase: str, ws: str, task: str, start: str, finish: str, dur_wks: float, dep: str, owner: str, wave: str, is_mstone: bool = False):
        nonlocal task_counter
        tid = f"TSK-{task_counter:03d}"
        task_counter += 1
        tasks.append({
            "id": tid,
            "phase": phase,
            "workstream": ws,
            "task": task,
            "start": start,
            "finish": finish,
            "duration_weeks": round(dur_wks, 1),
            "dependency": dep,
            "owner_role": owner,
            "wave": wave,
            "status": "Planned",
            "milestone": is_mstone,
        })

    has_dates = schedule and schedule.get("start") and schedule.get("end")
    p_start = schedule.get("start") if has_dates else "Week 1"

    # Strategy & Mobilisation Phase
    _add_task("Strategy", "Mobilisation", "Project Kickoff & Team Onboarding", p_start, p_start, 0.0, "None", "Migration Programme Manager", "All", True)
    _add_task("Strategy", "Mobilisation", "Stakeholder Alignment & Governance Setup", p_start, schedule.get("wave_execution_start") if has_dates else "Week 3", 3.0, "Kickoff", "Migration Programme Manager", "All")

    # Plan Phase
    _add_task("Plan", "Assessment", "Server & Workload Inventory Validation", p_start, schedule.get("wave_execution_start") if has_dates else "Week 3", 2.0, "Kickoff", "Lead Cloud Architect", "All")
    _add_task("Plan", "Assessment", "Application Dependency & 6R Disposition Signoff", p_start, schedule.get("wave_execution_start") if has_dates else "Week 3", 3.0, "Inventory", "Lead Cloud Architect", "All")
    _add_task("Plan", "Assessment", "Discovery & Disposition Gate Approval", schedule.get("wave_execution_start") if has_dates else "Week 3", schedule.get("wave_execution_start") if has_dates else "Week 3", 0.0, "Disposition", "Application Owner / SME", "All", True)

    # Ready Phase
    _add_task("Ready", "Landing Zone", "Azure Landing Zone Core Infrastructure Build", p_start, schedule.get("wave_execution_start") if has_dates else "Week 3", 3.0, "Kickoff", "Lead Cloud Architect", "Platform")
    _add_task("Ready", "Landing Zone", "Hybrid Connectivity & Spoke Network Peering", p_start, schedule.get("wave_execution_start") if has_dates else "Week 3", 2.5, "LZ Core", "Network Engineer", "Platform")
    _add_task("Ready", "Landing Zone", "Security Baseline, RBAC & Policy Overlay Validation", p_start, schedule.get("wave_execution_start") if has_dates else "Week 3", 2.0, "Network", "Security & Compliance Lead", "Platform")
    _add_task("Ready", "Landing Zone", "Landing Zone Ready Milestone", schedule.get("wave_execution_start") if has_dates else "Week 3", schedule.get("wave_execution_start") if has_dates else "Week 3", 0.0, "Security", "Lead Cloud Architect", "Platform", True)

    # Adopt Phase (Waves)
    waves = schedule.get("waves", []) if schedule else []
    prev_dep = "LZ Ready"

    if waves:
        for w in waves:
            w_name = str(w.get("wave"))
            w_prep_s = w.get("prep_start", "Week 4")
            w_exec_s = w.get("exec_start", "Week 6")
            w_golive = w.get("go_live", "Week 8")
            w_soak_e = w.get("soak_end", "Week 9")

            _add_task("Adopt", "Wave Execution", f"Wave {w_name} Prep & Runbook Finalisation", w_prep_s, w_exec_s, float(w.get("prep_weeks", 2)), prev_dep, "Infrastructure / Migration Engineer", f"Wave {w_name}")
            _add_task("Adopt", "Wave Execution", f"Wave {w_name} Replication & Test Failovers", w_exec_s, w_golive, float(w.get("exec_weeks", 2)), f"Wave {w_name} Prep", "Infrastructure / Migration Engineer", f"Wave {w_name}")
            _add_task("Adopt", "Wave Cutover", f"Wave {w_name} Production Cutover & DNS Switch", w_golive, w_golive, 0.0, f"Wave {w_name} Replicate", "Migration Programme Manager", f"Wave {w_name}", True)
            _add_task("Adopt", "Testing", f"Wave {w_name} Post-Cutover UAT & Soak", w_golive, w_soak_e, float(w.get("soak_weeks", 1)), f"Wave {w_name} Cutover", "Application Owner / SME", f"Wave {w_name}")
            prev_dep = f"Wave {w_name} Soak"
    else:
        # Generic wave pipeline task if no detailed schedule
        _add_task("Adopt", "Wave Execution", "Migration Wave Execution Pipeline", "Week 4", "Week 20", 16.0, "LZ Ready", "Infrastructure / Migration Engineer", "Wave Pipeline")
        _add_task("Adopt", "Wave Cutover", "Final Wave Production Cutover", "Week 20", "Week 20", 0.0, "Wave Execution", "Migration Programme Manager", "Wave Pipeline", True)
        prev_dep = "Final Wave Cutover"

    # Manage & Govern Phase
    end_date = schedule.get("end") if has_dates else "Week 24"
    _add_task("Manage", "Hypercare", "Production Hypercare & Operational Stability", waves[-1].get("soak_end", "Week 20") if waves else "Week 20", end_date, 4.0, prev_dep, "DevOps & Operations Lead", "All")
    _add_task("Govern", "Governance", "Operational Handoff & Project Close-Out", end_date, end_date, 0.0, "Hypercare", "Migration Programme Manager", "All", True)

    return tasks
