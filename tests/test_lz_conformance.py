"""C28 / E11.23 — design_landing_zone scores its output against the vendored Azure
(AI) Landing Zone design checklists.
"""
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))

from lz.conformance import MET, GAP, NA, evaluate, ai_workloads_present  # noqa: E402
from lz.design import design_landing_zone  # noqa: E402

_REG_APPS = [
    {"app_id": "a1", "app_name": "Storefront", "criticality": "1", "internet_facing": "1",
     "compliance_scope": "PCI-DSS"},
    {"app_id": "a2", "app_name": "Back office", "criticality": "3"},
]
_AI_APPS = [
    {"app_id": "m1", "app_name": "Fraud scoring", "criticality": "2", "workload_type": "machine learning"},
    {"app_id": "m2", "app_name": "HR", "criticality": "3"},
]
_SS = {"total_servers": 30, "by_env": {"prod": 15, "nonprod": 15}, "total_vcpu": 240}


def _design(apps, ss=_SS):
    return design_landing_zone(apps, ss)


def test_design_output_carries_a_conformance_block():
    d = _design(_REG_APPS)
    assert isinstance(d["checklist_conformance"], list) and d["checklist_conformance"]
    s = d["checklist_summary"]
    assert s["met"] + s["partial"] + s["gap"] == s["total"]
    assert 0 <= s["met_pct"] <= 100
    assert s["headline"].startswith(f"{s['met']}/{s['total']}")
    # every item is well-formed
    for it in d["checklist_conformance"]:
        assert it["status"] in (MET, "partial", GAP, NA)
        assert it["id"] and it["domain"] and it["item"]
        if it["status"] != MET:
            assert it["recommendation"] or it["status"] == NA


def test_met_items_have_no_recommendation_and_gaps_do():
    d = _design(_REG_APPS)
    for it in d["checklist_conformance"]:
        if it["status"] == MET:
            assert not it["recommendation"]
    assert d["checklist_gaps"]
    assert all(g["recommendation"] for g in d["checklist_gaps"])
    assert {g["id"] for g in d["checklist_gaps"]} <= {it["id"] for it in d["checklist_conformance"]}


def test_deterministic():
    a = _design(_REG_APPS)["checklist_conformance"]
    b = _design(_REG_APPS)["checklist_conformance"]
    assert a == b


def test_baseline_meets_the_identity_and_resource_org_items():
    items = {it["id"]: it for it in _design(_REG_APPS)["checklist_conformance"]}
    assert items["ID-2"]["status"] == MET          # PIM in the identity block
    assert items["RO-1"]["status"] == MET          # CAF MG hierarchy
    assert items["RO-2"]["status"] == MET          # connectivity/identity/management subs
    assert items["NET-3"]["status"] == MET         # private DNS in the hub


def test_no_dr_region_is_a_reliability_gap():
    d = design_landing_zone(_REG_APPS, _SS, cfg=_no_dr_cfg())
    items = {it["id"]: it for it in d["checklist_conformance"]}
    assert items["REL-1"]["status"] == GAP
    assert "REL-1" in {g["id"] for g in d["checklist_gaps"]}


def _no_dr_cfg():
    from cost.config import load_config
    cfg = load_config()
    cfg = {**cfg, "landing_zone": {**cfg["landing_zone"], "dr_region": None}}
    return cfg


def test_regulated_items_are_na_without_a_compliance_scope():
    items = {it["id"]: it for it in _design([{"app_id": "x", "app_name": "y", "criticality": "3"}])["checklist_conformance"]}
    assert items["SEC-2"]["status"] == NA
    assert items["SEC-3"]["status"] == NA
    assert items["GOV-3"]["status"] == NA


def test_regulated_items_scored_when_a_scope_exists():
    items = {it["id"]: it for it in _design(_REG_APPS)["checklist_conformance"]}
    assert items["SEC-3"]["status"] in (MET, "partial")
    assert items["SEC-2"]["status"] in (MET, GAP)


def test_ai_overlay_applies_only_with_ai_workloads():
    assert ai_workloads_present(_AI_APPS) is True
    assert ai_workloads_present(_REG_APPS) is False

    d_ai = _design(_AI_APPS)
    d_plain = _design(_REG_APPS)
    assert d_ai["ai_lz_applicable"] is True
    assert d_plain["ai_lz_applicable"] is False

    ai_rows = {it["id"]: it for it in d_ai["checklist_conformance"] if it["id"].startswith("AILZ")}
    plain_rows = {it["id"]: it for it in d_plain["checklist_conformance"] if it["id"].startswith("AILZ")}
    assert len(ai_rows) == 10 and len(plain_rows) == 10
    assert all(r["status"] == NA for r in plain_rows.values())            # excluded from the ratio
    assert any(r["status"] == GAP for r in ai_rows.values())              # real gaps surfaced
    assert ai_rows["AILZ-4"]["status"] == MET                             # managed identity from the baseline


def test_na_rows_are_excluded_from_the_ratio():
    d = _design(_REG_APPS)
    s = d["checklist_summary"]
    na = sum(1 for it in d["checklist_conformance"] if it["status"] == NA)
    assert s["na"] == na
    assert s["total"] == len(d["checklist_conformance"]) - na


def test_evaluate_is_robust_to_a_thin_design():
    out = evaluate({}, [], {})
    assert out["summary"]["total"] > 0
    assert out["ai_lz_applicable"] is False


def test_assemble_and_export_surface_conformance():
    from deliverable.assemble import assemble_estimate
    from deliverable.export import export

    d = _design(_AI_APPS)
    pkg = assemble_estimate({"inventory_summary": {"servers": 30, "applications": 2},
                             "landing_zone": d})
    lz_body = next(s["body"] for s in pkg["sections"] if s["key"] == "landing_zone")
    conf = lz_body["design_conformance"]
    assert conf["headline"] == d["checklist_summary"]["headline"]
    assert conf["ai_lz_applicable"] is True
    assert conf["gaps"]

    fig = next((f for f in pkg["figures"] if f["key"] == "lz_conformance"), None)
    assert fig and fig["value"] == d["checklist_summary"]["met"]

    for fmt in ("docx", "pptx", "xlsx"):
        blob, _n, _m = export(pkg, fmt)
        assert blob and len(blob) > 1000


def test_dashboard_renders_the_conformance_block():
    html = open(os.path.join(ROOT, "src", "web", "static", "dashboard.js"), encoding="utf-8").read()
    assert "design_conformance" in html and "Design conformance" in html


def test_checklists_are_vendored():
    for name in ("alz-checklist.md", "ai-lz-checklist.md"):
        p = os.path.join(ROOT, "docs", "lz-design", name)
        assert os.path.exists(p) and os.path.getsize(p) > 500
