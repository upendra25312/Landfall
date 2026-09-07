"""Cycle 6 — estimate_run_rate_extras (E2.4). Pure; all rates from config."""
import csv
import io

from conftest import sample_bytes

from cost.config import load_config
from cost.run_rate import estimate_run_rate_extras


def _cfg(**extras):
    return load_config(overrides={"extras": extras} if extras else None)


SRV = [
    {"server_id": "a", "used_disk_gb": 200, "net_out_gb_30d": 500, "powerstate": "poweredOn"},
    {"server_id": "b", "used_disk_gb": 300, "net_out_gb_30d": 1000, "powerstate": "poweredOn"},
    {"server_id": "c", "used_disk_gb": 100, "net_out_gb_30d": 50, "powerstate": "poweredOff"},
]


def test_powered_off_servers_excluded():
    r = estimate_run_rate_extras(SRV, 0, _cfg())
    assert r["servers_counted"] == 2
    assert r["servers_excluded_powered_off"] == 1
    assert r["run_rate_monthly"]["backup"]["protected_data_gb"] == 500.0   # a + b only


def test_backup_fee_is_storage_plus_instance():
    cfg = _cfg(backup={"enabled": True, "backup_size_factor": 2.0,
                       "vault_storage_usd_gb_month": 0.02, "protected_instance_usd_month": 5.0})
    r = estimate_run_rate_extras(SRV, 0, cfg)
    bk = r["run_rate_monthly"]["backup"]
    assert bk["vault_storage_gb"] == 1000.0                    # 500 * 2.0
    assert bk["storage_fee"] == 20.0                           # 1000 * 0.02
    assert bk["protected_instance_fee"] == 10.0                # 2 * 5
    assert bk["monthly"] == 30.0


def test_egress_applies_internet_fraction_and_free_tier():
    cfg = _cfg(egress={"free_gb_month": 100, "usd_per_gb": 0.10,
                       "internet_fraction_of_net_out": 0.5})
    r = estimate_run_rate_extras(SRV, 0, cfg)
    eg = r["run_rate_monthly"]["egress"]
    assert eg["internet_gb_month"] == 750.0                    # (500+1000) * 0.5
    assert eg["billable_gb"] == 650.0                          # - 100 free
    assert eg["monthly"] == 65.0


def test_monitoring_defender_toggle():
    on = estimate_run_rate_extras(SRV, 0, _cfg(
        monitoring={"log_analytics_gb_per_server_day": 1.0, "log_analytics_usd_gb": 2.0,
                    "defender_for_servers": True, "defender_usd_server_month": 10.0}))
    off = estimate_run_rate_extras(SRV, 0, _cfg(
        monitoring={"log_analytics_gb_per_server_day": 1.0, "log_analytics_usd_gb": 2.0,
                    "defender_for_servers": False, "defender_usd_server_month": 10.0}))
    m_on = on["run_rate_monthly"]["monitoring"]
    assert m_on["log_analytics_gb_month"] == 60.0              # 2 servers * 1 * 30
    assert m_on["log_analytics_monthly"] == 120.0
    assert m_on["defender_monthly"] == 20.0
    assert off["run_rate_monthly"]["monitoring"]["defender_monthly"] == 0.0


def test_support_plan_flat_rate():
    r = estimate_run_rate_extras(SRV, 0, _cfg(support={"plan": "prodirect",
                                                       "flat_usd_month": {"prodirect": 1000}}))
    assert r["run_rate_monthly"]["support"]["monthly"] == 1000.0
    r2 = estimate_run_rate_extras(SRV, 0, _cfg(support={"plan": "none", "flat_usd_month": {}}))
    assert r2["run_rate_monthly"]["support"]["monthly"] == 0.0


def test_one_time_tooling_zero_within_free_window():
    cfg = _cfg(one_time={"migration_tooling_free_days": 180,
                         "migration_tooling_usd_server_month": 25.0,
                         "avg_migration_months_per_server": 3,
                         "replication_egress_usd_per_gb": 0.0,
                         "dual_run_overlap_months": 0, "dual_run_fraction_of_infra": 0})
    r = estimate_run_rate_extras(SRV, 100000, cfg)
    assert r["one_time"]["migration_tooling"]["cost"] == 0.0   # 3 months < 6 months free
    assert r["one_time"]["total"] == 0.0


def test_one_time_dual_run_scales_with_infra():
    cfg = _cfg(one_time={"migration_tooling_free_days": 180, "avg_migration_months_per_server": 3,
                         "migration_tooling_usd_server_month": 25.0,
                         "replication_egress_usd_per_gb": 0.0,
                         "dual_run_overlap_months": 2, "dual_run_fraction_of_infra": 0.5})
    r = estimate_run_rate_extras(SRV, 100000, cfg)
    assert r["one_time"]["dual_run"]["cost"] == 100000.0       # 100k * 0.5 * 2
    assert r["one_time"]["total"] == 100000.0


def test_totals_reconcile():
    r = estimate_run_rate_extras(SRV, 50000, _cfg())
    rr = r["run_rate_monthly"]
    assert rr["total_monthly"] == round(
        rr["backup"]["monthly"] + rr["egress"]["monthly"]
        + rr["monitoring"]["monthly"] + rr["support"]["monthly"], 2)
    t = r["totals"]
    assert t["run_rate_annual"] == round(t["run_rate_monthly"] * 12, 2)
    assert t["first_year_extras"] == round(t["run_rate_monthly"] * 12 + t["one_time"], 2)


def test_deterministic_over_sample():
    rows = list(csv.DictReader(io.StringIO(sample_bytes("servers.csv").decode("utf-8-sig"))))
    a = estimate_run_rate_extras(rows, 103000, _cfg())
    b = estimate_run_rate_extras(rows, 103000, _cfg())
    assert a == b
    assert a["servers_counted"] == 233                         # 250 - 17 powered off
    assert a["totals"]["run_rate_monthly"] > 0
