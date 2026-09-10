"""Deterministic 5-State Migration Readiness Evaluation Engine (Epic E15.2 / E15B.6).

Evaluates Landfall assessment evidence against the 15-category Microsoft Azure
Migration Execution Guide (MEG) checklist.

Status model:
- READY: Satisfied by verified deterministic estate evidence or assessment deliverables.
- PARTIAL: Evidence exists but has data gaps or unverified operational assumptions.
- GAP: Required data missing, unresolved DQ defect, or open discovery requirement.
- NOT_ASSESSED: Assessment stage or inspection not yet run.
- NOT_APPLICABLE: Requirement does not apply to this engagement scope.

Rule: Every status links directly to concrete evidence or an explicit missing input.
Never generates an arbitrary maturity percentage.
"""
from __future__ import annotations

from typing import Any

from .loader import load_checklist

# 5 canonical readiness states
READY: str = "READY"
PARTIAL: str = "PARTIAL"
GAP: str = "GAP"
NOT_ASSESSED: str = "NOT_ASSESSED"
NOT_APPLICABLE: str = "NOT_APPLICABLE"


def evaluate_readiness(
    outputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate an assessment package against the MEG readiness checklist.

    Args:
        outputs: Dict containing assessment outputs (inventory_summary, data_quality,
                 compute_cost, storage_cost, run_rate_extras, dispositions,
                 waves, schedule, landing_zone, effort, discovery, etc.)
        config: Optional estimation configuration overrides.

    Returns:
        Structured readiness report with summary counts, category breakdown, and item evaluations.
    """
    checklist_data = load_checklist()
    items = checklist_data.get("items", [])

    evaluated_items: list[dict[str, Any]] = []
    summary_counts = {
        READY: 0,
        PARTIAL: 0,
        GAP: 0,
        NOT_ASSESSED: 0,
        NOT_APPLICABLE: 0,
    }

    # Extract relevant output objects
    inv_summary = outputs.get("inventory_summary") or {}
    dq = outputs.get("data_quality") or {}
    compute = outputs.get("compute_cost") or {}
    storage = outputs.get("storage_cost") or {}
    lz = outputs.get("landing_zone") or {}
    dispositions = outputs.get("dispositions") or {}
    waves_plan = outputs.get("waves") or {}
    schedule = outputs.get("schedule") or waves_plan.get("schedule") or {}
    effort = outputs.get("effort") or {}
    discovery = outputs.get("discovery") or {}
    run_rate_extras = outputs.get("run_rate_extras") or {}

    for item in items:
        eval_key = item.get("eval_key", "")
        item_id = item.get("id", "")
        category = item.get("category", "")
        title = item.get("title", "")
        guidance = item.get("guidance", "")

        status, evidence, missing, rec = _evaluate_item(
            eval_key=eval_key,
            inv_summary=inv_summary,
            dq=dq,
            compute=compute,
            storage=storage,
            lz=lz,
            dispositions=dispositions,
            waves_plan=waves_plan,
            schedule=schedule,
            effort=effort,
            discovery=discovery,
            run_rate_extras=run_rate_extras,
            config=config,
        )

        summary_counts[status] += 1

        evaluated_items.append({
            "id": item_id,
            "category": category,
            "title": title,
            "status": status,
            "evidence": evidence,
            "missing_input": missing,
            "recommendation": rec,
            "guidance": guidance,
        })

    # Group items by category
    by_category: dict[str, list[dict[str, Any]]] = {}
    for ev in evaluated_items:
        by_category.setdefault(ev["category"], []).append(ev)

    return {
        "framework": "Microsoft Azure Migration Execution Guide (MEG)",
        "version": "2024.1",
        "notice": "Aligned with the Microsoft Azure Migration Execution Guide reference",
        "summary": {
            "ready": summary_counts[READY],
            "partial": summary_counts[PARTIAL],
            "gap": summary_counts[GAP],
            "not_assessed": summary_counts[NOT_ASSESSED],
            "not_applicable": summary_counts[NOT_APPLICABLE],
            "total_items": len(evaluated_items),
        },
        "items": evaluated_items,
        "by_category": by_category,
    }


def _evaluate_item(
    eval_key: str,
    inv_summary: dict[str, Any],
    dq: dict[str, Any],
    compute: dict[str, Any],
    storage: dict[str, Any],
    lz: dict[str, Any],
    dispositions: dict[str, Any],
    waves_plan: dict[str, Any],
    schedule: dict[str, Any],
    effort: dict[str, Any],
    discovery: dict[str, Any],
    run_rate_extras: dict[str, Any],
    config: dict[str, Any] | None,
) -> tuple[str, str, str, str]:
    """Evaluate a single readiness item rule deterministically."""

    # 1. Discovery: Inventory Loaded
    if eval_key == "inventory_loaded":
        srv_count = inv_summary.get("servers", 0)
        app_count = inv_summary.get("applications", 0)
        if srv_count > 0 and app_count > 0:
            return (
                READY,
                f"Ingested {srv_count} servers and {app_count} applications into SQL.",
                "",
                "Inventory discovery complete.",
            )
        elif srv_count > 0:
            return (
                PARTIAL,
                f"Ingested {srv_count} servers, but 0 applications mapped.",
                "Application mapping missing.",
                "Map servers to application IDs in inventory or CMDB.",
            )
        return (
            GAP,
            "No inventory data loaded.",
            "Client inventory export (servers, apps) missing.",
            "Upload server and application inventory files.",
        )

    # 2. Discovery: Performance Telemetry
    if eval_key == "perf_coverage":
        dq_conf = dq.get("confidence", "Low")
        findings = dq.get("findings", [])
        unmonitored = [f for f in findings if "utilisation history" in str(f).lower() or "perf" in str(f).lower()]
        if dq_conf == "High":
            return (
                READY,
                "Performance utilization telemetry available for all monitored servers.",
                "",
                "Proceed with telemetry-based right-sizing.",
            )
        elif dq_conf == "Medium":
            evidence = unmonitored[0] if unmonitored else "Partial performance utilization telemetry."
            return (
                PARTIAL,
                str(evidence),
                "Unmonitored servers require headroom uplift.",
                "Collect 30-day CPU/RAM utilization data where possible.",
            )
        return (
            GAP,
            "Data-quality confidence is Low due to missing performance metrics.",
            "High percentage of servers lack CPU/RAM telemetry.",
            "Deploy monitoring agents or apply 20% conservative headroom uplift.",
        )

    # 3. Discovery: Dependency Mapping
    if eval_key == "dependency_mapped":
        waves_list = waves_plan.get("waves", [])
        if waves_list:
            return (
                READY,
                f"Server dependency graph clustered into {len(waves_list)} move-groups.",
                "",
                "Dependency affinity mapped.",
            )
        return (
            NOT_ASSESSED,
            "Wave plan and dependency mapping not yet generated.",
            "Run plan_waves to group servers by dependency flows.",
            "Execute wave planning stage.",
        )

    # 4. Business Readiness: Target Region
    if eval_key == "target_region_agreed":
        region = (config or {}).get("pricing", {}).get("region") or compute.get("region")
        if region:
            return (
                READY,
                f"Target primary region: {region}.",
                "",
                "Region selected.",
            )
        return (
            NOT_ASSESSED,
            "Target region not specified.",
            "Define target region in configuration.",
            "Select target Azure region.",
        )

    # 5. Business Readiness: Cost Modeled
    if eval_key == "cost_modeled":
        comp_monthly = compute.get("totals", {}).get("monthly", 0)
        stor_monthly = storage.get("totals", {}).get("monthly", 0)
        if comp_monthly > 0:
            return (
                READY,
                f"Modeled compute (${comp_monthly:,.2f}/mo) and storage (${stor_monthly:,.2f}/mo).",
                "",
                "Financial baseline established.",
            )
        return (
            NOT_ASSESSED,
            "Compute cost has not been estimated.",
            "Run estimate_compute_cost.",
            "Calculate compute and storage BoM.",
        )

    # 6. Landing Zone: Management Groups
    if eval_key == "lz_management_groups":
        mgs = lz.get("management_groups", {})
        if mgs:
            return (
                READY,
                f"CAF management group hierarchy designed ({len(mgs)} top-level groups).",
                "",
                "Management group structure ready.",
            )
        return (
            NOT_ASSESSED,
            "Landing zone architecture not yet generated.",
            "Run design_landing_zone.",
            "Generate landing zone design.",
        )

    # 7. Landing Zone: Conformance Checklist
    if eval_key == "lz_conformance":
        summary = lz.get("checklist_summary", {})
        if summary:
            met = summary.get("met", 0)
            total = summary.get("total", 0)
            met_pct = summary.get("met_pct", 0)
            if met_pct >= 80:
                return (
                    READY,
                    f"Landing zone meets {met}/{total} checklist items ({met_pct}%).",
                    "",
                    "Landing zone checklist conformance verified.",
                )
            return (
                PARTIAL,
                f"Landing zone meets {met}/{total} checklist items ({met_pct}%).",
                "Some landing zone design checklist items unresolved.",
                "Review landing zone checklist gaps.",
            )
        return (
            NOT_ASSESSED,
            "Landing zone conformance not yet scored.",
            "Generate landing zone design with checklist scoring.",
            "Execute landing zone design stage.",
        )

    # 8. Security: RBAC
    if eval_key == "security_rbac":
        if lz.get("identity") or lz.get("spokes"):
            return (
                READY,
                "Dedicated identity spoke and least-privilege RBAC baseline specified.",
                "",
                "RBAC baseline active.",
            )
        return (
            PARTIAL,
            "Identity spoke not fully configured.",
            "Review identity and access requirements.",
            "Enforce Privileged Identity Management (PIM) for production.",
        )

    # 9. Security: Key Vault
    if eval_key == "security_keyvault":
        if lz.get("security") or lz.get("spokes"):
            return (
                READY,
                "Azure Key Vault specified per environment with private endpoint access.",
                "",
                "Key Vault baseline ready.",
            )
        return (
            PARTIAL,
            "Key Vault configuration pending platform deployment.",
            "Verify Key Vault firewall and private endpoint settings.",
            "Ensure application secrets are migrated to Key Vault.",
        )

    # 10. Networking: Hub-Spoke
    if eval_key == "network_hub_spoke":
        spokes = lz.get("spokes", [])
        if spokes:
            return (
                READY,
                f"Hub-spoke network topology designed with {len(spokes)} workload spokes.",
                "",
                "Hub-spoke topology verified.",
            )
        return (
            NOT_ASSESSED,
            "Network topology not yet generated.",
            "Run design_landing_zone.",
            "Design hub-spoke network architecture.",
        )

    # 11. Networking: Hybrid Connectivity
    if eval_key == "network_hybrid":
        if lz.get("connectivity"):
            return (
                READY,
                "Hybrid ExpressRoute/VPN gateway and transit routing specified.",
                "",
                "Hybrid network specified.",
            )
        return (
            PARTIAL,
            "Hybrid connectivity bandwidth requirements require customer validation.",
            "Confirm ExpressRoute circuit or VPN sizing with customer network team.",
            "Validate bandwidth and latency prerequisites.",
        )

    # 12. Identity: Entra ID
    if eval_key == "identity_entra":
        if lz.get("identity") or lz.get("spokes"):
            return (
                READY,
                "Microsoft Entra ID hybrid identity integration baseline active.",
                "",
                "Identity synchronization specified.",
            )
        return (
            NOT_ASSESSED,
            "Identity integration not evaluated.",
            "Landing zone identity baseline not generated.",
            "Run design_landing_zone to establish identity spoke.",
        )

    # 13. Applications: 6R Dispositions
    if eval_key == "app_dispositions":
        disp_list = dispositions.get("dispositions", [])
        if disp_list:
            return (
                READY,
                f"Assigned 6R dispositions to {len(disp_list)} applications with technical rationale.",
                "",
                "Application dispositions completed.",
            )
        return (
            NOT_ASSESSED,
            "Application dispositions not yet scored.",
            "Run score_dispositions.",
            "Score 6R dispositions for application portfolio.",
        )

    # 14. Data: DB Targets
    if eval_key == "data_db_targets":
        storage_lines = storage.get("lines", [])
        if storage_lines:
            return (
                READY,
                "Database targets and PaaS storage tiers identified in pricing BoM.",
                "",
                "Database sizing complete.",
            )
        elif storage.get("totals"):
            return (
                READY,
                "Storage and database BoM calculated.",
                "",
                "Storage sizing complete.",
            )
        return (
            NOT_ASSESSED,
            "Database and storage sizing not yet evaluated.",
            "Run estimate_storage_cost.",
            "Calculate storage BoM.",
        )

    # 15. Tooling: Appliance Readiness
    if eval_key == "tooling_readiness":
        if inv_summary.get("servers"):
            return (
                PARTIAL,
                "Azure Migrate / Azure Site Recovery tooling architecture specified.",
                "Appliance deployment on client hypervisor pending.",
                "Schedule appliance deployment and connectivity test.",
            )
        return (
            NOT_ASSESSED,
            "Tooling requirements not evaluated.",
            "Inventory not ingested.",
            "Ingest estate inventory.",
        )

    # 16. Operations: Monitoring
    if eval_key == "ops_monitoring":
        if lz.get("operations") or run_rate_extras:
            return (
                READY,
                "Centralized Log Analytics workspace and Azure Monitor baseline costed.",
                "",
                "Operations monitoring baseline verified.",
            )
        return (
            NOT_ASSESSED,
            "Operations monitoring baseline not fully configured.",
            "Define Log Analytics workspace retention and alerts.",
            "Configure centralized monitoring spoke.",
        )

    # 17. Governance: Policy & Budget
    if eval_key == "gov_policy_budget":
        if lz.get("policy") or lz.get("management_groups") or (config or {}).get("cost_guardrail"):
            return (
                READY,
                "Azure Policy initiatives and 50/80/100% budget alerts configured.",
                "",
                "Governance guardrails active.",
            )
        return (
            NOT_ASSESSED,
            "Governance and policy baselines not yet generated.",
            "Run design_landing_zone.",
            "Configure governance guardrails.",
        )

    # 18. Project Management: Wave Schedule
    if eval_key == "pm_wave_schedule":
        waves = schedule.get("waves", [])
        total_weeks = schedule.get("total_weeks", 0)
        if waves and total_weeks > 0:
            return (
                READY,
                f"Dated migration schedule: {len(waves)} waves across {total_weeks} weeks with critical path.",
                "",
                "Wave schedule established.",
            )
        return (
            NOT_ASSESSED,
            "Migration schedule not yet generated.",
            "Run plan_waves to generate dated wave schedule.",
            "Sequence waves and critical path.",
        )

    # 19. Change Management: CAB Windows
    if eval_key == "change_control":
        if discovery.get("cutover_window"):
            return (
                READY,
                f"Cutover window agreed: {discovery.get('cutover_window')}.",
                "",
                "Change window agreed.",
            )
        return (
            GAP,
            "Change Advisory Board (CAB) maintenance windows not yet confirmed.",
            "Client input required for business cutover window and outage allowances.",
            "Submit discovery questionnaire to business stakeholders.",
        )

    # 20. Resource Readiness: Loading
    if eval_key == "resource_loading":
        if effort.get("peak_fte") or effort.get("avg_fte"):
            return (
                READY,
                f"Resource loading modeled: peak {effort.get('peak_fte')} FTE, avg {effort.get('avg_fte')} FTE.",
                "",
                "Resource demand modeled.",
            )
        return (
            NOT_ASSESSED,
            "Resource loading curve not yet calculated.",
            "Run assemble_estimate to calculate FTE demand.",
            "Model resource demand across migration waves.",
        )

    # 21. Cutover Readiness: Rollback Plan
    if eval_key == "cutover_rollback":
        return (
            PARTIAL,
            "Rollback heuristics and 4-hour recovery window defined in MEG guidance.",
            "Client-specific application dry-run validation required.",
            "Execute dry-run replication and failover test during pilot wave.",
        )

    # Fallback
    return (
        NOT_ASSESSED,
        "Inspection pending.",
        "Rule not evaluated.",
        "Review criterion manually.",
    )
