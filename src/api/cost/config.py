"""
Load the firm's estimation config over documented defaults (PRD E6.1).

Resolution order for the file:
  1. explicit path passed to load_config()
  2. $ESTIMATION_CONFIG
  3. estimation_config.json next to the repo root (dev / local)
Anything the file omits falls back to DEFAULTS below, so a partial file is fine.
"""
from __future__ import annotations

import copy
import json
import os

DEFAULTS: dict = {
    "pricing": {
        "region": "swedencentral",
        "currency": "USD",
        "reserved_term": "1yr",                 # none | 1yr | 3yr
        "reservation_coverage_pct": 80,
        "azure_hybrid_benefit_windows": True,
        "azure_hybrid_benefit_sql": True,
        "dev_test_pricing_nonprod": False,
    },
    "rightsize": {
        "utilisation_metric": "p95",            # p95 | peak | avg
        "cpu_target_utilisation_pct": 65,
        "ram_target_utilisation_pct": 80,
        "min_vcpu_retain_pct": 50,              # never cut below this fraction of current
        "min_ram_retain_pct": 60,
        "vcpu_floor": 2,
        "ram_floor_gb": 4,
        "headroom_band_pct": 20,                # +/- for the low/high range
        "no_perf_data": {
            "cpu_scale_pct": 100,               # 100 = keep as-is (no blind haircut)
            "ram_scale_pct": 100,
            "confidence": "low",
        },
    },
    "uplift": {
        # each server's compute cost is scaled by these for its environment.
        # 100 = same as its listed size. Set nonprod < 100 if non-prod is scaled
        # down in Azure; set dr < 100 for cold / pilot-light DR.
        "nonprod_of_prod_pct": 100,
        "dr_of_prod_pct": 100,
        "dev_test_discount_pct": 55,     # applied to dev/nonprod when dev_test_pricing_nonprod=true
    },
    "storage": {
        # estimate_storage_cost (E2.3) — the dbo.storage table (file shares, DB
        # volumes, object storage). Block / managed-disk volumes are priced by
        # estimate_compute_cost (one disk per VM) and excluded here unless
        # price_block_from_storage_table is set (then set that tool to skip disk).
        "price_block_from_storage_table": False,
        "db_growth_headroom_pct": 20,        # PaaS DB storage is provisioned above data size
        "rate_band_pct": 25,                 # +/- for the low / high range on list rates
        "min_provision_gb": {               # provisioned-capacity floors that bill anyway
            "files_premium": 100,
            "anf_standard": 4096, "anf_premium": 4096, "anf_ultra": 4096,
        },
        # USD / GB-month list rates. Approximate swedencentral list prices — refresh
        # with cost.pricing.fetch_storagebook or pin your negotiated rates here.
        "rates_usd_gb_month": {
            "files_premium": 0.1636,
            "files_standard_hot": 0.06,
            "anf_standard": 0.1466, "anf_premium": 0.2932, "anf_ultra": 0.3908,
            "db_sql_mi": 0.115,
            "db_sql_hyperscale": 0.10,
            "db_flex_postgresql": 0.115,
            "db_flex_mysql": 0.115,
            "db_oracle": 0.161,
            "blob_hot_lrs": 0.0196,
            "blob_cool_lrs": 0.0115,
            "managed_premium_ssd_v2": 0.075,   # per GiB, capacity only (excl. IOPS/throughput)
        },
    },
    "extras": {
        # estimate_run_rate_extras (E2.4) — run-rate lines beyond compute + storage,
        # plus one-time migration cost. Slow-moving list rates; pin your negotiated
        # numbers here. All USD.
        "backup": {
            "enabled": True,
            "backup_size_factor": 1.3,            # protected data GB * this = vault GB (fulls + incrementals + retention)
            "vault_storage_usd_gb_month": 0.0224, # LRS vault; GRS ~ 0.05
            "protected_instance_usd_month": 5.0,  # per protected VM (Azure Backup, <500 GB band)
        },
        "egress": {
            "free_gb_month": 100,
            "usd_per_gb": 0.05,                   # blended internet egress after the free tier
            "internet_fraction_of_net_out": 0.30, # share of net_out_gb_30d that leaves Azure for the internet
        },
        "monitoring": {
            "log_analytics_gb_per_server_day": 0.5,   # syslog + perf counters (not verbose VM insights)
            "log_analytics_usd_gb": 2.30,             # pay-as-you-go; commitment tiers discount 15-30%
            "defender_for_servers": True,
            "defender_usd_server_month": 15.0,        # Defender for Servers Plan 2
        },
        "support": {
            "plan": "standard",                  # none | developer | standard | prodirect
            "flat_usd_month": {"developer": 29, "standard": 100, "prodirect": 1000},
        },
        "one_time": {
            "migration_tooling_free_days": 180,          # Azure Migrate / ASR free window per server
            "migration_tooling_usd_server_month": 25.0,  # after the free window
            "avg_migration_months_per_server": 3,
            "replication_egress_usd_per_gb": 0.0,        # on-prem -> Azure is ingress (free); set >0 for cross-cloud
            "dual_run_overlap_months": 1.5,             # months on-prem + Azure run in parallel during cutover
            "dual_run_fraction_of_infra": 0.5,         # fraction of the monthly infra bill incurred twice
        },
    },
    "effort": {
        "bands_pd": {"S": 8, "M": 14, "L": 22, "XL": 40},
        "assessment_pd_per_server": 0.15,
        "assessment_pd_per_app": 1.5,
        "rehost_pd_per_server": 0.5,
        "pm_pct": 15,
        "governance_pct": 10,
        "contingency_pct": None,                # None => derive from the data-quality score
    },
    "rates": {
        "blended_day_rate": 780,
        "currency": "USD",
    },
    "landing_zone": {
        # design_landing_zone (E3) — the ALZ is derived from the app portfolio; these
        # are the engagement's platform choices, not the topology itself.
        "org_id": "alz",                       # intermediate-root MG / naming prefix
        "primary_region": "swedencentral",
        "dr_region": "westeurope",
        "ip_supernet": "10.100.0.0/14",
        "dr_ip_supernet": "10.104.0.0/14",
        "hub_prefix": 22,                       # hub VNet size within the supernet
        "spoke_prefix": 22,                     # each spoke VNet size
        "connectivity": "expressroute+vpn",    # expressroute | vpn | expressroute+vpn
        "identity_model": "extend_ad",          # extend_ad | greenfield_entra | entra_domain_services
        "forced_tunnel_egress": True,           # spoke 0.0.0.0/0 -> hub Azure Firewall
        "prod_availability_zones": True,
        "environments": ["prod", "nonprod"],   # env spokes built per zone
        # compliance scopes that earn a dedicated spoke + Confidential MG + policy overlay
        "regulated_scopes": ["PCI-DSS", "PCI", "HIPAA", "HITRUST", "IRAP",
                             "FedRAMP", "CJIS", "ITAR"],
        "policy_baseline": ["Azure Landing Zones default", "Microsoft Cloud Security Benchmark",
                            "CIS Azure Foundations Benchmark v2.0"],
        "resiliency_tiers": {
            "1": {"rpo": "15 min", "rto": "2 h",  "pattern": "zone-redundant + cross-region replication (ASR / native DB)"},
            "2": {"rpo": "1 h",   "rto": "8 h",  "pattern": "zone-redundant + cross-region ASR"},
            "3": {"rpo": "24 h",  "rto": "48 h", "pattern": "zonal + Azure Backup restore"},
            "4": {"rpo": "24 h",  "rto": "5 d",  "pattern": "Azure Backup restore only"},
        },
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if k.startswith("$"):
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _repo_config() -> str | None:
    roots = [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]
    for root in roots:
        for up in range(5):
            cand = os.path.join(root, *([".."] * up), "estimation_config.json")
            if os.path.exists(cand):
                return os.path.abspath(cand)
    return None


def load_config(path: str | None = None, overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    env = os.environ.get("ESTIMATION_CONFIG")
    if not path and env and env.lstrip().startswith("{"):
        # ESTIMATION_CONFIG may hold the JSON inline (handy as a Function app setting)
        try:
            _deep_merge(cfg, json.loads(env))
            cfg["_source"] = "ESTIMATION_CONFIG (inline)"
        except json.JSONDecodeError as exc:
            cfg["_source"] = f"defaults (bad inline ESTIMATION_CONFIG: {exc})"
    else:
        p = path or env or _repo_config()
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    _deep_merge(cfg, json.load(fh))
                cfg["_source"] = p
            except (OSError, json.JSONDecodeError) as exc:
                cfg["_source"] = f"defaults (could not read {p}: {exc})"
        else:
            cfg["_source"] = "defaults (no estimation_config.json found)"
    if overrides:
        _deep_merge(cfg, overrides)
    return cfg
