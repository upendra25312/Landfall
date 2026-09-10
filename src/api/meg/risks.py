"""Deterministic Risk Register Engine (Epic E15.2 / E15B.7).

Derives migration risks deterministically from estate inventory evidence, data-quality
reports, and landing-zone architectural patterns.

Classifications:
- Observed Risk: Factually verified in inventory data (e.g. EOL OS, stale dependencies).
- Derived Risk: Logically derived from architecture choices (e.g. single region, DB replatform).
- Generic MEG Check: Standard baseline governance risks from the MEG reference.
- Architect-Added Risk: Explicit operator or architect findings.

Probability and Impact are strictly governed by configuration rules or explicit inputs;
never guessed or hallucinated by an LLM.
"""
from __future__ import annotations

from typing import Any

from .loader import load_risks


def generate_risk_register(
    outputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate an initial deterministic risk register from assessment evidence.

    Args:
        outputs: Dict containing assessment outputs (inventory_summary, data_quality,
                 dispositions, waves, landing_zone, discovery, etc.)
        config: Optional configuration overrides.

    Returns:
        List of structured risk dictionaries matching E15B.7 column schema.
    """
    risks_def = load_risks()
    rating_matrix = risks_def.get("rating_matrix", {})
    rules = risks_def.get("rules", [])

    dq = outputs.get("data_quality") or {}
    dispositions = outputs.get("dispositions") or {}
    waves = outputs.get("waves") or {}
    lz = outputs.get("landing_zone") or {}
    discovery = outputs.get("discovery") or {}

    register: list[dict[str, Any]] = []

    # 1. Evaluate Rule: RISK-RULE-PERF-GAP (Unmonitored servers)
    findings = dq.get("findings", [])
    perf_gap_findings = [f for f in findings if "utilisation history" in str(f).lower()]
    if perf_gap_findings or dq.get("confidence") in ("Low", "Medium"):
        rule = next((r for r in rules if r["rule_id"] == "RISK-RULE-PERF-GAP"), None)
        if rule:
            evidence = perf_gap_findings[0] if perf_gap_findings else "Data-quality confidence is Medium/Low due to unmonitored servers."
            register.append(_build_risk_entry(rule, str(evidence), rating_matrix))

    # 2. Evaluate Rule: RISK-RULE-EOL-OS (Legacy / EOL operating systems)
    eol_count = 0
    eol_details: list[str] = []
    for app in dispositions.get("dispositions", []):
        app_eol = app.get("eol_servers", 0)
        if app_eol > 0:
            eol_count += app_eol
            eol_details.append(f"{app.get('app_name', app.get('app_id'))}: {app_eol} EOL server(s)")

    if eol_count > 0:
        rule = next((r for r in rules if r["rule_id"] == "RISK-RULE-EOL-OS"), None)
        if rule:
            evidence = f"{eol_count} server(s) running unsupported/EOL OS ({', '.join(eol_details[:3])})."
            register.append(_build_risk_entry(rule, evidence, rating_matrix))

    # 3. Evaluate Rule: RISK-RULE-SINGLE-REGION (Resilience & DR)
    dr_block = lz.get("dr") or {}
    dr_strategy = dr_block.get("strategy") or "none"
    if dr_strategy.lower() in ("none", "backup-only", "single-region", "local"):
        rule = next((r for r in rules if r["rule_id"] == "RISK-RULE-SINGLE-REGION"), None)
        if rule:
            evidence = f"Target landing zone uses single-region posture with strategy '{dr_strategy}'."
            register.append(_build_risk_entry(rule, evidence, rating_matrix))

    # 4. Evaluate Rule: RISK-RULE-DB-REPLATFORM (Database replatforming)
    replatform_apps = [
        a for a in dispositions.get("dispositions", [])
        if str(a.get("disposition", "")).lower() in ("replatform", "refactor")
        and any(db in str(a.get("database_engine", "")).lower() for db in ("sql", "oracle", "postgres", "mysql"))
    ]
    if replatform_apps:
        rule = next((r for r in rules if r["rule_id"] == "RISK-RULE-DB-REPLATFORM"), None)
        if rule:
            evidence = f"{len(replatform_apps)} application(s) require database replatforming / modernization."
            register.append(_build_risk_entry(rule, evidence, rating_matrix))

    # 5. Evaluate Rule: RISK-RULE-DEPENDENCY-GAPS (Cross-wave affinity)
    stale_deps = waves.get("stale_dependencies_count", 0)
    if stale_deps > 0:
        rule = next((r for r in rules if r["rule_id"] == "RISK-RULE-DEPENDENCY-GAPS"), None)
        if rule:
            evidence = f"{stale_deps} network dependency edge(s) older than 30 days observed in dependency graph."
            register.append(_build_risk_entry(rule, evidence, rating_matrix))

    # 6. Evaluate Rule: RISK-RULE-DISCOVERY-GAPS (Unanswered questionnaire fields)
    unanswered = discovery.get("unanswered_required", [])
    if unanswered:
        rule = next((r for r in rules if r["rule_id"] == "RISK-RULE-DISCOVERY-GAPS"), None)
        if rule:
            evidence = f"{len(unanswered)} required discovery questionnaire questions remain unanswered ({', '.join(unanswered[:3])})."
            register.append(_build_risk_entry(rule, evidence, rating_matrix))

    return register


def _build_risk_entry(
    rule: dict[str, Any],
    evidence: str,
    rating_matrix: dict[str, str],
) -> dict[str, Any]:
    """Format a single risk entry adhering to the E15B.7 column schema."""
    prob = rule.get("probability", "Medium")
    impact = rule.get("impact", "Medium")
    rating_key = f"{prob}:{impact}"
    rating = rating_matrix.get(rating_key, "Medium")

    return {
        "risk_id": rule.get("risk_id", "RSK-GEN"),
        "category": rule.get("category", "General"),
        "risk": rule.get("title", ""),
        "classification": rule.get("classification", "Generic MEG Check"),
        "evidence": evidence,
        "probability": prob,
        "impact": impact,
        "rating": rating,
        "mitigation": rule.get("mitigation", "Review risk during wave planning."),
        "owner_role": rule.get("owner_role", "Lead Cloud Architect"),
        "status": "Open",
    }
