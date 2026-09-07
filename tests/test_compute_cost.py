"""Cycle 4 — estimate_compute_cost (E2.2). Price math only; prices are injected."""
import csv
import io

from conftest import sample_bytes

from cost.compute_cost import HOURS_PER_MONTH, estimate_compute_cost
from cost.config import load_config
from cost.skus import DISK_TIERS, SKUS


def fake_book() -> dict:
    b: dict = {}
    for rows in SKUS.values():
        for sku, v, _r in rows:
            lin = round(v * 0.05, 4)
            win = round(v * 0.09, 4)
            b[sku] = {
                "linux": {"payg": lin, "ri1y": round(lin * 0.65, 4), "ri3y": round(lin * 0.45, 4)},
                "windows": {"payg": win, "ri1y": round(win * 0.65, 4), "ri3y": round(win * 0.45, 4)},
            }
    return b


def fake_disks() -> dict:
    return {t: round(g * 0.12, 2) for t, g, _ in DISK_TIERS}


def _cfg(**pricing):
    base = {"pricing": {"reserved_term": "none", "reservation_coverage_pct": 0,
                        "azure_hybrid_benefit_windows": True}}
    base["pricing"].update(pricing)
    return load_config(overrides=base)


WIN = {"server_id": "w1", "vcpu": 4, "ram_gb": 16, "os_name": "Windows Server",
       "env": "prod", "cpu_p95_pct": 50, "ram_avg_pct": 50}


def test_azure_hybrid_benefit_prices_windows_at_the_linux_rate():
    r = estimate_compute_cost([WIN], fake_book(), fake_disks(), _cfg())
    li = r["line_items"][0]
    assert li["ahb_applied"] is True
    assert li["sku"] == "Standard_D4s_v5"
    assert li["compute_payg_monthly"] == round(0.20 * HOURS_PER_MONTH, 2)   # linux 4*0.05


def test_without_ahb_windows_pays_the_windows_rate():
    r = estimate_compute_cost([WIN], fake_book(), fake_disks(),
                              _cfg(azure_hybrid_benefit_windows=False))
    li = r["line_items"][0]
    assert li["ahb_applied"] is False
    assert li["compute_payg_monthly"] == round(0.36 * HOURS_PER_MONTH, 2)   # windows 4*0.09


def test_reserved_instance_blend():
    r = estimate_compute_cost([WIN], fake_book(), fake_disks(),
                              _cfg(reserved_term="1yr", reservation_coverage_pct=80))
    payg, ri = 0.20, round(0.20 * 0.65, 4)
    eff = (0.8 * ri + 0.2 * payg) * HOURS_PER_MONTH
    assert r["line_items"][0]["compute_effective_monthly"] == round(eff, 2)


def test_environment_factor_scales_dr_compute():
    dr = dict(WIN, server_id="dr1", env="dr")
    cfg = load_config(overrides={"pricing": {"reserved_term": "none"},
                                 "uplift": {"dr_of_prod_pct": 30}})
    r = estimate_compute_cost([dr], fake_book(), fake_disks(), cfg)
    li = r["line_items"][0]
    assert li["env_factor"] == 0.3
    assert li["compute_effective_monthly"] == round(0.20 * HOURS_PER_MONTH * 0.3, 2)


def test_missing_price_is_flagged_not_fatal():
    book = fake_book()
    del book["Standard_D4s_v5"]
    r = estimate_compute_cost([WIN], book, fake_disks(), _cfg())
    assert "Standard_D4s_v5" in r["missing_prices"]
    li = r["line_items"][0]
    assert li["compute_effective_monthly"] is None
    assert li["total_monthly"] == li["disk_monthly"]          # disk still counted


def test_range_is_ordered_and_totals_add_up():
    rows = _sample_slice(12)
    r = estimate_compute_cost(rows, fake_book(), fake_disks(),
                              _cfg(reserved_term="1yr", reservation_coverage_pct=70))
    t = r["totals"]
    assert t["range"]["low_monthly"] <= t["range"]["expected_monthly"] <= t["range"]["high_monthly"]
    assert t["monthly"] == round(sum(x["total_monthly"] for x in r["line_items"]), 2)
    assert t["annual"] == round(t["monthly"] * 12, 2)
    assert not r["missing_prices"]


def test_deterministic():
    a = estimate_compute_cost([WIN], fake_book(), fake_disks(), _cfg())
    b = estimate_compute_cost([WIN], fake_book(), fake_disks(), _cfg())
    assert a["totals"] == b["totals"] and a["line_items"] == b["line_items"]


def test_by_environment_breakdown_over_a_sample_slice():
    rows = _sample_slice(40)
    r = estimate_compute_cost(rows, fake_book(), fake_disks(), _cfg())
    assert sum(e["servers"] for e in r["by_environment"].values()) == 40
    assert r["totals"]["monthly"] > 0
    assert r["rightsize_summary"]["servers"] == 40


def _sample_slice(n):
    text = sample_bytes("servers.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))[:n]
