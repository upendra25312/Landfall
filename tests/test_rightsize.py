"""Cycle 3 — deterministic right-sizer (E2.1). Closes audit FIN-1 (vcpu/2 haircut)
and FIN-2 (RAM never sized)."""
import csv
import io

from conftest import sample_bytes

from cost.config import load_config
from cost.rightsize import rightsize_one, rightsize_many


def test_ram_bound_server_never_maps_to_a_tiny_sku():
    r = rightsize_one({"server_id": "s1", "vcpu": 4, "ram_gb": 128})
    assert r["recommended"]["ram_gb"] >= 128            # FIN-2: RAM is honoured
    assert r["recommended"]["bound_by"] == "ram"
    assert r["recommended"]["family"] == "E"


def test_no_perf_data_keeps_the_allocation_not_halves_it():
    r = rightsize_one({"server_id": "s1", "vcpu": 8, "ram_gb": 32})
    assert r["confidence"] == "low"
    assert r["utilisation_used"] is None
    assert r["recommended"]["vcpu"] >= 8                # FIN-1: no blind /2 haircut
    assert "no blind reduction" in r["basis"]


def test_utilisation_data_downsizes_and_is_high_confidence():
    r = rightsize_one(
        {"server_id": "s1", "vcpu": 16, "ram_gb": 64, "cpu_p95_pct": 15, "ram_avg_pct": 20},
        load_config(overrides={"rightsize": {"min_vcpu_retain_pct": 30, "min_ram_retain_pct": 30}}),
    )
    assert r["confidence"] == "high"
    assert r["utilisation_used"]["metric"] == "p95"
    assert r["recommended"]["vcpu"] < 16                # genuinely smaller
    assert r["delta"]["vcpu"] < 0


def test_disk_tier_respects_iops_not_just_size():
    r = rightsize_one({"server_id": "s1", "vcpu": 2, "ram_gb": 8,
                       "used_disk_gb": 100, "disk_iops_peak": 4000})
    # 100 GiB fits P10 (128) but P10 caps at 500 IOPS -> must step up
    assert r["disk"]["tier"] == "P30"
    assert r["disk"]["provisioned_iops"] >= 4000


def test_config_override_changes_the_no_perf_scaling():
    cfg = load_config(overrides={"rightsize": {"no_perf_data":
                     {"cpu_scale_pct": 60, "ram_scale_pct": 70, "confidence": "low"}}})
    r = rightsize_one({"server_id": "s1", "vcpu": 10, "ram_gb": 40}, cfg)
    assert r["need"]["vcpu"] == 6.0
    assert r["recommended"]["vcpu"] < 10


def test_deterministic():
    s = {"server_id": "s1", "vcpu": 8, "ram_gb": 64, "cpu_peak_pct": 55, "ram_avg_pct": 61}
    assert rightsize_one(s) == rightsize_one(s)


def test_config_loads_the_repo_estimation_config():
    cfg = load_config()
    assert "estimation_config.json" in cfg["_source"]
    assert cfg["rates"]["blended_day_rate"] == 780


def _servers_from_sample():
    text = sample_bytes("servers.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_full_sample_estate_rightsizes_and_rolls_up():
    rows = _servers_from_sample()
    out = rightsize_many(rows)
    assert out["summary"]["servers"] == 250
    assert all(r["recommended"]["sku"].startswith("Standard_") for r in out["recommendations"])
    # 66 unmonitored servers -> low confidence
    assert 50 <= out["summary"]["low_confidence"] <= 90
    # the estate is heavily over-provisioned -> the fleet shrinks on vCPU
    assert out["summary"]["recommended_vcpu"] < out["summary"]["current_vcpu"]


def test_monitored_sample_server_is_sized_from_its_utilisation():
    rows = _servers_from_sample()
    monitored = next(r for r in rows if r["cpu_peak_pct"] and r["ram_avg_pct"])
    rec = rightsize_one(monitored)
    assert rec["confidence"] in ("high", "medium")
    assert rec["utilisation_used"] is not None
