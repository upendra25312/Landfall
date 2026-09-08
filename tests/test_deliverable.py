"""Cycle 9 — assemble_estimate (E5.1/E5.2/E5.3) + estimate_effort (E6.2 basic)."""
import csv
import io

from conftest import sample_bytes

from cost.config import load_config
from cost.compute_cost import estimate_compute_cost
from cost.storage_cost import estimate_storage_cost
from cost.run_rate import estimate_run_rate_extras
from lz.design import design_landing_zone
from waves.disposition import score_dispositions
from waves.plan import plan_waves
from deliverable.assemble import assemble_estimate
from deliverable.effort import estimate_effort
from test_compute_cost import fake_book, fake_disks


def _cfg():
    return load_config()


INV = {"servers": 250, "servers_powered_on": 233, "applications": 31, "total_vcpu": 1940,
       "total_ram_gb": 10486, "provisioned_disk_tb": 186, "used_disk_tb": 106,
       "eol_servers": 84, "no_perf_data_servers": 66,
       "by_env": {"prod": 173, "nonprod": 47, "dev": 27, "dr": 3}}


# --- effort ----------------------------------------------------------

def test_effort_contingency_tracks_data_quality_confidence():
    lo = estimate_effort(250, 31, None, "Low", spokes=9, regulated=True, waves=7)
    hi = estimate_effort(250, 31, None, "High", spokes=9, regulated=True, waves=7)
    assert lo["contingency_pct"] == 20 and hi["contingency_pct"] == 8
    assert lo["estimate_at_completion_pd"] > hi["estimate_at_completion_pd"]


def test_effort_range_and_services_cost_reconcile():
    e = estimate_effort(100, 10, [{"disposition": "Rehost"}] * 10, "Medium")
    assert e["range_pd"]["low"] < e["range_pd"]["expected"] < e["range_pd"]["high"]
    assert e["services_cost"]["expected"] == round(e["estimate_at_completion_pd"] * e["blended_day_rate"])


# --- assemble ------------------------------------------------------

def _min_inputs():
    return {"inventory_summary": INV, "data_quality": {"confidence": "Medium",
            "findings": ["66 servers have no performance history"]}, "generated_on": "2026-09-08"}


def test_assembles_with_only_inventory():
    p = assemble_estimate(_min_inputs(), _cfg())
    assert p["meta"]["status"] == "DRAFT"
    assert len(p["sections"]) == len(_cfg()["deliverable"]["sections"])
    # sections with no tool output are marked, not dropped
    lz_sec = next(s for s in p["sections"] if s["key"] == "landing_zone")
    assert "not run" in lz_sec["body"]["note"]
    assert p["summary_markdown"].startswith("# Migration estimate")


def test_every_figure_has_an_appendix_entry_with_formula():
    p = assemble_estimate(_min_inputs(), _cfg())
    ids = {f["id"] for f in p["figures"]}
    appendix_ids = {a["figure_id"] for a in p["calculation_appendix"]}
    assert ids == appendix_ids and ids
    for a in p["calculation_appendix"]:
        assert a["formula"] and a["source_tool"] and a["confidence"]


def test_register_collects_caveats_from_each_tool():
    inp = _min_inputs()
    inp["storage_cost"] = {"totals": {"monthly": 100, "file_monthly": 100, "db_monthly": 0,
                                      "object_monthly": 0, "range": {}},
                           "caveats": ["DB lines are the STORAGE component only"],
                           "not_costed": ["stg-9: no size_gb"], "currency": "USD"}
    p = assemble_estimate(inp, _cfg())
    texts = [i["text"] for i in p["register"]["assumptions"]]
    gaps = [i["text"] for i in p["register"]["data_gaps"]]
    assert any("STORAGE component" in t for t in texts)
    assert any("stg-9" in g for g in gaps)
    assert any(i["category"] == "exclusion" for i in p["register"]["exclusions"])
    # standing exclusion for ExpressRoute always present
    assert any("ExpressRoute" in i["text"] for i in p["register"]["exclusions"])


def test_run_rate_figures_and_top_drivers_present_when_costs_supplied():
    inp = _min_inputs()
    inp["compute_cost"] = {"currency": "USD", "region": "swedencentral", "price_date": "2026-06-01",
                           "reserved_term": "1yr", "line_items": [1, 2],
                           "totals": {"monthly": 80000, "annual": 960000,
                                      "compute_effective_monthly": 55000, "storage_monthly": 25000,
                                      "range": {"low_monthly": 70000, "high_monthly": 100000}},
                           "rightsize_summary": {"servers": 250, "low_confidence": 60},
                           "missing_prices": []}
    inp["storage_cost"] = {"currency": "USD", "totals": {"monthly": 16000, "file_monthly": 8000,
                           "db_monthly": 8000, "object_monthly": 0, "range": {}}, "caveats": [],
                           "not_costed": [], "excluded": {"block_volumes": 522}}
    inp["run_rate_extras"] = {"currency": "USD",
        "run_rate_monthly": {"total_monthly": 16000, "backup": {"monthly": 4000},
                             "egress": {"monthly": 500}, "monitoring": {"monthly": 11500},
                             "support": {"monthly": 100}},
        "one_time": {"total": 77000, "dual_run": {"cost": 77000},
                     "migration_tooling": {"cost": 0}}}
    p = assemble_estimate(inp, _cfg())
    figs = {f["key"]: f["value"] for f in p["figures"]}
    assert figs["run_rate_monthly"] == 112000.0          # 80k + 16k + 16k
    assert figs["run_rate_annual"] == round(112000 * 12, 2)
    assert figs["one_time_cost"] == 77000.0
    rr = next(s for s in p["sections"] if s["key"] == "run_rate_cost")["body"]
    assert len(rr["top_cost_drivers"]) == 3
    assert rr["top_cost_drivers"][0]["driver"].startswith("Compute")   # biggest
    # overall confidence drops to Low (right-sizer low-confidence ratio > 25%)
    assert p["meta"]["overall_confidence"] == "Low"


def test_full_pipeline_over_the_sample_estate():
    apps = list(csv.DictReader(io.StringIO(sample_bytes("applications.csv").decode("utf-8-sig"))))
    servers = list(csv.DictReader(io.StringIO(sample_bytes("servers.csv").decode("utf-8-sig"))))
    deps = list(csv.DictReader(io.StringIO(sample_bytes("dependencies.csv").decode("utf-8-sig"))))
    storage = list(csv.DictReader(io.StringIO(sample_bytes("storage.csv").decode("utf-8-sig"))))
    cfg = load_config()
    roll = {}
    for s in servers:
        aid = s.get("app_id")
        if aid:
            roll.setdefault(aid, {"servers": 0, "eol_servers": 0})["servers"] += 1

    inp = {
        "inventory_summary": INV,
        "data_quality": {"confidence": "Medium", "findings": ["66 servers without perf history"]},
        "generated_on": "2026-09-08",
        "compute_cost": estimate_compute_cost(servers[:60], fake_book(), fake_disks(), cfg, "2026-06-01"),
        "storage_cost": estimate_storage_cost(storage, {"anf_premium": 0.29, "db_sql_mi": 0.13,
                        "files_premium": 0.16, "db_flex_postgresql": 0.11}, cfg, "2026-09-01"),
        "run_rate_extras": estimate_run_rate_extras(servers, 100000, cfg),
        "landing_zone": design_landing_zone(apps, {"total_servers": 250}, cfg),
        "dispositions": score_dispositions(apps, roll, cfg),
        "waves": plan_waves(apps, servers, deps, cfg),
    }
    a = assemble_estimate(inp, cfg)
    b = assemble_estimate(inp, cfg)
    assert a == b                                              # deterministic
    assert a["meta"]["tools_run"] == ["compute_cost", "storage_cost", "run_rate_extras",
                                      "landing_zone", "dispositions", "waves"]
    # every headline figure is traceable
    for f in a["figures"]:
        entry = next(x for x in a["calculation_appendix"] if x["figure_id"] == f["id"])
        assert entry["formula"]
    # effort section is populated and the register has real content
    eff = next(s for s in a["sections"] if s["key"] == "migration_effort")["body"]
    assert eff["estimate_at_completion_pd"] > 0
    assert len(a["register"]["assumptions"]) >= 5
    assert len(a["register"]["exclusions"]) >= 5
    assert "PCI-DSS" in a["summary_markdown"] or "regulated" in a["summary_markdown"].lower()
