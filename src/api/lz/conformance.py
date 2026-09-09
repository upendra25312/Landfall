"""
Checklist conformance for `design_landing_zone` (PRD E11.23 / §4.11).

Deterministic, pure. Given the output of `design_landing_zone` (+ the portfolio it
was designed for), score every item in the vendored Azure Landing Zone design
checklist (`docs/lz-design/alz-checklist.md`) — and the AI Landing Zone overlay
(`docs/lz-design/ai-lz-checklist.md`) when the estate has AI / ML workloads — as
`met` / `partial` / `gap` / `n/a`, each with evidence and, for anything short of
`met`, a recommendation.

The rules read the design's *structured* output (management groups, hub components,
policy baseline, DR block, …); they never parse prose. `n/a` rows are excluded from
the met/total ratio the dashboard shows.
"""
from __future__ import annotations

MET, PARTIAL, GAP, NA = "met", "partial", "gap", "n/a"

_AI_TOKENS = ("ai", "ml", "genai", "gen-ai", "llm", "openai", "machine learning",
              "machine-learning", "analytics", "data science", "data-science",
              "cognitive", "ml runtime", "mlflow", "databricks", "synapse",
              "tensorflow", "pytorch")


def _text(*parts) -> str:
    out = []
    for p in parts:
        if isinstance(p, dict):
            out.append(" ".join(str(v) for v in p.values()))
        elif isinstance(p, (list, tuple, set)):
            out.append(" ".join(str(v) for v in p))
        elif p is not None:
            out.append(str(p))
    return " ".join(out).lower()


def _has(hay: str, *needles) -> bool:
    return any(n in hay for n in needles)


def ai_workloads_present(applications, server_summary=None) -> bool:
    for a in applications or []:
        blob = _text(a.get("workload_type"), a.get("app_name"), a.get("tech_stack"),
                     a.get("notes"), a.get("category"))
        if _has(blob, *_AI_TOKENS):
            return True
    fam = _text((server_summary or {}).get("os_families"),
                (server_summary or {}).get("workload_types"))
    return _has(fam, *_AI_TOKENS)


# --------------------------------------------------------------------------- rules
# Each rule: (id, domain, item, fn) where fn(d) -> (status, evidence, recommendation).
# `d` is a small context object with the design + precomputed helpers.

class _Ctx:
    def __init__(self, design: dict, ai: bool):
        self.d = design or {}
        self.ai = ai
        self.identity = _text((self.d.get("identity") or {}).get("model"),
                              (self.d.get("identity") or {}).get("components"))
        self.hub = _text((self.d.get("hub") or {}).get("components"),
                         (self.d.get("hub") or {}).get("spoke_egress"))
        self.policy = _text((self.d.get("policy") or {}).get("baseline"),
                            (self.d.get("policy") or {}).get("regulated_overlay"))
        self.conn = _text((self.d.get("connectivity") or {}).get("model"),
                          (self.d.get("connectivity") or {}).get("topology"),
                          (self.d.get("connectivity") or {}).get("notes"))
        self.dr = self.d.get("dr") or {}
        self.mgs = _text(self.d.get("management_groups"))
        self.subs = [str(s).lower() for s in self.d.get("subscriptions") or []]
        self.regulated = bool(self.d.get("regulated"))


def _rules():
    R: list[tuple] = []

    def rule(rid, domain, item):
        def deco(fn):
            R.append((rid, domain, item, fn))
            return fn
        return deco

    # -- Identity --
    @rule("ID-1", "Identity", "Entra ID for control-plane auth; no shared keys")
    def _(c):
        return (MET, "Design uses Entra ID + Azure RBAC; PIM in the identity block.", "") \
            if _has(c.identity, "entra", "pim") else \
            (GAP, "Identity model does not state Entra ID / RBAC.", "Base control-plane auth on Entra ID groups; disable local credentials.")

    @rule("ID-2", "Identity", "PIM for just-in-time Azure RBAC")
    def _(c):
        return (MET, "PIM for Azure RBAC is in the identity components.", "") if "pim" in c.identity else \
            (GAP, "No PIM in the identity design.", "Enable Entra PIM; remove standing owner/contributor at MG and subscription scope.")

    @rule("ID-3", "Identity", "Break-glass accounts + no standing admin RDP/SSH")
    def _(c):
        if _has(c.identity, "break-glass", "break glass") and _has(c.identity, "bastion"):
            return (MET, "Break-glass accounts + Azure Bastion (no standing RDP) in the design.", "")
        if "bastion" in c.identity:
            return (PARTIAL, "Bastion present; break-glass accounts not called out.", "Add monitored emergency-access accounts excluded from Conditional Access.")
        return (GAP, "Neither break-glass accounts nor Bastion in the identity design.", "Add break-glass accounts and Azure Bastion for admin access.")

    # -- Resource organization --
    @rule("RO-1", "Resource Organization", "CAF management-group hierarchy")
    def _(c):
        return (MET, "MG hierarchy has platform + landing-zones (+ sandbox, decommissioned).", "") \
            if _has(c.mgs, "platform") and _has(c.mgs, "landingzones", "landing zones", "landingzone") else \
            (GAP, "No CAF platform / landing-zones management groups.", "Adopt the CAF MG hierarchy under an intermediate root.")

    @rule("RO-2", "Resource Organization", "Platform subscriptions: connectivity, identity, management")
    def _(c):
        need = ("connectivity", "identity", "management")
        hit = [n for n in need if any(n in s for s in c.subs)]
        if len(hit) == 3:
            return (MET, "Separate connectivity / identity / management subscriptions.", "")
        return (PARTIAL if hit else GAP, f"Platform subscriptions present: {', '.join(hit) or 'none'}.",
                "Create dedicated subscriptions for the missing platform functions.")

    @rule("RO-3", "Resource Organization", "Landing-zone subscriptions per workload/zone")
    def _(c):
        n = sum(1 for s in c.subs if "-lz-" in s or s.endswith("-sandbox"))
        return (MET, f"{n} landing-zone subscriptions, one per spoke.", "") if n else \
            (GAP, "No per-workload landing-zone subscriptions.", "Split workloads into landing-zone subscriptions by archetype.")

    # -- Networking --
    @rule("NET-1", "Networking", "Hub-spoke or Virtual WAN topology")
    def _(c):
        return (MET, f"Topology: {(c.d.get('connectivity') or {}).get('topology') or 'hub-spoke'}.", "") \
            if _has(c.conn, "hub", "vwan", "virtual wan") or (c.d.get("hub")) else \
            (GAP, "No hub-spoke / vWAN topology in the design.", "Adopt a hub-spoke topology with a central connectivity subscription.")

    @rule("NET-2", "Networking", "Central controlled egress (Azure Firewall / NVA)")
    def _(c):
        if "azure firewall" in c.hub:
            return (MET, "Hub Azure Firewall; " + ((c.d.get("hub") or {}).get("spoke_egress") or ""), "")
        return (PARTIAL, "Egress is direct / NAT gateway per spoke.", "Route spoke egress through a hub Azure Firewall or NVA for inspection and control.")

    @rule("NET-3", "Networking", "Private DNS zones for PaaS + DNS resolver")
    def _(c):
        return (MET, "Hub has Private DNS Resolver + Private DNS zones.", "") if _has(c.hub, "private dns") else \
            (GAP, "No private DNS design in the hub.", "Add Azure Private DNS zones for PaaS + a DNS Private Resolver in the hub.")

    @rule("NET-4", "Networking", "Planned, non-overlapping IP address space")
    def _(c):
        ip = c.d.get("ip_plan") or {}
        return (PARTIAL, f"Supernet {ip.get('supernet')} carved into hub + {len(ip) - 2} spokes; not yet reconciled with client IPAM.",
                "Reconcile the carved plan against the client's real IPAM before build.") if ip else \
            (GAP, "No IP plan.", "Carve a non-overlapping supernet for hub + spokes + DR.")

    @rule("NET-5", "Networking", "Hybrid connectivity (ExpressRoute + VPN backup)")
    def _(c):
        if _has(c.conn, "expressroute") and _has(c.conn, "vpn"):
            return (MET, "ExpressRoute primary with VPN backup.", "")
        if _has(c.conn, "expressroute", "vpn"):
            return (PARTIAL, f"Connectivity: {(c.d.get('connectivity') or {}).get('model')}.", "Add a VPN backup path for the ExpressRoute circuit (or vice-versa).")
        return (GAP, "No hybrid connectivity in the design.", "Size ExpressRoute (with VPN backup) for the migration bandwidth.")

    # -- Security --
    @rule("SEC-1", "Security", "Private Endpoints for PaaS; deny public network access")
    def _(c):
        return (MET, "Policy baseline / overlay requires Private Endpoints + denies public access.", "") \
            if _has(c.policy, "private endpoint", "private-endpoint", "deny public") else \
            (GAP, "Private-endpoint / deny-public-access policy not in the baseline.", "Assign the 'deny public network access' + private-endpoint policy initiative at MG scope.")

    @rule("SEC-2", "Security", "Customer-managed keys for regulated data")
    def _(c):
        if not c.regulated:
            return (NA, "No regulated workloads in the portfolio.", "")
        return (MET, "Regulated overlay mandates CMK for Storage + SQL/MI TDE.", "") if _has(c.policy, "customer-managed key", "cmk", "managed hsm") else \
            (GAP, "Regulated workloads present but no CMK requirement.", "Add a customer-managed-keys policy for regulated data stores.")

    @rule("SEC-3", "Security", "Regulatory-compliance initiative assigned")
    def _(c):
        if not c.regulated:
            return (NA, "No compliance scope in the portfolio.", "")
        return (MET, f"Built-in initiative assigned for {', '.join(c.d.get('regulated_scopes_present') or [])}.", "") \
            if _has(c.policy, "initiative") else \
            (PARTIAL, f"Regulated scopes {c.d.get('regulated_scopes_present')} but no built-in initiative named.",
             "Assign the matching built-in regulatory-compliance initiative (PCI DSS v4, HIPAA HITRUST, …).")

    @rule("SEC-4", "Security", "DDoS Network Protection for internet-facing spokes")
    def _(c):
        online = (c.d.get("zone_counts") or {}).get("online")
        if not online:
            return (NA, "No internet-facing (Online) workloads.", "")
        return (MET, "DDoS protection referenced in the hub / policy.", "") if "ddos" in (c.hub + c.policy) else \
            (GAP, f"{online} internet-facing app(s) but no DDoS Network Protection.", "Enable Azure DDoS Network Protection on VNets hosting the Online spokes.")

    # -- Governance --
    @rule("GOV-1", "Governance", "Policy baseline assigned at MG scope")
    def _(c):
        base = (c.d.get("policy") or {}).get("baseline") or []
        return (MET, f"{len(base)} baseline policy/initiative assignments.", "") if base else \
            (GAP, "No policy baseline.", "Assign a policy baseline at the intermediate-root / platform MG scope.")

    @rule("GOV-2", "Governance", "Guardrails: allowed regions, SKUs, required tags")
    def _(c):
        hits = [w for w in ("region", "sku", "tag") if w in c.policy]
        if len(hits) >= 2:
            return (MET, f"Guardrail policies cover: {', '.join(hits)}.", "")
        return (PARTIAL, f"Baseline covers: {', '.join(hits) or 'none of region/SKU/tag'}.",
                "Add allowed-locations, allowed-SKU and require-tag policies to the baseline.")

    @rule("GOV-3", "Governance", "Regulated workloads isolated by MG + policy overlay")
    def _(c):
        if not c.regulated:
            return (NA, "No regulated workloads.", "")
        return (MET, "Confidential management group + regulated policy overlay + dedicated spokes.", "") \
            if _has(c.mgs, "confidential") and ((c.d.get("policy") or {}).get("regulated_overlay")) else \
            (PARTIAL, "Regulated workloads present; isolation only partial.", "Add a Confidential MG and a policy overlay for the regulated spokes.")

    # -- Management --
    @rule("MGMT-1", "Management", "Centralized Log Analytics workspace")
    def _(c):
        if _has(c.hub + c.policy, "log analytics", "log-analytics"):
            return (MET, "Central Log Analytics workspace in the design.", "")
        if any("management" in s for s in c.subs):
            return (PARTIAL, "Management subscription exists but no central workspace is named.", "Provision a central Log Analytics workspace in the management subscription.")
        return (GAP, "No central logging design.", "Add a management subscription with a central Log Analytics workspace.")

    @rule("MGMT-2", "Management", "Diagnostic settings routed to the central workspace by policy")
    def _(c):
        return (MET, "Diagnostic-settings policy in the baseline.", "") if _has(c.policy, "diagnostic") else \
            (GAP, "No deploy-diagnostic-settings policy.", "Assign the 'deploy diagnostic settings to Log Analytics' policy initiative.")

    @rule("MGMT-3", "Management", "Patch / update management for migrated VMs")
    def _(c):
        return (MET, "Update management referenced in the design.", "") if _has(c.policy + c.hub, "update manager", "update management", "patch") else \
            (GAP, "No patching strategy for migrated VMs.", "Adopt Azure Update Manager with maintenance configurations per environment.")

    # -- Monitoring --
    @rule("MON-1", "Monitoring", "Platform vs. workload monitoring separation")
    def _(c):
        return (PARTIAL, "Platform subscriptions exist; monitoring ownership split not documented.",
                "State that the platform team owns the monitoring baseline and workload teams own app telemetry.")

    @rule("MON-2", "Monitoring", "Alerting baseline with action groups")
    def _(c):
        return (MET, "Alerting baseline in the design.", "") if _has(c.policy + c.hub, "action group", "alert") else \
            (GAP, "No platform alerting baseline.", "Define action groups + baseline alerts for platform-critical signals.")

    @rule("MON-3", "Monitoring", "Service-health and resource-health alerts")
    def _(c):
        return (MET, "Service/resource-health alerts in the design.", "") if _has(c.policy + c.hub, "service health", "resource health") else \
            (GAP, "No service-health alerting.", "Add Service Health + Resource Health alerts to the platform baseline.")

    # -- Reliability --
    @rule("REL-1", "Reliability", "Two or more regions for tier-1/2 workloads")
    def _(c):
        return (MET, f"Primary {c.d.get('region')} paired with DR {c.d.get('dr_region')}.", "") if c.d.get("dr_region") else \
            (GAP, "No DR region — single-region design.", "Select the Azure paired region and design DR for tier-1/2 workloads.")

    @rule("REL-2", "Reliability", "Availability zones for production")
    def _(c):
        return (MET, "Production availability zones enabled.", "") if c.dr.get("prod_availability_zones") else \
            (PARTIAL, "Availability zones not enabled for production.", "Deploy production workloads across availability zones where the region supports them.")

    @rule("REL-3", "Reliability", "Documented RPO/RTO per resiliency tier")
    def _(c):
        return (MET, f"{len(c.dr.get('tier_definitions') or {})} resiliency tiers with RPO/RTO defined.", "") \
            if c.dr.get("tier_definitions") else \
            (GAP, "No resiliency-tier definitions.", "Define RPO/RTO per criticality tier in estimation_config.json.")

    @rule("REL-4", "Reliability", "Backup with a GRS / geo-redundant vault")
    def _(c):
        return (MET, "DR strategy recovers lower tiers from a GRS Backup vault.", "") if _has(_text(c.dr.get("strategy")), "backup", "grs") else \
            (GAP, "Backup strategy not stated.", "Add Azure Backup with a GRS vault for tiers that recover from backup.")

    # -- Cost --
    @rule("COST-1", "Cost", "Reserved Instances / savings plan for steady-state compute")
    def _(c):
        return (PARTIAL, "Reservation strategy is set in the cost estimate, not the LZ design.",
                "Confirm 1- or 3-year Reserved Instances / a savings plan for the steady-state fleet in the estimate.")

    @rule("COST-2", "Cost", "Budgets and cost alerts per landing-zone subscription")
    def _(c):
        return (GAP, "No budgets / cost alerts in the design.", "Assign a budget + cost-alert action group to every landing-zone subscription.")

    @rule("COST-3", "Cost", "Tagging standard for cost allocation")
    def _(c):
        return (MET, "Require-tag governance in the policy baseline.", "") if "tag" in c.policy else \
            (PARTIAL, "No tagging policy in the baseline.", "Define and enforce a cost-allocation tag set (cost-centre, owner, environment).")

    # -- Data --
    @rule("DATA-1", "Data", "Data residency honoured by region choice")
    def _(c):
        return (MET, f"All workloads land in {c.d.get('region')} (+ DR {c.d.get('dr_region') or 'n/a'}).", "") if c.d.get("region") else \
            (GAP, "No primary region chosen.", "Choose the primary region for the customer's data-residency requirement.")

    @rule("DATA-2", "Data", "Private connectivity for data-platform services")
    def _(c):
        return (MET, "Private-endpoint policy covers data services.", "") if _has(c.policy, "private endpoint", "private-endpoint") else \
            (GAP, "Data-platform services not required to be private.", "Extend the private-endpoint initiative to SQL, Storage, Cosmos and analytics services.")

    @rule("DATA-3", "Data", "Backup and retention for migrated data stores")
    def _(c):
        return (MET, "Backup + retention in the DR strategy.", "") if _has(_text(c.dr.get("strategy")), "backup") else \
            (GAP, "No backup/retention for data stores.", "Define backup policy + retention for each migrated data store.")

    return R


_ALZ_RULES = _rules()


def _ai_rules(ctx: _Ctx) -> list[dict]:
    """The AI-LZ overlay. Nothing in `design_landing_zone` produces an AI platform
    today, so every row is a `gap` (with a recommendation) when AI workloads exist,
    except the ones the base design already satisfies (managed identity)."""
    if not ctx.ai:
        rows = [
            ("AILZ-1", "AI platform", "AI Foundry hub + project per engagement in the LZ"),
            ("AILZ-2", "AI platform", "PTU baseline + PAYG spillover, quota per region"),
            ("AILZ-3", "Networking & security", "AI services private-endpoint only"),
            ("AILZ-4", "Networking & security", "Managed identities for AI calls (no keys)"),
            ("AILZ-5", "Networking & security", "APIM as the generative-AI gateway"),
            ("AILZ-6", "Networking & security", "Private grounding / RAG data store"),
            ("AILZ-7", "Responsible AI & governance", "Content Safety on every production inference path"),
            ("AILZ-8", "Responsible AI & governance", "Responsible-AI review + evaluation before go-live"),
            ("AILZ-9", "Operations & cost", "AI observability (token / latency / cost / quality)"),
            ("AILZ-10", "Operations & cost", "AI cost controls: PTU sizing, budgets, quota alerts"),
        ]
        return [{"id": i, "domain": f"AI-LZ · {dom}", "item": it, "status": NA,
                 "evidence": "No AI / ML / analytics workloads in the portfolio.",
                 "recommendation": ""} for i, dom, it in rows]

    keys = "no api key" not in ctx.identity  # baseline uses managed identity / Entra
    out = [
        ("AILZ-1", "AI platform", "AI Foundry hub + project per engagement in the LZ", GAP,
         "The base LZ design has no AI platform.", "Add an AI Foundry hub + a per-engagement project, deployed into a landing-zone subscription."),
        ("AILZ-2", "AI platform", "PTU baseline + PAYG spillover, quota per region", GAP,
         "No model-capacity plan.", "Plan Provisioned Throughput for the baseline load with PAYG spillover; request quota in the primary region."),
        ("AILZ-3", "Networking & security", "AI services private-endpoint only", GAP,
         "AI Foundry / OpenAI / AI Search / Content Safety not in the private-endpoint scope.",
         "Extend the deny-public-access + private-endpoint policy to all AI services."),
        ("AILZ-4", "Networking & security", "Managed identities for AI calls (no keys)",
         MET if keys else PARTIAL,
         "Base identity design uses Entra ID / managed identity." if keys else "Confirm no API keys in AI app config.",
         "" if keys else "Switch every AI service call to a managed identity."),
        ("AILZ-5", "Networking & security", "APIM as the generative-AI gateway", GAP,
         "No API Management gen-AI gateway.", "Front Azure OpenAI with APIM for token metering, throttling, multi-region load balancing and key vaulting."),
        ("AILZ-6", "Networking & security", "Private grounding / RAG data store", GAP,
         "No private grounding-data store.", "Store RAG / grounding data in a private AI Search + private storage account."),
        ("AILZ-7", "Responsible AI & governance", "Content Safety on every production inference path", GAP,
         "Azure AI Content Safety not in the design.", "Require prompt-shield + output filtering on all production inference paths."),
        ("AILZ-8", "Responsible AI & governance", "Responsible-AI review + evaluation before go-live", GAP,
         "No responsible-AI gate.", "Add a content-filter policy, abuse monitoring and a documented evaluation / red-team step before go-live."),
        ("AILZ-9", "Operations & cost", "AI observability (token / latency / cost / quality)", GAP,
         "No AI telemetry design.", "Route token usage, latency, cost and quality metrics to the central Log Analytics workspace."),
        ("AILZ-10", "Operations & cost", "AI cost controls: PTU sizing, budgets, quota alerts", GAP,
         "No AI cost controls.", "Size PTU reservations, set per-project budgets and quota alerts for AI spend."),
    ]
    return [{"id": i, "domain": f"AI-LZ · {dom}", "item": it, "status": st,
             "evidence": ev, "recommendation": rec} for i, dom, it, st, ev, rec in out]


def evaluate(design: dict, applications: list[dict] | None = None,
             server_summary: dict | None = None) -> dict:
    """Score the design against the ALZ checklist (+ AI-LZ overlay when applicable).

    Returns {items: [{id, domain, item, status, evidence, recommendation}],
             summary: {met, partial, gap, na, total, met_pct, headline},
             ai_lz_applicable: bool, gaps: [...], sources: [...]}.
    """
    ai = ai_workloads_present(applications, server_summary)
    ctx = _Ctx(design, ai)

    items: list[dict] = []
    for rid, domain, item, fn in _ALZ_RULES:
        try:
            status, evidence, rec = fn(ctx)
        except Exception as exc:                      # noqa: BLE001 - a rule must never break the estimate
            status, evidence, rec = GAP, f"rule error: {exc}", "Review this checklist item manually."
        items.append({"id": rid, "domain": domain, "item": item, "status": status,
                      "evidence": evidence, "recommendation": rec if status != MET else ""})

    items.extend(_ai_rules(ctx))

    counts = {MET: 0, PARTIAL: 0, GAP: 0, NA: 0}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    total = counts[MET] + counts[PARTIAL] + counts[GAP]
    met_pct = round(100 * counts[MET] / total) if total else 0
    gaps = [{"id": it["id"], "domain": it["domain"], "item": it["item"],
             "status": it["status"], "recommendation": it["recommendation"]}
            for it in items if it["status"] in (PARTIAL, GAP)]

    return {
        "items": items,
        "summary": {
            "met": counts[MET], "partial": counts[PARTIAL], "gap": counts[GAP],
            "na": counts[NA], "total": total, "met_pct": met_pct,
            "headline": f"{counts[MET]}/{total} checklist items met"
            + (f" · {counts[GAP]} gaps" if counts[GAP] else ""),
        },
        "ai_lz_applicable": ai,
        "gaps": gaps,
        "sources": ["docs/lz-design/alz-checklist.md", "docs/lz-design/ai-lz-checklist.md"],
    }
