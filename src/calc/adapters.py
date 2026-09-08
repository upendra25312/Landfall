"""
Per-product adapters for the Azure Pricing Calculator (PRD E11.16).

Each adapter knows two things about one calculator product module:

  * `product`    — the text to search for in the product picker
  * `fields(cfg)`— given a spec line-item's `config`, return an ordered list of
                   (control-name, value, kind) tuples to apply to the newest
                   module.  kind ∈ {"select", "number", "text", "radio", "typeahead"}

The driver adds the product, then applies the fields with the native-setter +
input/change trick (verified against the live calculator 2026-09-08). A control
that can't be found is logged and skipped — the line item degrades to
`skipped[]`, never a wrong price.

VIRTUAL_MACHINES and MANAGED_DISKS were verified end-to-end. The platform
adapters below are built from the observed module shape and are checked by the
weekly Playwright smoke (E11.19); until an adapter is confirmed it sets what it
can and the line still reflects the real calculator's default for anything it
misses.
"""
from __future__ import annotations

# region name is applied by the driver to select[name=region] for every module.

def _vm_fields(c: dict) -> list[tuple]:
    f: list[tuple] = [
        ("operatingSystem", c.get("operatingSystem", "windows"), "select"),
        ("type", c.get("type", "os-only"), "select"),
        ("tier", c.get("tier", "standard"), "select"),
    ]
    if c.get("category"):
        f.append(("category", c["category"], "select"))
    # instance: typeahead on input[name=size]; fall back to the human name
    f.append(("size", c.get("size") or c.get("size_name", ""), "typeahead"))
    f.append(("count", c.get("count", 1), "number"))
    f.append(("hours", c.get("hours", 730), "number"))
    if c.get("computeBillingOption"):
        f.append(("__radio_computeBillingOption", c["computeBillingOption"], "radio"))
    if c.get("osBillingOption"):
        f.append(("__radio_osBillingOption", c["osBillingOption"], "radio"))
    return f


def _disk_fields(c: dict) -> list[tuple]:
    return [
        ("managedDisksTier", c.get("tier", "prem-ssd"), "select"),
        ("size", c.get("size") or c.get("size_name", ""), "typeahead"),
        ("count", c.get("count", 1), "number"),
    ]


def _passthrough(keys: list[str], defaults: dict | None = None):
    defaults = defaults or {}

    def _f(c: dict) -> list[tuple]:
        out = []
        for k in keys:
            v = c.get(k, defaults.get(k))
            if v is None:
                continue
            kind = "number" if isinstance(v, (int, float)) else "select"
            out.append((k, v, kind))
        return out
    return _f


# product-search text -> adapter
ADAPTERS: dict[str, dict] = {
    "virtual-machines":  {"product": "Virtual Machines", "fields": _vm_fields,
                          "verified": True},
    "managed-disks":     {"product": "Managed Disks", "fields": _disk_fields,
                          "verified": True},
    "storage-accounts":  {"product": "Storage Accounts",
                          "fields": _passthrough(["type", "tier", "access", "redundancy", "capacity_gb"]),
                          "verified": False},
    "azure-netapp-files": {"product": "Azure NetApp Files",
                           "fields": _passthrough(["service_level", "capacity_gb"]),
                           "verified": False},
    "sql-managed-instance": {"product": "Azure SQL Managed Instance",
                             "fields": _passthrough(["tier", "vcores", "storage_gb", "capacity_gb"]),
                             "verified": False},
    "sql-database":      {"product": "Azure SQL Database",
                          "fields": _passthrough(["tier", "vcores", "capacity_gb"]),
                          "verified": False},
    "azure-database-for-postgresql": {"product": "Azure Database for PostgreSQL",
                                      "fields": _passthrough(["tier", "component", "capacity_gb"]),
                                      "verified": False},
    "azure-database-for-mysql": {"product": "Azure Database for MySQL",
                                 "fields": _passthrough(["tier", "component", "capacity_gb"]),
                                 "verified": False},
    "bandwidth":         {"product": "Bandwidth",
                          "fields": _passthrough(["internet_egress_gb"]),
                          "verified": False},
    "vpn-gateway":       {"product": "VPN Gateway",
                          "fields": _passthrough(["tier", "hours", "s2s_tunnels", "p2s_connections"]),
                          "verified": False},
    "expressroute":      {"product": "Azure ExpressRoute",
                          "fields": _passthrough(["gateway", "circuit", "circuit_bandwidth_mbps", "hours"]),
                          "verified": False},
    "azure-firewall":    {"product": "Azure Firewall",
                          "fields": _passthrough(["tier", "deployments", "hours", "data_processed_gb"]),
                          "verified": False},
    "azure-bastion":     {"product": "Azure Bastion",
                          "fields": _passthrough(["tier", "hours", "scale_units", "outbound_data_gb"]),
                          "verified": False},
    "ddos-protection-plan": {"product": "DDoS Protection",
                             "fields": _passthrough(["plans", "protected_public_ips"]),
                             "verified": False},
    "azure-dns":         {"product": "Azure DNS",
                          "fields": _passthrough(["public_zones", "private_zones", "queries_millions"]),
                          "verified": False},
    "azure-monitor":     {"product": "Azure Monitor",
                          "fields": _passthrough(["log_data_ingestion_gb", "interactive_retention_months", "basic_logs_gb"]),
                          "verified": False},
    "key-vault":         {"product": "Key Vault",
                          "fields": _passthrough(["vault_type", "operations_10k", "certificate_renewals"]),
                          "verified": False},
    "load-balancer":     {"product": "Load Balancer",
                          "fields": _passthrough(["tier", "rules", "data_processed_gb"]),
                          "verified": False},
    "application-gateway": {"product": "Application Gateway",
                            "fields": _passthrough(["tier", "hours", "capacity_units", "data_processed_gb"]),
                            "verified": False},
    "azure-site-recovery": {"product": "Azure Site Recovery",
                            "fields": _passthrough(["protected_instances", "target", "source"]),
                            "verified": False},
}


def adapter_for(service: str) -> dict | None:
    return ADAPTERS.get((service or "").strip().lower())
