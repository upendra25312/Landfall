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
    "disposition": {
        # score_dispositions (E4.2) — rule-derived 6R candidate per application.
        "appetite": "rehost_first",           # rehost_first | replatform_where_easy | aggressive
        "paas_db_engines": {                  # engine substring -> PaaS target
            "postgresql": "Azure Database for PostgreSQL Flexible Server",
            "postgres": "Azure Database for PostgreSQL Flexible Server",
            "mysql": "Azure Database for MySQL Flexible Server",
            "mariadb": "Azure Database for MySQL Flexible Server",
            "sql server": "Azure SQL Managed Instance",
        },
        "clustered_markers": ["always on", "always-on", "availability group", "data guard",
                              "rac", "patroni", "galera", "wsfc", "replica set"],
        "container_markers": ["docker", "kubernetes", "k8s", "containerd", "openshift"],
        "repurchase_markers": {               # name / stack substring -> SaaS category
            "learning management": "SaaS LMS",
            "collaboration": "SharePoint Online / Teams",
        },
        "retire_markers": ["sandbox", "proof of concept", "poc", "decommission",
                           "to be retired", "print & output", "print and output",
                           "legacy billing (frozen)"],
        "replatform_min_criticality": 3,      # only tier 3+ (lower-criticality) apps replatform; tier 1-2 stay IaaS
        "replatform_max_servers": 6,
        "allow_refactor": False,
    },
    "waves": {
        # plan_waves (E4.1) — dependency graph -> affinity move-groups -> risk-ordered waves.
        "min_edge_confidence": "low",         # low | medium | high — edges below this are dropped
        "stale_after_days": 21,               # a flow not seen in this many days is excluded (flagged)
        "observation_window_end": None,       # ISO date; default = max last_seen in the data
        "max_servers_per_wave": 40,
        "max_apps_per_wave": 6,
        # platform / commodity services (AD, DNS, NTP, Kerberos, monitoring) — every app
        # depends on them, so they don't form affinity groups; they migrate in the pilot wave.
        "commodity_protocols": ["LDAP", "LDAPS", "DNS", "NTP", "KERBEROS", "SMB", "CIFS", "SNMP"],
        "commodity_ports": [53, 88, 123, 137, 138, 139, 389, 445, 636, 3268, 3269, 514, 161],
        "infra_app_markers": ["infrastructure", "shared services", "shared-infra",
                              "platform services", "active directory", "domain services"],
        "regulated_scopes_last": ["PCI-DSS", "PCI", "HIPAA", "HITRUST"],
        "risk_weights": {                    # contribution to the 0-100 group risk score
            "criticality": 40, "internet_facing": 12, "compliance": 22,
            "size": 14, "eol_os": 6, "change": 10, "data_quality": 8,
        },
    },
    "schedule": {
        # build_schedule (E4.3) — the wave plan -> a dated schedule + critical path.
        "throughput_servers_per_week": 12,     # migrated + soaked per wave per week
        "wave_prep_weeks": 2,                   # runbook, spoke hardening, rehearsal
        "wave_soak_weeks": 1,                   # steady-state watch before the wave clears
        "min_wave_weeks": 2,                    # floor on execution regardless of size
        "gap_weeks_between_waves": 1,           # breather between consecutive waves on a lane
        "parallel_waves": 1,                    # wave execution windows running at once
        "mobilisation_weeks": 3,                # before wave 1; LZ build overlaps this
        "programme_hypercare_weeks": 4,         # after the last wave
        "blackout_windows": [],                 # [{"name","start":"YYYY-MM-DD","end":"YYYY-MM-DD"}]
        "default_start": None,                  # ISO date; None => next Monday from the run date
    },
    "effort": {
        # estimate_effort (E6.2, used by assemble_estimate) — parametric person-days.
        "bands_pd": {"S": 8, "M": 14, "L": 22, "XL": 40},
        "assessment_pd_per_server": 0.15,
        "assessment_pd_per_app": 1.5,
        "rehost_pd_per_server": 0.5,
        "execution_pd_per_app": {              # disposition -> PD per application
            "Rehost": 4, "Replatform": 16, "Repurchase": 6,
            "Retire": 1, "Retain": 0, "Refactor": 30,
        },
        "mobilisation_pd": 10,
        "landing_zone_pd": 45,                 # base ALZ build
        "landing_zone_pd_per_spoke": 3,
        "regulated_spoke_controls_pd": 20,     # added when the portfolio has a regulated scope
        "testing_pd_per_app": 2.5,
        "cutover_pd_per_wave": 3,
        "hypercare_pd_per_month": 15,
        "hypercare_months": 2,
        "pm_pct": 15,
        "governance_pct": 10,
        "contingency_pct": None,               # None => derive from the data-quality confidence
        "contingency_by_confidence": {"High": 8, "Medium": 12, "Low": 20},
        "working_days_per_month": 21,           # E6.2 resource loading — FTE = PD / this
    },
    "rates": {
        "blended_day_rate": 780,
        "currency": "USD",
    },
    "deliverable": {
        # assemble_estimate (E5) — the estimate package.
        "firm_name": None,                     # optional, printed on the cover
        "watermark": "DRAFT — architect review required before external issue",
        "sections": ["current_state", "landing_zone", "disposition", "waves",
                     "run_rate_cost", "migration_effort", "assumptions_register", "next_steps"],
        "top_cost_drivers": 3,                 # E2.5 — how many drivers to surface per cost total
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
