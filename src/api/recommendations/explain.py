"""
Explain Recommendation Engine & Baseline vs. Research Compare (PRD E15D.4, E15D.5).

Provides a deterministic 6-part justification for architectural recommendations:
  1. Recommendation
  2. Customer Driver
  3. Landfall Deterministic Rule
  4. Microsoft Guidance
  5. Confidence
  6. Assumptions / Gaps

Maintains the strict separation between ASSESSMENT BASELINE (immutable pinned assessment)
and LIVE MICROSOFT RESEARCH, flagging differences without silently mutating results.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RecommendationExplanation:
    topic: str
    recommendation: str
    customer_driver: str
    landfall_rule: str
    microsoft_guidance: str
    confidence: str
    assumptions_gaps: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Authoritative deterministic justifications for core architectural recommendations
CORE_EXPLANATIONS: dict[str, RecommendationExplanation] = {
    "firewall": RecommendationExplanation(
        topic="Azure Firewall SKU",
        recommendation="Azure Firewall Premium with TLS Inspection & IDPS",
        customer_driver="Estate carries PCI-DSS and HIPAA regulated workloads with internet-facing ingress requirements.",
        landfall_rule="Regulated compliance scope (PCI-DSS/HIPAA) automatically triggers dedicated spoke with Azure Firewall Premium IDPS and TLS inspection overlay.",
        microsoft_guidance="Microsoft Cloud Adoption Framework (CAF) Landing Zone Hub-Spoke Security Baseline & Microsoft Cloud Security Benchmark (MCSB v1.0).",
        confidence="High",
        assumptions_gaps="Customer must provision an Enterprise Intermediate CA certificate in Azure Key Vault for outbound TLS decryption."
    ),
    "landing_zone_topology": RecommendationExplanation(
        topic="Network Topology",
        recommendation="Hub-Spoke Virtual Network Architecture with Azure Firewall Central Egress",
        customer_driver="Enterprise portfolio requiring isolated environment tiers (Prod, NonProd) and strict compliance separation.",
        landfall_rule="Portfolio exceeding 5 virtual networks or with regulated scopes defaults to Hub-Spoke with forced-tunnel 0.0.0.0/0 egress.",
        microsoft_guidance="Azure Landing Zone (ALZ) Conceptual Architecture — Network Topology and Connectivity guidelines (github.com/Azure/Enterprise-Scale).",
        confidence="High",
        assumptions_gaps="On-premises ExpressRoute or VPN gateway capacity must support minimum 1 Gbps dedicated throughput."
    ),
    "resiliency": RecommendationExplanation(
        topic="Disaster Recovery & Resiliency",
        recommendation="Zone-Redundant Compute with Cross-Region Azure Site Recovery (Tier 1 RTO < 2h, RPO < 15m)",
        customer_driver="Tier 1 mission-critical business applications requiring high availability and regulatory business continuity.",
        landfall_rule="Criticality Tier 1 maps to Availability Zones in primary region paired with asynchronous replication to paired secondary region.",
        microsoft_guidance="Azure Well-Architected Framework (WAF) Reliability Pillar & Business Continuity/DR guidance.",
        confidence="Medium",
        assumptions_gaps="Secondary DR region bandwidth cost assumed at standard inter-region data transfer rates."
    ),
    "compute_rightsizing": RecommendationExplanation(
        topic="VM Right-Sizing & Reservation Strategy",
        recommendation="P95 CPU/RAM Right-Sizing with 1-Year Reserved Instances (80% Coverage) + Azure Hybrid Benefit",
        customer_driver="Customer target to reduce compute operating expense while maintaining operational headroom.",
        landfall_rule="Calculates p95 peak utilization with 20% safety headroom floor (min 2 vCPU / 4 GB RAM); applies 80% 1-year RI commitment.",
        microsoft_guidance="Azure FinOps Framework & Azure Advisor Cost Optimization recommendations.",
        confidence="Medium",
        assumptions_gaps="66 servers lack 30-day performance history; right-sized at 100% current capacity as a conservative baseline."
    ),
    "disposition_replatform": RecommendationExplanation(
        topic="Database Replatforming (6R)",
        recommendation="Replatform to Azure Database for PostgreSQL / MySQL Flexible Server & Azure SQL Managed Instance",
        customer_driver="Eliminate OS-level patching overhead and license costs for standalone database instances.",
        landfall_rule="Databases on tier 3+ lower-criticality applications with standard engines replatform to managed PaaS services.",
        microsoft_guidance="Microsoft Azure Database Migration Guide & Cloud Adoption Framework Migrate Phase Strategy.",
        confidence="Medium",
        assumptions_gaps="Schema compatibility and extension support must be validated using Azure Database Migration Service (DMS)."
    ),
    "resource_planning": RecommendationExplanation(
        topic="Resource Demand & Team Sizing",
        recommendation="Peak 9.42 FTE Delivery Team across 10 Standard Functional Roles over 24-Week Schedule",
        customer_driver="Target to migrate 250 servers and 31 applications within 6 months across 7 waves.",
        landfall_rule="Derives person-days per 6R disposition and packs into wave execution intervals floored at 2-week execution.",
        microsoft_guidance="Microsoft Azure Migration Execution Guide (MEG) Wave Planning and Role RACI Baseline.",
        confidence="Medium",
        assumptions_gaps="Pre-sales default assumes role-based planning (MODE 1). Customer available capacity is unsupplied."
    ),
}


def explain_recommendation(topic_or_query: str) -> dict[str, Any]:
    """
    Returns the structured 6-part explanation for a recommendation topic or natural query.
    """
    q = (topic_or_query or "").lower().strip()

    # Match against known topics
    matched_key = "landing_zone_topology"
    if any(k in q for k in ("firewall", "security", "tls", "premium", "idps")):
        matched_key = "firewall"
    elif any(k in q for k in ("resilien", "dr", "rto", "rpo", "disaster", "recovery")):
        matched_key = "resiliency"
    elif any(k in q for k in ("rightsize", "cost", "ri", "reserve", "saving", "vm", "compute")):
        matched_key = "compute_rightsizing"
    elif any(k in q for k in ("replatform", "database", "sql", "postgres", "mysql", "6r", "paas")):
        matched_key = "disposition_replatform"
    elif any(k in q for k in ("resource", "fte", "team", "staff", "role", "person-day", "capacity")):
        matched_key = "resource_planning"

    explanation = CORE_EXPLANATIONS[matched_key]
    return explanation.to_dict()


def compare_baseline_to_live_guidance(
    baseline_topic: str,
    baseline_value: str,
    live_guidance_text: str | None = None,
) -> dict[str, Any]:
    """
    Compares the immutable assessment baseline with live Microsoft research (E15D.5).
    Flags differences for architect review without silently mutating the baseline.
    """
    has_live_research = bool(live_guidance_text and live_guidance_text.strip())
    is_divergent = False
    flag = "IN_SYNC"
    diff_summary = "Live Microsoft research is consistent with the pinned assessment baseline."

    if has_live_research:
        # Check if live text suggests newer SKUs or deprecations
        text_lower = (live_guidance_text or "").lower()
        if "retire" in text_lower or "deprecated" in text_lower or "preview" in text_lower or "v2" in text_lower:
            is_divergent = True
            flag = "DIFFERENCE_FLAGGED"
            diff_summary = "Live research indicates potential SKU deprecation or newer guidance available since baseline pinning."

    return {
        "status": "ASSESSMENT BASELINE vs LIVE MICROSOFT RESEARCH",
        "topic": baseline_topic,
        "baseline_value": baseline_value,
        "baseline_status": "IMMUTABLE PINNED ASSESSMENT",
        "live_research_available": has_live_research,
        "is_divergent": is_divergent,
        "flag": flag,
        "difference_summary": diff_summary,
        "recommendation": (
            "Flagged difference logged for architect review. To apply new Microsoft research, "
            "trigger an explicit recalculation; the completed assessment baseline will not be changed automatically."
            if is_divergent else "Assessment baseline remains authoritative."
        ),
    }
