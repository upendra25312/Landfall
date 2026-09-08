"""
design_landing_zone (PRD E3.1 / E3.2 / E3.3) — deterministic, pure.

    result = design_landing_zone(applications, server_summary, cfg)

Rules (the topology is DERIVED from the portfolio, never a fixed template):
  * zone per app — internet_facing -> Online; a regulated compliance_scope ->
    Regulated (its own spoke per distinct scope); else Corp.
  * spokes = (zone x environment) that actually has apps, plus one regulated
    spoke pair per distinct regulated scope, plus sandbox. No PCI app -> no PCI
    spoke.
  * management groups / subscriptions follow the spokes.
  * IP plan carves the configured supernet sequentially.
  * policy set = baseline + a regulated overlay when any regulated app exists.
  * resiliency tier per app from criticality (E3.3).
"""
from __future__ import annotations

import ipaddress

from cost.config import load_config

_ENV_ORDER = {"prod": 0, "nonprod": 1, "dev": 1, "test": 1, "uat": 1, "qa": 1, "dr": 2}


def _scopes(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = [p.strip() for chunk in str(raw).replace(",", ";").split(";") for p in [chunk]]
    return [p for p in parts if p and p.lower() not in ("none", "n/a", "-")]


def _norm_scope(s: str) -> str:
    return s.upper().replace(" ", "").replace("_", "-")


def assign_zone(app: dict, regulated: set[str]) -> tuple[str, str | None]:
    """(zone, regulated_scope). zone in {online, corp, regulated}."""
    app_scopes = [_norm_scope(s) for s in _scopes(app.get("compliance_scope"))]
    hit = next((s for s in app_scopes if s in regulated), None)
    if hit:
        return "regulated", hit
    if str(app.get("internet_facing")).strip() in ("1", "true", "True", "yes", "Y"):
        return "online", None
    return "corp", None


def _tier_for(criticality, tiers: dict) -> str:
    c = str(criticality).strip()
    return c if c in tiers else "3"


def design_landing_zone(
    applications: list[dict],
    server_summary: dict | None = None,
    cfg: dict | None = None,
) -> dict:
    cfg = cfg or load_config()
    lz = cfg["landing_zone"]
    ss = server_summary or {}
    org = lz.get("org_id", "alz")
    region = lz.get("primary_region")
    dr_region = lz.get("dr_region")
    envs = lz.get("environments", ["prod", "nonprod"])
    regulated = {_norm_scope(s) for s in lz.get("regulated_scopes", [])}
    tiers = lz.get("resiliency_tiers", {})

    # --- classify every app -------------------------------------------------
    placed: list[dict] = []
    zones_present: set[str] = set()
    reg_scopes_present: list[str] = []
    for a in applications:
        zone, scope = assign_zone(a, regulated)
        zones_present.add(zone)
        if scope and scope not in reg_scopes_present:
            reg_scopes_present.append(scope)
        placed.append({
            "app_id": a.get("app_id"),
            "app_name": a.get("app_name"),
            "zone": zone,
            "regulated_scope": scope,
            "criticality": a.get("criticality"),
            "resiliency_tier": _tier_for(a.get("criticality"), tiers),
            "compliance_scope": _scopes(a.get("compliance_scope")),
            "internet_facing": str(a.get("internet_facing")).strip() in ("1", "true", "True", "yes"),
        })
    reg_scopes_present.sort()
    has_regulated = bool(reg_scopes_present)

    # --- spokes (one per zone x environment that has apps) -------------------
    # apps aren't environment-scoped in the portfolio; a zone's apps land in that
    # zone's prod AND nonprod spokes (their prod / non-prod servers respectively).
    spokes: list[dict] = []
    for zone in ("online", "corp"):
        if zone not in zones_present:
            continue
        zone_apps = [p["app_id"] for p in placed if p["zone"] == zone]
        for env in envs:
            spokes.append({"name": f"{zone}-{env}", "zone": zone, "env": env,
                           "regulated_scope": None, "apps": zone_apps})
    for scope in reg_scopes_present:
        scope_apps = [p["app_id"] for p in placed if p["regulated_scope"] == scope]
        for env in envs:
            spokes.append({"name": f"{scope.lower().replace('-', '')}-{env}",
                           "zone": "regulated", "env": env, "regulated_scope": scope,
                           "apps": scope_apps})
    spokes.append({"name": "sandbox", "zone": "sandbox", "env": "sandbox",
                   "regulated_scope": None, "apps": []})

    # --- IP plan ------------------------------------------------------
    supernet = ipaddress.ip_network(lz.get("ip_supernet", "10.100.0.0/14"))
    hub_prefix = int(lz.get("hub_prefix", 22))
    spoke_prefix = int(lz.get("spoke_prefix", 22))
    blocks = _carve(supernet, [hub_prefix] + [spoke_prefix] * len(spokes))
    ip_plan = {"supernet": str(supernet), "hub": str(blocks[0])}
    for sp, blk in zip(spokes, blocks[1:]):
        sp["address_space"] = str(blk)
        ip_plan[sp["name"]] = str(blk)
    dr_super = lz.get("dr_ip_supernet")
    if dr_super:
        ip_plan["dr_supernet"] = dr_super

    # --- management groups (CAF ALZ) --------------------------------
    lz_children = []
    if "corp" in zones_present:
        lz_children.append(f"{org}-corp")
    if "online" in zones_present:
        lz_children.append(f"{org}-online")
    if has_regulated:
        lz_children.append(f"{org}-confidential")
    mg_hierarchy = {
        org: {
            f"{org}-platform": [f"{org}-connectivity", f"{org}-identity", f"{org}-management"],
            f"{org}-landingzones": lz_children,
            f"{org}-sandbox": [],
            f"{org}-decommissioned": [],
        }
    }

    # --- subscriptions -------------------------------------------
    subs = [f"{org}-connectivity", f"{org}-identity", f"{org}-management"]
    for sp in spokes:
        if sp["zone"] == "sandbox":
            subs.append(f"{org}-sandbox")
        else:
            subs.append(f"{org}-lz-{sp['name']}")

    # --- hub ---------------------------------------------------
    conn = lz.get("connectivity", "expressroute+vpn")
    hub_components = ["Hub VNet", "Azure Bastion", "Private DNS Resolver + Private DNS zones"]
    if "expressroute" in conn:
        hub_components.append("ExpressRoute Gateway")
    if "vpn" in conn:
        hub_components.append("VPN Gateway (backup / interim)")
    if lz.get("forced_tunnel_egress", True):
        hub_components.append("Azure Firewall Premium (forced-tunnel egress, IDPS + TLS inspection)")
    identity = lz.get("identity_model", "extend_ad")
    if identity == "extend_ad":
        hub_components.append("2x AD Domain Controllers (new AD site, existing forest)")
    elif identity == "entra_domain_services":
        hub_components.append("Entra Domain Services (replica set)")

    # --- policy set --------------------------------------------
    policy_set = list(lz.get("policy_baseline", []))
    regulated_overlay = []
    if has_regulated:
        regulated_overlay = [
            "Customer-managed keys for Storage + SQL/managed-instance TDE (Key Vault / Managed HSM)",
            "Deny public network access; require Private Endpoints on PaaS data services",
            "Dedicated Azure Firewall policy + explicit east-west deny between regulated and non-regulated spokes",
        ]
        for scope in reg_scopes_present:
            builtin = _COMPLIANCE_INITIATIVE.get(scope)
            if builtin:
                regulated_overlay.append(f"Assign built-in initiative: {builtin}")

    # --- DR ---------------------------------------------------
    tier_rollup: dict[str, int] = {}
    for p in placed:
        tier_rollup[p["resiliency_tier"]] = tier_rollup.get(p["resiliency_tier"], 0) + 1
    dr_tiers = sorted(t for t in tier_rollup if t in ("1", "2"))
    dr = {
        "dr_region": dr_region,
        "strategy": (f"Region pair {region} -> {dr_region}. Azure Site Recovery + native DB "
                     f"replication for resiliency tiers {', '.join(dr_tiers) or 'n/a'}; "
                     f"tiers 3-4 recover from Azure Backup (GRS vault)."),
        "prod_availability_zones": bool(lz.get("prod_availability_zones", True)),
        "tier_definitions": tiers,
        "apps_by_tier": dict(sorted(tier_rollup.items())),
    }

    zone_counts = {z: sum(1 for p in placed if p["zone"] == z) for z in sorted(zones_present)}
    summary = (
        f"CAF Azure Landing Zone for {len(applications)} applications in {region} "
        f"(DR {dr_region}). {len(spokes)} spokes across "
        f"{', '.join(f'{v} {k}' for k, v in zone_counts.items())}"
        + (f"; regulated: {', '.join(reg_scopes_present)} (dedicated spoke + Confidential MG + policy overlay)"
           if has_regulated else "; no regulated workloads — standard Corp/Online zones only")
        + f". Identity: {identity.replace('_', ' ')}. Connectivity: {conn}."
    )

    return {
        "region": region,
        "dr_region": dr_region,
        "regulated": has_regulated,
        "regulated_scopes_present": reg_scopes_present,
        "zone_counts": zone_counts,
        "applications_placed": placed,
        "management_groups": mg_hierarchy,
        "subscriptions": subs,
        "spokes": spokes,
        "ip_plan": ip_plan,
        "hub": {"region": region, "components": hub_components,
                "spoke_egress": "forced-tunnel via hub Azure Firewall" if lz.get("forced_tunnel_egress", True)
                else "direct / NAT gateway per spoke"},
        "identity": _identity_block(identity, ss),
        "connectivity": {
            "model": conn, "topology": "single hub-spoke (hub in " + str(region) + ")",
            "notes": "ExpressRoute primary with S2S VPN as backup / seeding fallback"
                     if conn == "expressroute+vpn" else conn,
        },
        "policy": {"baseline": policy_set, "regulated_overlay": regulated_overlay},
        "dr": dr,
        "server_footprint": {
            "total_servers": ss.get("total_servers"),
            "by_env": ss.get("by_env"),
            "total_vcpu": ss.get("total_vcpu"),
            "total_ram_gb": ss.get("total_ram_gb"),
            "os_families": ss.get("os_families"),
        },
        "summary": summary,
        "next_step": ("Feed this design to the azure-enterprise-infra-planner skill as a "
                      "requirements document to generate subscription-scope Bicep / Terraform."),
        "assumptions": [
            "CAF Azure Landing Zones architecture (platform + landing-zone management groups).",
            f"Environment spokes built per zone: {', '.join(envs)}. DR region gets a mirrored address space.",
            "A dedicated spoke + Confidential management group + CMK/private-endpoint policy overlay "
            "is created for each distinct regulated compliance scope in the portfolio.",
            f"Resiliency tier is derived from application criticality 1-4 -> "
            f"{'/'.join(tiers.keys()) or 'default'} (RPO/RTO per estimation_config.json).",
            "IP plan is a sequential carve of the configured supernet — reconcile against the "
            "client's real IPAM before build.",
        ],
        "config": {"source": cfg.get("_source"), "landing_zone": lz},
    }


_COMPLIANCE_INITIATIVE = {
    "PCI-DSS": "PCI DSS v4 (built-in regulatory compliance initiative)",
    "PCI": "PCI DSS v4 (built-in regulatory compliance initiative)",
    "HIPAA": "HIPAA HITRUST 9.2 (built-in regulatory compliance initiative)",
    "HITRUST": "HIPAA HITRUST 9.2 (built-in regulatory compliance initiative)",
    "FedRAMP": "FedRAMP High (built-in regulatory compliance initiative)",
    "IRAP": "Australian Government ISM PROTECTED (built-in regulatory compliance initiative)",
}


def _identity_block(model: str, ss: dict) -> dict:
    base = {
        "extend_ad": {
            "model": "Extend on-prem AD",
            "components": ["2x replica Domain Controllers in the hub (new AD site)",
                           "Entra Connect (existing)", "Entra PIM for Azure RBAC",
                           "Azure Bastion + break-glass per admin tier (no standing RDP)"],
            "notes": "Preserve SPNs / gMSA; keep migrated servers domain-joined.",
        },
        "greenfield_entra": {
            "model": "Greenfield Entra ID",
            "components": ["Entra ID only", "Entra PIM", "Conditional Access baseline"],
            "notes": "No domain-join; apps must support modern auth.",
        },
        "entra_domain_services": {
            "model": "Entra Domain Services",
            "components": ["Entra DS replica set in the hub", "Entra PIM"],
            "notes": "Managed domain; no DC VMs to run, limited schema control.",
        },
    }.get(model, {"model": model, "components": [], "notes": ""})
    return base


def _carve(supernet: ipaddress._BaseNetwork, prefixes: list[int]) -> list:
    """Allocate each requested prefix length sequentially from the supernet."""
    out = []
    cursor = int(supernet.network_address)
    end = int(supernet.broadcast_address)
    for p in prefixes:
        size = 2 ** (supernet.max_prefixlen - p)
        # align cursor up to the block size
        if cursor % size:
            cursor += size - (cursor % size)
        if cursor + size - 1 > end:
            raise ValueError(f"supernet {supernet} too small for the requested spokes")
        out.append(ipaddress.ip_network((cursor, p)))
        cursor += size
    return out
