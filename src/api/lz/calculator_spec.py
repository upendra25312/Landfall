"""
Build an Azure Pricing Calculator *line-item spec* from Landfall's own design and
cost output (PRD E11.15).

    spec = build_calculator_spec(
        engagement={"customer": "Contoso", "project": "DC Exit",
                    "target_region": "swedencentral", "dr_region": "westeurope",
                    "currency": "USD", "licensing_program": "MCA"},
        design=design_landing_zone(...),          # lz.design output  (optional)
        compute=estimate_compute_cost(...),       # cost.compute_cost output (optional)
        storage=estimate_storage_cost(...),       # cost.storage_cost output (optional)
        run_rate=estimate_run_rate_extras(...),   # cost.run_rate output     (optional)
    )

The spec is the contract between Landfall and the `ca-calc` container (§4.6): it
says *which calculator product module to add and how to configure it* — region,
SKU/tier, quantity, hours, billing option — and carries **no prices**. The
calculator supplies the prices; `ca-calc` drives the real calculator with this
spec and captures its Excel export as the POE artifact.

Pure and deterministic. No network, no Azure imports. Every quantity is traceable
to a Landfall figure via the `note` on each line item; anything that can't be
mapped to a real calculator module lands in `spec["skipped"]` with a reason
rather than being silently dropped or mispriced.
"""
from __future__ import annotations

import re

# --- Azure region name -> Pricing Calculator select[name=region] value --------
# Captured from the live calculator 2026-09-08. A region not in this table is
# rejected (fail loud at engagement-create rather than mis-region a POE).
_CALC_REGION: dict[str, str] = {
    "centralus": "us-central", "eastus": "us-east", "eastus2": "us-east-2",
    "northcentralus": "us-north-central", "southcentralus": "us-south-central",
    "westcentralus": "us-west-central", "westus": "us-west", "westus2": "us-west-2",
    "westus3": "us-west-3",
    "uksouth": "united-kingdom-south", "ukwest": "united-kingdom-west",
    "uaecentral": "uae-central", "uaenorth": "uae-north",
    "switzerlandnorth": "switzerland-north", "switzerlandwest": "switzerland-west",
    "swedencentral": "sweden-central", "swedensouth": "sweden-south",
    "spaincentral": "spain-central", "qatarcentral": "qatar-central",
    "polandcentral": "poland-central", "norwayeast": "norway-east",
    "norwaywest": "norway-west", "newzealandnorth": "new-zealand-north",
    "mexicocentral": "mexico-central", "malaysiawest": "malaysia-west",
    "koreacentral": "korea-central", "koreasouth": "korea-south",
    "japaneast": "japan-east", "japanwest": "japan-west",
    "italynorth": "italy-north", "israelcentral": "israel-central",
    "indonesiacentral": "indonesia-central",
    "centralindia": "central-india", "southindia": "south-india",
    "westindia": "west-india", "southcentralindia": "south-central-india",
    "germanynorth": "germany-north", "germanywestcentral": "germany-west-central",
    "francecentral": "france-central", "francesouth": "france-south",
    "northeurope": "europe-north", "westeurope": "europe-west",
    "denmarkeast": "denmark-east", "chilecentral": "chile-central",
    "canadacentral": "canada-central", "canadaeast": "canada-east",
    "brazilsouth": "brazil-south", "brazilsoutheast": "brazil-southeast",
    "belgiumcentral": "belgium-central",
    "usgovarizona": "usgov-arizona", "usgovtexas": "usgov-texas",
    "usgovvirginia": "usgov-virginia",
    "austriaeast": "austria-east",
    "australiacentral": "australia-central", "australiacentral2": "australia-central-2",
    "australiaeast": "australia-east", "australiasoutheast": "australia-southeast",
    "eastasia": "asia-pacific-east", "southeastasia": "asia-pacific-southeast",
    "southafricanorth": "south-africa-north", "southafricawest": "south-africa-west",
}

# licensing program -> select[name=discountLevel] value. Anonymous calculator
# sessions only expose MCA; EA / CSP / MOSP need Log in (E11.19).
_CALC_LICENSING = {"MCA": "mca", "EA": "ea", "MOSP": "mosp", "CSP": "csp"}

_TERM_TO_BILLING = {"none": "payg", "1yr": "one-year", "3yr": "three-year",
                    "1 year": "one-year", "3 years": "three-year"}

# VM family letter -> (calculator category label, series hint)
_VM_FAMILY = {
    "b": ("General purpose", "Bs-series"),
    "d": ("General purpose", "Dsv5-series"),
    "e": ("Memory optimized", "Esv5-series"),
    "f": ("Compute optimized", "Fsv2-series"),
    "l": ("Storage optimized", "Lsv3-series"),
    "m": ("Memory optimized", "M-series"),
    "n": ("GPU", "NC-series"),
}

# storage_cost category -> (calculator service, config)
_STORAGE_MODULE = {
    "files_premium":      ("storage-accounts", {"type": "files", "tier": "premium", "redundancy": "lrs"}),
    "files_standard_hot": ("storage-accounts", {"type": "files", "tier": "standard", "access": "hot", "redundancy": "lrs"}),
    "anf_standard": ("azure-netapp-files", {"service_level": "standard"}),
    "anf_premium":  ("azure-netapp-files", {"service_level": "premium"}),
    "anf_ultra":    ("azure-netapp-files", {"service_level": "ultra"}),
    "blob_hot_lrs":       ("storage-accounts", {"type": "block-blob", "tier": "standard", "access": "hot", "redundancy": "lrs"}),
    "blob_cool_lrs":      ("storage-accounts", {"type": "block-blob", "tier": "standard", "access": "cool", "redundancy": "lrs"}),
    "db_sql_mi":          ("sql-managed-instance", {"tier": "general-purpose"}),
    "db_sql_hyperscale":  ("sql-database", {"tier": "hyperscale"}),
    "db_flex_postgresql": ("azure-database-for-postgresql", {"tier": "flexible-server", "component": "storage"}),
    "db_flex_mysql":      ("azure-database-for-mysql", {"tier": "flexible-server", "component": "storage"}),
    "db_oracle":          (None, {}),   # priced outside the calculator
}

_HOURS_MONTH = 730


# --------------------------------------------------------------------------
# public
# --------------------------------------------------------------------------
def calc_region(azure_name: str) -> str:
    """Azure region name (e.g. 'swedencentral') -> calculator region value
    (e.g. 'sweden-central'). Raises ValueError for a region the calculator
    cannot price."""
    key = re.sub(r"[\s_-]", "", (azure_name or "").strip().lower())
    if key in _CALC_REGION:
        return _CALC_REGION[key]
    raise ValueError(
        f"region {azure_name!r} is not one the Azure Pricing Calculator lists "
        f"(so a POE cannot be generated for it) — pick another target region"
    )


def region_is_supported(azure_name: str) -> bool:
    try:
        calc_region(azure_name)
        return True
    except ValueError:
        return False


def vm_size_slug(sku: str) -> str:
    """'Standard_D4s_v5' -> 'd4sv5' (the calculator's size id)."""
    s = (sku or "").strip()
    s = re.sub(r"^standard[_\s-]*", "", s, flags=re.I)
    return re.sub(r"[_\s-]", "", s).lower()


def vm_size_name(sku: str) -> str:
    """'Standard_D4s_v5' -> 'D4s v5' (the human name to type as a fallback)."""
    s = re.sub(r"^Standard_", "", (sku or "").strip())
    return s.replace("_", " ")


def _vm_family_meta(sku: str) -> tuple[str, str]:
    m = re.search(r"([a-z])", vm_size_slug(sku))
    return _VM_FAMILY.get(m.group(1) if m else "d", ("General purpose", "Dsv5-series"))


def build_calculator_spec(
    engagement: dict,
    design: dict | None = None,
    compute: dict | None = None,
    storage: dict | None = None,
    run_rate: dict | None = None,
    *,
    include_dr_compute: bool = False,
    generated_on: str | None = None,
) -> dict:
    """Assemble the calculator line-item spec. Every argument but `engagement`
    is optional — a missing tool output just contributes no line items."""
    cust = str(engagement.get("customer") or engagement.get("display") or "Customer").strip()
    proj = str(engagement.get("project") or "Project").strip()
    region_az = engagement.get("target_region") or (design or {}).get("region") \
        or (compute or {}).get("region") or "swedencentral"
    region = calc_region(region_az)                        # raises on unsupported
    dr_az = engagement.get("dr_region") or (design or {}).get("dr_region")
    dr_region = calc_region(dr_az) if dr_az else None

    currency = (engagement.get("currency") or "USD").upper()
    lic = (engagement.get("licensing_program") or "MCA").upper()

    skipped: list[dict] = []
    lines: list[dict] = []
    internal = 0.0

    if _has_rows(compute):
        vm, disk, c_int = _compute_lines(compute, region, skipped)
        lines += vm + disk
        internal += c_int
    else:
        skipped.append({"what": "workload compute + managed disks",
                        "why": "estimate_compute_cost output not supplied"})

    if _has_rows(storage):
        st, s_int = _storage_lines(storage, region, skipped)
        lines += st
        internal += s_int

    plat, p_int = _platform_lines(design or {}, region, run_rate or {}, skipped)
    lines += plat
    internal += p_int

    if dr_region:
        dr_lines, dr_int = _dr_lines(design or {}, compute or {}, dr_region,
                                     include_dr_compute, skipped)
        lines += dr_lines
        internal += dr_int

    if lic not in ("MCA",):
        skipped.append({"what": f"licensing program {lic}",
                        "why": "anonymous calculator only prices MCA; EA/CSP need "
                               "an authenticated Save (E11.19) — spec keeps the "
                               "request, ca-calc falls back to MCA"})

    return {
        "engagement": _eid(engagement),
        "estimate_name": f"{cust} — {proj} — Azure Landing Zone (POE)",
        "currency": currency,
        "licensing_program": lic,
        "licensing_program_calc": _CALC_LICENSING.get(lic, "mca"),
        "region_default": region,
        "region_azure": _norm_region(region_az),
        "dr_region_default": dr_region,
        "generated_on": generated_on,
        "line_items": lines,
        "skipped": skipped,
        "internal_monthly_estimate": round(internal, 2),
        "provenance": {
            "design": bool(design), "compute": _has_rows(compute),
            "storage": _has_rows(storage), "run_rate": bool(run_rate),
            "note": "quantities are Landfall figures; the Azure Pricing Calculator "
                    "supplies all prices. internal_monthly_estimate is Landfall's "
                    "own number, for the post-export reconciliation check.",
        },
    }


# --------------------------------------------------------------------------
# line-item builders
# --------------------------------------------------------------------------
def _compute_lines(compute: dict, region: str, skipped: list) -> tuple[list, list, float]:
    term = str(compute.get("reserved_term", "none")).lower()
    billing = _TERM_TO_BILLING.get(term, "payg")
    items = [x for x in compute.get("line_items", []) if isinstance(x, dict)]

    # VMs: group by (size, os, ahb) -> one calculator module with count = servers
    vm_groups: dict[tuple, dict] = {}
    disk_groups: dict[str, int] = {}
    internal = 0.0
    for x in items:
        sku = x.get("sku")
        if not sku:
            skipped.append({"what": f"server {x.get('server_id')}",
                            "why": "no recommended SKU (right-sizer produced none)"})
            continue
        ahb = bool(x.get("ahb_applied"))
        os_ = "windows" if (x.get("os") == "windows" or ahb) else "linux"
        key = (vm_size_slug(sku), os_, ahb)
        g = vm_groups.setdefault(key, {"sku": sku, "count": 0, "servers": []})
        g["count"] += 1
        g["servers"].append(x.get("server_id"))
        internal += float(x.get("total_monthly") or 0)

        tier = x.get("disk_tier")
        if tier:
            disk_groups[tier] = disk_groups.get(tier, 0) + 1

    vm_lines = []
    for (slug, os_, ahb), g in sorted(vm_groups.items()):
        cat, series = _vm_family_meta(g["sku"])
        vm_lines.append({
            "service": "virtual-machines",
            "region": region,
            "config": {
                "operatingSystem": os_,
                "type": "os-only",
                "tier": "standard",
                "category": cat,
                "instanceSeries": series,
                "size": slug,
                "size_name": vm_size_name(g["sku"]),
                "count": g["count"],
                "hours": _HOURS_MONTH,
                "computeBillingOption": billing,
                "osBillingOption": "ahb" if ahb else "payg",
            },
            "note": (f"{g['count']}x {vm_size_name(g['sku'])} "
                     f"({'Windows/AHB' if ahb else os_}) — right-sized workloads "
                     f"({term} reserved)" if billing != "payg"
                     else f"{g['count']}x {vm_size_name(g['sku'])} "
                          f"({'Windows/AHB' if ahb else os_}) — right-sized workloads"),
        })

    disk_lines = []
    for tier, n in sorted(disk_groups.items()):
        disk_lines.append({
            "service": "managed-disks",
            "region": region,
            "config": {
                "tier": "prem-ssd" if tier.upper().startswith("P") else "standard-ssd",
                "size": tier.lower(),
                "size_name": tier.upper(),
                "count": n,
                "unit": "disks",
            },
            "note": f"{n}x {tier.upper()} managed OS/data disk — one per VM",
        })

    return vm_lines, disk_lines, internal


def _storage_lines(storage: dict, region: str, skipped: list) -> tuple[list, float]:
    by_cat: dict[str, dict] = {}
    internal = 0.0
    for x in storage.get("line_items", []):
        if not isinstance(x, dict):
            continue
        cat = x.get("category")
        g = by_cat.setdefault(cat, {"gb": 0.0, "volumes": 0, "monthly": 0.0})
        g["gb"] += float(x.get("size_gb") or 0)
        g["volumes"] += 1
        g["monthly"] += float(x.get("monthly") or 0)
        internal += float(x.get("monthly") or 0)

    out = []
    for cat, g in sorted(by_cat.items()):
        mod = _STORAGE_MODULE.get(cat)
        if not mod or not mod[0]:
            skipped.append({"what": f"{cat} storage ({g['gb']:.0f} GB)",
                            "why": "no direct Azure Pricing Calculator module "
                                   "(price separately / replatform decision)"})
            continue
        service, base = mod
        cfg = dict(base)
        cfg["capacity_gb"] = round(g["gb"], 1)
        cfg["region"] = region
        out.append({
            "service": service,
            "region": region,
            "config": cfg,
            "note": f"{g['volumes']} volume(s), {g['gb']:.0f} GB — {cat.replace('_', ' ')}",
        })
    return out, internal


def _platform_lines(design: dict, region: str, run_rate: dict, skipped: list) -> tuple[list, float]:
    """Hub / shared landing-zone platform. `design['hub']['components']` is a list
    of human strings; map the priceable ones to calculator modules. Quantities
    lean on the design (spoke count, regulated flag) + run_rate (egress GB)."""
    hub = (design.get("hub") or {})
    components = " | ".join(hub.get("components", [])).lower()
    conn = str((design.get("connectivity") or {}).get("model", "")).lower() or components
    spokes = len(design.get("spokes") or []) or 4
    regulated = bool(design.get("regulated"))
    out: list[dict] = []

    egress_gb = 0.0
    rr = (run_rate.get("run_rate_monthly") or {})
    if isinstance(rr.get("egress"), dict):
        egress_gb = float(rr["egress"].get("billable_gb")
                          or rr["egress"].get("net_out_gb_30d") or 0)
    egress_gb = round(egress_gb or 2048.0, 0)

    if "bastion" in components:
        out.append(_line("azure-bastion", region,
                         {"tier": "standard", "hours": _HOURS_MONTH, "scale_units": 2,
                          "outbound_data_gb": 5},
                         "Azure Bastion (Standard) for admin access to the hub"))

    if "expressroute" in conn:
        out.append(_line("expressroute", region,
                         {"gateway": "erGw1AZ", "hours": _HOURS_MONTH,
                          "circuit": "metered", "circuit_bandwidth_mbps": 1000},
                         "ExpressRoute gateway (ErGw1AZ). Circuit port/bandwidth "
                         "is often carrier-billed — confirm with the customer."))
    if "vpn" in conn:
        out.append(_line("vpn-gateway", region,
                         {"tier": "vpngw1az", "hours": _HOURS_MONTH,
                          "s2s_tunnels": 1, "p2s_connections": 0},
                         "VPN gateway (VpnGw1AZ) — backup / seeding path"))

    if "firewall" in components:
        premium = "premium" in components
        out.append(_line("azure-firewall", region,
                         {"tier": "premium" if premium else "standard",
                          "deployments": 1, "hours": _HOURS_MONTH,
                          "data_processed_gb": max(egress_gb, 1024)},
                         f"Azure Firewall {'Premium' if premium else 'Standard'} "
                         f"(forced-tunnel egress), ~{max(egress_gb,1024):.0f} GB/mo processed"))

    if regulated or "ddos" in components:
        out.append(_line("ddos-protection-plan", region,
                         {"plans": 1, "protected_public_ips": max(spokes, 5)},
                         "DDoS Network Protection plan (regulated workloads present)"))

    if "dns" in components:
        out.append(_line("azure-dns", region,
                         {"public_zones": 1, "private_zones": max(spokes + 1, 3),
                          "queries_millions": 5},
                         f"Azure DNS — 1 public + {max(spokes+1,3)} private zones "
                         "(Private DNS Resolver priced separately if used)"))

    # identity: AD DCs in the hub
    ident = str(design.get("identity", {}).get("model")
                or design.get("connectivity", {}).get("model") or "").lower()
    if "extend_ad" in components or "domain controller" in components or "extend_ad" in ident:
        out.append(_line("virtual-machines", region,
                         {"operatingSystem": "windows", "type": "os-only",
                          "tier": "standard", "category": "General purpose",
                          "instanceSeries": "Dsv5-series", "size": "d2sv5",
                          "size_name": "D2s v5", "count": 2, "hours": _HOURS_MONTH,
                          "computeBillingOption": "three-year", "osBillingOption": "ahb"},
                         "2x AD Domain Controllers (D2s v5, Windows/AHB) — new AD site"))

    # management: Log Analytics + Key Vault
    la_gb = 0.0
    if isinstance(rr.get("monitoring"), dict):
        la_gb = float(rr["monitoring"].get("log_analytics_gb_month") or 0)
    la_gb = round(la_gb or (spokes * 30.0), 0)
    out.append(_line("azure-monitor", region,
                     {"log_data_ingestion_gb": la_gb, "interactive_retention_months": 3,
                      "basic_logs_gb": 0},
                     f"Azure Monitor / Log Analytics — ~{la_gb:.0f} GB/mo ingestion, 3-mo retention"))
    out.append(_line("key-vault", region,
                     {"vault_type": "standard", "operations_10k": 20,
                      "certificate_renewals": 5},
                     "Azure Key Vault (Standard) — platform secrets / CMK"))

    out.append(_line("bandwidth", region,
                     {"internet_egress_gb": egress_gb, "source_region": region},
                     f"Internet egress — ~{egress_gb:.0f} GB/mo (from run-rate)"))

    return out, 0.0   # platform lines carry no internal $ — the calculator prices them


def _dr_lines(design: dict, compute: dict, dr_region: str,
              include_dr_compute: bool, skipped: list) -> tuple[list, float]:
    out: list[dict] = []
    tiers = (design.get("dr") or {}).get("apps_by_tier") or {}
    protected = sum(v for k, v in tiers.items() if str(k) in ("1", "2"))
    if not protected:
        # fall back: count servers if the design didn't roll tiers up
        protected = sum(1 for x in compute.get("line_items", []) if isinstance(x, dict)) or 0
    if protected:
        out.append(_line("azure-site-recovery", dr_region,
                         {"protected_instances": protected,
                          "target": "azure", "source": "azure"},
                         f"Azure Site Recovery — {protected} tier-1/2 instances "
                         f"replicating to {dr_region}"))
    if include_dr_compute:
        for x in compute.get("line_items", []):
            pass  # explicit DR compute build-out — left for a later cycle
        skipped.append({"what": "warm DR compute in " + dr_region,
                        "why": "include_dr_compute set but per-instance DR build-out "
                               "is not implemented yet (C25+); ASR line covers "
                               "replication storage"})
    else:
        skipped.append({"what": "warm DR compute in " + dr_region,
                        "why": "DR runs on failover only — no standing DR VMs priced "
                               "(set include_dr_compute for a warm-standby POE)"})
    return out, 0.0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _line(service: str, region: str, config: dict, note: str) -> dict:
    return {"service": service, "region": region, "config": config, "note": note}


def _has_rows(d: dict | None) -> bool:
    return bool(isinstance(d, dict) and d and "error" not in d and d.get("line_items"))


def _norm_region(name: str) -> str:
    return re.sub(r"[\s_-]", "", (name or "").strip().lower())


def _eid(engagement: dict) -> str:
    if engagement.get("engagement"):
        return str(engagement["engagement"])
    c = _slug(engagement.get("customer") or engagement.get("display") or "")
    p = _slug(engagement.get("project") or "")
    return f"{c}/{p}" if c and p else "_default_/_default_"


def _slug(v: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (v or "").strip().lower()).strip("-")
    return s[:40]
