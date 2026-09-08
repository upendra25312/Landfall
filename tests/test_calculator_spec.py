"""E11.15 — build_calculator_spec: Landfall design/cost output -> Azure Pricing
Calculator line-item spec (no prices)."""
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))
sys.path.insert(0, os.path.join(ROOT, "evals"))

from lz.calculator_spec import (  # noqa: E402
    build_calculator_spec, calc_region, region_is_supported, vm_size_slug, vm_size_name,
)


# --- region mapping --------------------------------------------------------

@pytest.mark.parametrize("azure,calc", [
    ("swedencentral", "sweden-central"),
    ("westeurope", "europe-west"),
    ("northeurope", "europe-north"),
    ("eastus", "us-east"),
    ("westus2", "us-west-2"),
    ("uksouth", "united-kingdom-south"),
    ("eastasia", "asia-pacific-east"),
    ("Sweden Central", "sweden-central"),   # display form tolerated
])
def test_calc_region_maps_known_regions(azure, calc):
    assert calc_region(azure) == calc


def test_calc_region_rejects_unsupported():
    with pytest.raises(ValueError):
        calc_region("mars-central")
    assert region_is_supported("swedencentral") is True
    assert region_is_supported("nowhere") is False


# --- SKU -> calculator size ----------------------------------------------

@pytest.mark.parametrize("sku,slug,name", [
    ("Standard_D2_v3", "d2v3", "D2 v3"),
    ("Standard_D4s_v5", "d4sv5", "D4s v5"),
    ("Standard_E8s_v5", "e8sv5", "E8s v5"),
    ("Standard_F4s_v2", "f4sv2", "F4s v2"),
])
def test_vm_size_mapping(sku, slug, name):
    assert vm_size_slug(sku) == slug
    assert vm_size_name(sku) == name


# --- spec assembly (hand-built inputs) ----------------------------------

def _compute():
    return {
        "region": "swedencentral", "currency": "USD", "reserved_term": "3yr",
        "line_items": [
            {"server_id": "s1", "env": "prod", "os": "windows", "sku": "Standard_D4s_v5",
             "ahb_applied": True, "disk_tier": "P20", "total_monthly": 210.0},
            {"server_id": "s2", "env": "prod", "os": "windows", "sku": "Standard_D4s_v5",
             "ahb_applied": True, "disk_tier": "P20", "total_monthly": 210.0},
            {"server_id": "s3", "env": "nonprod", "os": "linux", "sku": "Standard_E8s_v5",
             "ahb_applied": False, "disk_tier": "P30", "total_monthly": 400.0},
            {"server_id": "s4", "env": "prod", "os": "linux", "sku": None,
             "disk_tier": None, "total_monthly": 0.0},
        ],
    }


def _storage():
    return {
        "region": "swedencentral",
        "line_items": [
            {"storage_id": "v1", "category": "files_premium", "size_gb": 4096, "monthly": 800.0},
            {"storage_id": "v2", "category": "db_sql_mi", "size_gb": 512, "monthly": 120.0},
            {"storage_id": "v3", "category": "db_oracle", "size_gb": 1024, "monthly": 300.0},
        ],
    }


def _design():
    return {
        "region": "swedencentral", "dr_region": "westeurope", "regulated": True,
        "spokes": [{"name": "corp-prod"}, {"name": "corp-nonprod"}, {"name": "online-prod"}],
        "connectivity": {"model": "expressroute+vpn"},
        "identity": {"model": "extend_ad"},
        "hub": {"components": [
            "Hub VNet", "Azure Bastion", "Private DNS Resolver + Private DNS zones",
            "ExpressRoute Gateway", "VPN Gateway (backup / interim)",
            "Azure Firewall Premium (forced-tunnel egress, IDPS + TLS inspection)",
            "2x AD Domain Controllers (new AD site, existing forest)",
        ]},
        "dr": {"apps_by_tier": {"1": 3, "2": 5, "3": 10}},
    }


def _run_rate():
    return {"run_rate_monthly": {
        "egress": {"billable_gb": 1500.0, "net_out_gb_30d": 1800.0},
        "monitoring": {"log_analytics_gb_month": 120.0},
    }}


def _eng(**kw):
    base = {"customer": "Contoso Ltd", "project": "DC Exit 2027",
            "target_region": "swedencentral", "dr_region": "westeurope",
            "currency": "USD", "licensing_program": "MCA"}
    base.update(kw)
    return base


def test_spec_has_contract_shape():
    spec = build_calculator_spec(_eng(), _design(), _compute(), _storage(), _run_rate())
    assert spec["estimate_name"] == "Contoso Ltd — DC Exit 2027 — Azure Landing Zone (POE)"
    assert spec["region_default"] == "sweden-central"
    assert spec["dr_region_default"] == "europe-west"
    assert spec["currency"] == "USD"
    assert spec["licensing_program_calc"] == "mca"
    assert spec["engagement"] == "contoso-ltd/dc-exit-2027"
    assert isinstance(spec["line_items"], list) and spec["line_items"]
    assert spec["internal_monthly_estimate"] > 0
    # every line item names a real service, a region and a note
    for li in spec["line_items"]:
        assert li["service"] and li["region"] and li["note"]
        assert li["region"] in ("sweden-central", "europe-west")


def test_vms_grouped_by_sku_and_disks_counted():
    spec = build_calculator_spec(_eng(), _design(), _compute(), _storage(), _run_rate())
    vms = [x for x in spec["line_items"] if x["service"] == "virtual-machines"]
    # D4s v5 (x2, AHB) grouped into one line; E8s v5 (x1) another; + 2 AD DCs
    d4 = next(x for x in vms if x["config"]["size"] == "d4sv5")
    assert d4["config"]["count"] == 2
    assert d4["config"]["osBillingOption"] == "ahb"
    assert d4["config"]["computeBillingOption"] == "three-year"
    disks = {x["config"]["size"]: x["config"]["count"]
             for x in spec["line_items"] if x["service"] == "managed-disks"}
    assert disks == {"p20": 2, "p30": 1}


def test_unpriceable_items_are_skipped_not_dropped():
    spec = build_calculator_spec(_eng(), _design(), _compute(), _storage(), _run_rate())
    reasons = " ".join(s["why"] for s in spec["skipped"])
    whats = " ".join(s["what"] for s in spec["skipped"])
    assert "no recommended SKU" in reasons           # server s4
    assert "oracle" in whats.lower()                 # Oracle storage — no calc module
    assert "DR compute" in whats                     # DR compute note


def test_platform_lines_present_for_regulated_hub():
    spec = build_calculator_spec(_eng(), _design(), _compute(), _storage(), _run_rate())
    svc = {x["service"] for x in spec["line_items"]}
    assert {"azure-bastion", "azure-firewall", "ddos-protection-plan", "azure-dns",
            "expressroute", "vpn-gateway", "azure-monitor", "key-vault",
            "bandwidth", "azure-site-recovery"} <= svc
    fw = next(x for x in spec["line_items"] if x["service"] == "azure-firewall")
    assert fw["config"]["tier"] == "premium"


def test_missing_tool_outputs_degrade_cleanly():
    spec = build_calculator_spec(_eng(), design=None, compute=None, storage=None)
    assert spec["region_default"] == "sweden-central"
    assert any("estimate_compute_cost" in s["why"] for s in spec["skipped"])
    # still emits the always-on management lines
    assert any(x["service"] == "azure-monitor" for x in spec["line_items"])


def test_unsupported_region_raises_at_build():
    with pytest.raises(ValueError):
        build_calculator_spec(_eng(target_region="atlantis"), _design(), _compute(), _storage())


def test_non_mca_licensing_is_recorded_and_flagged():
    spec = build_calculator_spec(_eng(licensing_program="EA"), _design(), _compute(), _storage())
    assert spec["licensing_program"] == "EA"
    assert spec["licensing_program_calc"] == "ea"
    assert any("licensing program EA" in s["what"] for s in spec["skipped"])


# --- against the real sample-estate tool output -------------------------

def test_spec_from_live_pipeline_tools():
    import pipeline as P
    from cost.config import load_config
    from cost.compute_cost import estimate_compute_cost
    from cost.storage_cost import estimate_storage_cost
    from cost.run_rate import estimate_run_rate_extras
    from lz.design import design_landing_zone
    from fixtures import price_book, disk_book, storage_rates, load

    cfg = load_config()
    servers, apps, storage = load("servers"), load("applications"), load("storage")
    cc = estimate_compute_cost(servers, price_book(), disk_book(), cfg, P.PRICE_DATE)
    sc = estimate_storage_cost(storage, storage_rates(), cfg, "2026-09-01")
    infra = (cc["totals"]["monthly"] or 0) + (sc["totals"]["monthly"] or 0)
    rr = estimate_run_rate_extras(servers, infra, cfg)
    lz = design_landing_zone(apps, {"total_servers": len(servers)}, cfg)

    spec = build_calculator_spec(
        {"customer": "Sample", "project": "Estate", "target_region": "swedencentral",
         "dr_region": "westeurope", "currency": "USD", "licensing_program": "MCA"},
        design=lz, compute=cc, storage=sc, run_rate=rr,
    )
    assert spec["line_items"]
    vms = [x for x in spec["line_items"] if x["service"] == "virtual-machines"]
    assert sum(x["config"]["count"] for x in vms) >= len(servers) - len(spec["skipped"])
    assert spec["internal_monthly_estimate"] > 1000
    # no line item points at an unknown region
    assert all(x["region"] in ("sweden-central", "europe-west") for x in spec["line_items"])
