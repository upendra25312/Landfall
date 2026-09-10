"""
Per-product adapters for the Azure Pricing Calculator (PRD E11.16 / E11.19).

Each adapter maps one Landfall spec line-item (`service` + `config`) onto the
real controls of one calculator product module:

  * ``product``      — the text typed into the product picker to add the module
  * ``fields(cfg)``  — an ordered list of ``(control, value, kind)`` tuples the
                       driver applies to that module.
                       kind ∈ {"select", "number", "radio", "typeahead", "accordion"}
                       - "accordion": ``control`` is button text to click first
                         (reveals a collapsed sub-panel), ``value`` is ignored.
  * ``verified``     — True once every control name + option value below was
                       confirmed against the live calculator DOM. Confirmed
                       2026-09-09 for the set marked True; the weekly Playwright
                       smoke (E11.19) re-checks them and drops a broken adapter's
                       line item into ``skipped[]`` rather than mispricing it.

Control names / option values were captured from the live calculator on
2026-09-09 by adding every module and dumping each ``.row.product-module``.
"""
from __future__ import annotations

_HOURS_MONTH = 730


def _num(v):
    """Calculator number inputs want a bare number; keep ints int."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() else round(f, 2)


def _pick(v, table, default):
    return table.get(str(v).strip().lower(), default)


# --------------------------------------------------------------------------
# compute
# --------------------------------------------------------------------------
_LINUX_DISTRO = {
    "ubuntu": "ubuntu", "ubuntu-pro": "ubuntu-pro", "ubuntu pro": "ubuntu-pro",
    "debian": "ubuntu", "linux": "ubuntu", "centos": "ubuntu", "": "ubuntu",
    "rhel": "redhat", "red hat": "redhat", "redhat": "redhat",
    "rhel-ha": "rhel-ha", "rhel ha": "rhel-ha",
    "sles": "sles-enterprise", "suse": "sles-enterprise", "sles-enterprise": "sles-enterprise",
}


def _vm_fields(c: dict) -> list[tuple]:
    os_ = _pick(c.get("operatingSystem") or c.get("os"),
                {"linux": "linux", "windows": "windows", "rhel": "linux", "ubuntu": "linux",
                 "suse": "linux", "sles": "linux", "centos": "linux", "debian": "linux"}, "windows")
    f: list[tuple] = [("operatingSystem", os_, "select")]
    if os_ == "windows":
        # Windows 'type': os-only | biztalk | sql  (os-only is the plain-Windows case)
        f.append(("type", c.get("type", "os-only"), "select"))
    else:
        # Linux 'type' is the distro; Ubuntu carries no OS surcharge (the safe default).
        f.append(("type", _pick(c.get("distro") or c.get("linux_distro") or c.get("os_detail")
                                or c.get("type") or c.get("os"), _LINUX_DISTRO, "ubuntu"), "select"))
    f.append(("tier", c.get("tier", "standard"), "select"))
    cat = _pick(c.get("category"), {
        "general purpose": "generalpurpose", "compute optimized": "computeoptimized",
        "memory optimized": "memoryoptimized", "storage optimized": "storageoptimized",
        "gpu": "gpu", "high performance compute": "highperformancecompute",
    }, None) or (c.get("category") if c.get("category") in (
        "all", "generalpurpose", "computeoptimized", "memoryoptimized",
        "storageoptimized", "gpu", "highperformancecompute") else None)
    if cat:
        f.append(("category", cat, "select"))
    f.append(("size", c.get("size") or c.get("size_name", ""), "typeahead"))
    f.append(("count", _num(c.get("count", 1)), "number"))
    f.append(("hours", _num(c.get("hours", _HOURS_MONTH)), "number"))
    if c.get("computeBillingOption"):
        f.append(("computeBillingOption", c["computeBillingOption"], "radio"))
    # Azure Hybrid Benefit (osBillingOption) is a Windows/SQL-only control — Linux
    # VM modules render no such radio, so only emit it for Windows.
    if os_ == "windows" and c.get("osBillingOption"):
        f.append(("osBillingOption", c["osBillingOption"], "radio"))
    return f


_DISK_TIER = {"prem-ssd": "premiumssd", "premium-ssd": "premiumssd", "premium ssd": "premiumssd",
              "prem-ssd-v2": "premiumssdv2", "premium-ssd-v2": "premiumssdv2",
              "standard-ssd": "standardssd", "standard ssd": "standardssd",
              "standard-hdd": "standardhdd", "standard hdd": "standardhdd",
              "ultra-ssd": "ultrassd", "ultra": "ultrassd"}


def _disk_fields(c: dict) -> list[tuple]:
    """Standalone 'Managed Disks' product. `managedDiskType` options are keyed by
    tier (p4/p6/p10… for premium SSD, e-series for std SSD, s-series for HDD)."""
    tier = _pick(c.get("tier"), _DISK_TIER, "premiumssd")
    sku = str(c.get("size") or c.get("size_name") or "p20").strip().lower()
    return [
        ("tier", tier, "select"),
        ("managedDiskType", sku, "select"),
        ("managedDisks", _num(c.get("count", 1)), "number"),
    ]


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------
_REDUNDANCY = {"lrs": "lrs", "zrs": "zrs", "grs": "grs", "ra-grs": "ra-grs",
               "gzrs": "gzrs", "ra-gzrs": "ra-gzrs"}


def _storage_fields(c: dict) -> list[tuple]:
    """Storage Accounts module — block-blob path only (Files and Managed Disks
    are their own calculator products now; see _files_fields / _disk_fields)."""
    gb = float(c.get("capacity_gb") or c.get("capacity") or 0)
    f = [
        ("type", "block-blob", "select"),
        ("performanceTier", _pick(c.get("tier"), {"premium": "premium", "standard": "standard"}, "standard"), "select"),
    ]
    if c.get("access"):
        f.append(("accessTier", _pick(c.get("access"),
                  {"hot": "hot", "cool": "cool", "cold": "cold", "archive": "archive"}, "hot"), "select"))
    f.append(("redundancy", _pick(c.get("redundancy"), _REDUNDANCY, "lrs"), "select"))
    f.append(("storageUnits", "1", "select"))         # 1 = GB (1024 = TB)
    f.append(("count", _num(round(gb)), "number"))    # capacity, in the unit above
    return f


def _files_fields(c: dict) -> list[tuple]:
    """Azure Files — provisioned v2 billing (GB provisioned). Premium (SSD) shares
    prefix the v2 controls with ``ssd``; standard (HDD) shares use the bare names.
    IOPS / throughput keep the calculator's storage-derived defaults."""
    gb = float(c.get("capacity_gb") or c.get("capacity") or 0)
    tier = _pick(c.get("tier") or c.get("service_level"),
                 {"premium": "premium", "standard": "standard"}, "premium")
    p = "ssdProvisionedV2" if tier == "premium" else "provisionedV2"
    return [
        ("performanceTier", tier, "select"),
        ("redundancy", _pick(c.get("redundancy"),
                             {"lrs": "lrs", "zrs": "zrs", "grs": "grs", "gzrs": "gzrs"}, "lrs"), "select"),
        ("billingModel", "provisionedv2", "select"),
        (f"{p}StorageFactor", "1", "select"),
        (f"{p}StorageUnits", _num(round(gb)), "number"),
    ]


_ANF_TIER = {"standard": "standard-storage", "premium": "premium-storage",
             "ultra": "ultra-storage", "flexible": "flexible-storage"}


def _anf_fields(c: dict) -> list[tuple]:
    """Azure NetApp Files — the capacity-pool controls are prefixed with the tier
    word (``premiumUnits``/``premiumHours`` for Premium Storage, etc.)."""
    tib = max(1.0, float(c.get("capacity_gb") or c.get("capacity") or 1024) / 1024.0)
    tier = _pick(c.get("service_level") or c.get("tier"), _ANF_TIER, "standard-storage")
    p = tier.split("-")[0]          # standard | premium | ultra | flexible
    f = [
        ("tier", tier, "select"),
        (f"{p}Units", _num(round(tib, 1)), "number"),
        (f"{p}Hours", _num(_HOURS_MONTH), "number"),
    ]
    bo = _pick(c.get("billing_option") or c.get("reserved"),
               {"1yr": "one-year", "1-year": "one-year", "1 year": "one-year",
                "3yr": "three-year", "3-year": "three-year", "3 years": "three-year",
                "payg": "payg"}, None)
    if bo:
        f.append((f"{p}StorageBillingOption", bo, "radio"))
    return f


# --------------------------------------------------------------------------
# databases  (all land on a "Compute" module)
# --------------------------------------------------------------------------
_MI_VCORES = [4, 8, 16, 24, 32, 40, 64, 80]
_DB_VCORES = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 32, 40, 80]


def _nearest(n, choices):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(choices[1])
    return str(min(choices, key=lambda x: abs(x - n)))


def _sql_mi_fields(c: dict) -> list[tuple]:
    f = [
        ("vcoreTier", _pick(c.get("tier"),
                            {"general-purpose": "general-purpose",
                             "business-critical": "business-critical",
                             "next-gen-general-purpose": "next-gen-general-purpose"},
                            "general-purpose"), "select"),
        ("managedInstanceType", "single-instance", "select"),
        ("generation", "gen5", "select"),
    ]
    if c.get("vcores"):
        f.append(("instanceSize", _nearest(c["vcores"], _MI_VCORES), "select"))
    f.append(("managedCount", _num(c.get("count", 1)), "number"))
    if c.get("capacity_gb"):
        # managedStorageUnits is in 32-GB increments (verified live: 512 -> "16384 GB")
        f.append(("managedStorageUnits", max(1, round(float(c["capacity_gb"]) / 32.0)), "number"))
    if c.get("reserved_term") in ("1yr", "3yr"):
        f.append(("databaseBillingOption",
                  "three-year" if c["reserved_term"] == "3yr" else "one-year", "radio"))
    if c.get("ahb"):
        f.append(("softwareBillingOption", "ahb", "radio"))
    return f


def _sql_db_fields(c: dict) -> list[tuple]:
    tier = _pick(c.get("tier"),
                 {"hyperscale": "hyperscale", "general-purpose": "general-purpose",
                  "business-critical": "business-critical"}, "general-purpose")
    f = [
        ("type", "single", "select"),
        ("purchaseModel", "vcore", "select"),
        ("vcoreTier", tier, "select"),
        ("computeTier", "provisioned", "select"),
    ]
    if c.get("vcores"):
        f.append(("instanceSize", _nearest(c["vcores"], _DB_VCORES), "select"))
    f.append(("singleCount", _num(c.get("count", 1)), "number"))
    if c.get("capacity_gb") and tier == "hyperscale":
        f.append(("singleHyperscaleStorageUnits", _num(round(float(c["capacity_gb"]))), "number"))
    return f


def _pg_fields(c: dict) -> list[tuple]:
    f = [
        ("deploymentType", "flexibleserver", "select"),
        ("tier", _pick(c.get("compute_tier"),
                       {"burstable": "burstable", "generalpurpose": "generalpurpose",
                        "memoryoptimized": "memoryoptimized"}, "burstable"), "select"),
        ("singleServers", _num(c.get("count", 1)), "number"),
    ]
    if c.get("capacity_gb"):
        f.append(("storageCount", _num(round(float(c["capacity_gb"]))), "number"))
    return f


def _mysql_fields(c: dict) -> list[tuple]:
    f = [
        ("deploymentType", "flexibleserver", "select"),
        ("tier", _pick(c.get("compute_tier"),
                       {"burstable": "burstable", "generalpurpose": "generalpurpose",
                        "memoryoptimized": "memoryoptimized"}, "burstable"), "select"),
        ("servers", _num(c.get("count", 1)), "number"),
    ]
    if c.get("capacity_gb"):
        f.append(("storageCount", _num(round(float(c["capacity_gb"]))), "number"))
    return f


# --------------------------------------------------------------------------
# networking
# --------------------------------------------------------------------------
def _bandwidth_fields(c: dict) -> list[tuple]:
    gb = float(c.get("internet_egress_gb") or c.get("outbound_data_transfer_gb") or 0)
    return [
        ("dataTransferType", "internetegress", "select"),
        ("routedVia", "microsoftglobalnetwork", "select"),
        ("internetEgressUnits", _num(round(gb)), "number"),
    ]


_VPN_TIER = {"vpngw1": "vpngw1", "vpngw1az": "vpngw1az", "vpngw2": "vpngw2",
             "vpngw2az": "vpngw2az", "vpngw3": "vpngw3", "vpngw3az": "vpngw3az",
             "vpngw4": "vpngw4", "vpngw4az": "vpngw4az", "vpngw5": "vpngw5",
             "vpngw5az": "vpngw5az", "basic": "basic"}


def _vpn_fields(c: dict) -> list[tuple]:
    return [
        ("type", "vpngateways", "select"),
        ("tier", _pick(c.get("tier"), _VPN_TIER, "vpngw1az"), "select"),
        ("gatewayHours", _num(c.get("hours", _HOURS_MONTH)), "number"),
    ]


_ER_PORT = {50: "50mbps", 100: "100mbps", 200: "200mbps", 500: "500mbps",
            1000: "1gbps", 2000: "2gbps", 5000: "5gbps", 10000: "10gbps"}
_ER_GW = {"ergw1az": "virtual-network-standard-gateway",
          "ergw2az": "virtual-network-high-performance-gateway",
          "ergw3az": "virtual-network-ultra-performance-gateway",
          "standard": "virtual-network-standard-gateway"}


def _expressroute_fields(c: dict) -> list[tuple]:
    mbps = int(c.get("circuit_bandwidth_mbps") or 1000)
    port = _ER_PORT.get(mbps) or min(_ER_PORT.items(), key=lambda kv: abs(kv[0] - mbps))[1]
    return [
        ("product", "expressRoute", "select"),
        ("plan", _pick(c.get("circuit"), {"metered": "metered", "unlimited": "unlimited"}, "metered"), "select"),
        ("portSpeed", port, "select"),
        ("gatewayValue", "virtual-network-gateways", "select"),
        ("gatewayTypeValue", _pick(c.get("gateway"), _ER_GW, "virtual-network-standard-gateway"), "select"),
        ("circuits", 1, "number"),
        ("expressRouteGatewayHours", _num(c.get("hours", _HOURS_MONTH)), "number"),
    ]


def _firewall_fields(c: dict) -> list[tuple]:
    # the numeric controls are prefixed with the selected tier: <tier>Hours, etc.
    t = _pick(c.get("tier"), {"basic": "basic", "standard": "standard", "premium": "premium"}, "standard")
    return [
        ("tier", t, "select"),
        (f"{t}DataProcessedUnits", "1", "select"),
        (f"{t}LogicalFirewallUnits", _num(c.get("deployments", 1)), "number"),
        (f"{t}Hours", _num(c.get("hours", _HOURS_MONTH)), "number"),
        (f"{t}DataProcessed", _num(round(float(c.get("data_processed_gb") or 0))), "number"),
    ]


def _bastion_fields(c: dict) -> list[tuple]:
    # controls are prefixed with the selected tier. The outbound-data-transfer
    # field renders inconsistently under automation, so it is best-effort; the
    # gateway-hours line is what dominates the Bastion cost anyway.
    t = _pick(c.get("tier"), {"basic": "basic", "standard": "standard", "premium": "premium"}, "standard")
    f = [
        ("tier", t, "select"),
        (f"{t}Hours", _num(c.get("hours", _HOURS_MONTH)), "number"),
    ]
    if t != "basic" and c.get("scale_units"):
        f.append((f"{t}AdditionalScaleUnits", _num(max(0, int(c["scale_units"]) - 2)), "number"))
    # the outbound-data-transfer control keeps the `standard` prefix for both the
    # Standard and Premium tiers; only Basic renames it.
    odt = "basic" if t == "basic" else "standard"
    f += [
        (f"{odt}OutboundDataTransferFactor", "1", "select"),
        (f"{odt}OutboundDataTransfer", _num(round(float(c.get("outbound_data_gb") or 5))), "number"),
    ]
    return f


def _ddos_fields(c: dict) -> list[tuple]:
    return [("tier", "networkprotection" if c.get("plans", 1) else "ipprotection", "select")]


def _dns_fields(c: dict) -> list[tuple]:
    # public zones use `zones`/`queries`; private zones use `privateZones`/`privateQueries`
    pub = int(c.get("public_zones") or 0)
    priv = int(c.get("private_zones") or 0)
    total = max(1, pub + priv)
    q = _num(c.get("queries_millions") or 0)
    if priv > pub:
        return [("type", "private", "select"),
                ("privateZones", total, "number"), ("privateQueries", q, "number")]
    return [("type", "public", "select"),
            ("zones", total, "number"), ("queries", q, "number")]


def _load_balancer_fields(c: dict) -> list[tuple]:
    return [
        ("tier", _pick(c.get("tier"), {"basic": "basic", "standard": "standard", "gateway": "gateway"}, "standard"), "select"),
        ("capacityFactor", "1", "select"),
        ("rules", _num(c.get("rules", 5)), "number"),
        ("capacity", _num(round(float(c.get("data_processed_gb") or 0))), "number"),
    ]


_AG_TIER = {"standard": "standard", "wafv2": "wafv2", "standard_v2": "standard",
            "waf_v2": "wafv2", "basic": "basicv2", "basicv2": "basicv2"}


def _app_gateway_fields(c: dict) -> list[tuple]:
    return [
        ("tier", _pick(c.get("tier"), _AG_TIER, "standard"), "select"),
        # V2 capacity is the maximum of compute, connections and throughput.
        # Pin the other dimensions to zero when only capacity_units is supplied.
        ("computeUnits", _num(c.get("capacity_units", 2)), "number"),
        ("persistentConnections", _num(c.get("persistent_connections", 0)), "number"),
        ("throughput", _num(c.get("throughput_mbps", 0)), "number"),
        ("hours", _num(c.get("hours", _HOURS_MONTH)), "number"),
        ("hoursFactor", "1", "select"),
        ("storageUnits", "1", "select"),
        ("units", _num(round(float(c.get("outbound_data_gb", c.get("data_processed_gb", 0))))), "number"),
    ]


# --------------------------------------------------------------------------
# management / DR
# --------------------------------------------------------------------------
def _monitor_fields(c: dict) -> list[tuple]:
    monthly = float(c.get("log_data_ingestion_gb") or 0)
    basic = float(c.get("basic_logs_gb") or 0)
    return [
        ("Log Data Ingestion", None, "accordion"),
        ("dailyLogsIngested", _num(round(monthly / 30.0, 1)), "number"),
        ("logAnalyticsRetention", _num(c.get("interactive_retention_months") or 3), "number"),
        ("basicLogsIngested", _num(round(basic / 30.0, 1)), "number"),
    ]


def _key_vault_fields(c: dict) -> list[tuple]:
    return [
        ("operations", _num(c.get("operations_10k") or 0), "number"),
        ("renewals", _num(c.get("certificate_renewals") or 0), "number"),
    ]


def _asr_fields(c: dict) -> list[tuple]:
    return [("azure", _num(c.get("protected_instances") or 0), "number")]


# product-search text -> adapter
ADAPTERS: dict[str, dict] = {
    "virtual-machines":      {"product": "Virtual Machines", "fields": _vm_fields, "verified": True},
    "managed-disks":         {"product": "Managed Disks", "fields": _disk_fields, "verified": True},
    "storage-accounts":      {"product": "Storage Accounts", "fields": _storage_fields, "verified": True},
    "azure-files":           {"product": "Azure Files", "fields": _files_fields, "verified": True},
    "azure-netapp-files":    {"product": "Azure NetApp Files", "fields": _anf_fields, "verified": True},
    "sql-managed-instance":  {"product": "Azure SQL Managed Instance", "fields": _sql_mi_fields, "verified": True},
    "sql-database":          {"product": "Azure SQL Database", "fields": _sql_db_fields, "verified": True},
    "azure-database-for-postgresql": {"product": "Azure Database for PostgreSQL", "fields": _pg_fields, "verified": True},
    "azure-database-for-mysql":      {"product": "Azure Database for MySQL", "fields": _mysql_fields, "verified": True},
    "bandwidth":             {"product": "Bandwidth", "fields": _bandwidth_fields, "verified": True},
    "vpn-gateway":           {"product": "VPN Gateway", "fields": _vpn_fields, "verified": True},
    "expressroute":          {"product": "Azure ExpressRoute", "fields": _expressroute_fields, "verified": True},
    "azure-firewall":        {"product": "Azure Firewall", "fields": _firewall_fields, "verified": True},
    "azure-bastion":         {"product": "Azure Bastion", "fields": _bastion_fields, "verified": True},
    "ddos-protection-plan":  {"product": "Azure DDoS Protection", "fields": _ddos_fields, "verified": True},
    "azure-dns":             {"product": "Azure DNS", "fields": _dns_fields, "verified": True},
    "key-vault":             {"product": "Key Vault", "fields": _key_vault_fields, "verified": True},
    "azure-site-recovery":   {"product": "Azure Site Recovery", "fields": _asr_fields, "verified": True},
    # C54: controls, non-default values and actual Excel/UI totals verified.
    "azure-monitor":         {"product": "Azure Monitor", "fields": _monitor_fields, "verified": True},
    "load-balancer":         {"product": "Load Balancer", "fields": _load_balancer_fields, "verified": True},
    "application-gateway":   {"product": "Application Gateway", "fields": _app_gateway_fields, "verified": True},
}

# spec `service` aliases -> canonical key above
_ALIASES = {
    "azure-bastion-host": "azure-bastion",
    "ddos-protection": "ddos-protection-plan",
    "ddos": "ddos-protection-plan",
    "log-analytics": "azure-monitor",
    "azure-monitor-logs": "azure-monitor",
    "postgresql": "azure-database-for-postgresql",
    "mysql": "azure-database-for-mysql",
    "anf": "azure-netapp-files",
}


def adapter_for(service: str) -> dict | None:
    key = (service or "").strip().lower()
    return ADAPTERS.get(key) or ADAPTERS.get(_ALIASES.get(key, ""))
