"""Unit tests for the Quarterly Price, SKU & CAF Re-benchmark Tool (S2)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Ensure root and scripts are resolvable
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

from rebenchmark_prices import (  # noqa: E402
    audit_caf_alignment,
    audit_sku_generations,
    calculate_disk_drifts,
    calculate_price_drifts,
    render_markdown_report,
    run_benchmark,
)
from cost.skus import SKUS  # noqa: E402


def test_audit_sku_generations_covers_all_families():
    findings = audit_sku_generations(SKUS)
    families = {f["family"] for f in findings}
    assert {"F", "D", "E"}.issubset(families)
    for f in findings:
        assert f["sku_count"] > 0
        assert f["generation"]
        assert f["status"]


def test_audit_caf_alignment_validates_standards():
    results = audit_caf_alignment(SKUS, "swedencentral")
    assert len(results) >= 4
    criteria_names = [r["criterion"] for r in results]
    assert "General-Purpose RAM/vCPU Ratio" in criteria_names
    assert "Storage Tier Foundation" in criteria_names
    assert all(r["result"] == "PASSED" for r in results)


def test_calculate_price_drifts_identifies_variance():
    base = {
        "Standard_D4s_v5": {
            "linux": {"payg": 0.20, "ri1y": 0.12, "ri3y": 0.08},
            "windows": {"payg": 0.36, "ri1y": 0.22, "ri3y": 0.15},
        }
    }
    # Current has a 10% increase on linux payg (0.20 -> 0.22)
    curr = {
        "Standard_D4s_v5": {
            "linux": {"payg": 0.22, "ri1y": 0.12, "ri3y": 0.08},
            "windows": {"payg": 0.36, "ri1y": 0.22, "ri3y": 0.15},
        }
    }

    # With 5% threshold, drift is detected
    drifts_5 = calculate_price_drifts(base, curr, threshold_pct=5.0)
    assert len(drifts_5) == 1
    assert drifts_5[0]["sku"] == "Standard_D4s_v5"
    assert drifts_5[0]["delta_pct"] == 10.0
    assert drifts_5[0]["direction"] == "increase"

    # With 15% threshold, no drift is flagged
    drifts_15 = calculate_price_drifts(base, curr, threshold_pct=15.0)
    assert len(drifts_15) == 0


def test_calculate_disk_drifts_identifies_variance():
    base = {"P10": 19.71, "P20": 38.32}
    curr = {"P10": 19.71, "P20": 34.00}  # ~11.27% drop on P20

    drifts = calculate_disk_drifts(base, curr, threshold_pct=5.0)
    assert len(drifts) == 1
    assert drifts[0]["tier"] == "P20"
    assert drifts[0]["direction"] == "decrease"
    assert drifts[0]["delta_pct"] < -10.0


def test_run_benchmark_offline_produces_valid_structure():
    res = run_benchmark(region="swedencentral", offline=True, date_str="2026-09-10")
    assert res["status"] == "APPROVED"
    assert res["region"] == "swedencentral"
    assert res["as_of"] == "2026-09-10"
    assert res["metrics"]["vm_price_drifts"] == 0
    assert res["metrics"]["disk_price_drifts"] == 0
    assert res["metrics"]["caf_criteria_met"] == res["metrics"]["caf_criteria_total"]
    assert len(res["sku_generations"]) == 3


def test_render_markdown_report_structure():
    res = run_benchmark(region="swedencentral", offline=True, date_str="2026-09-10")
    md = render_markdown_report(res)
    assert "# Azure Pricing, SKU & CAF Quarterly Re-benchmark Report" in md
    assert "**Target Region:** `swedencentral`" in md
    assert "Executive Summary" in md
    assert "VM SKU Family Generation Audit" in md
    assert "Cloud Adoption Framework (CAF) Conformance" in md
    assert "**Overall Audit Status:** **APPROVED**" in md
    assert "**Next Review Due:** 2026-12-09" in md


def test_rebenchmark_cli_offline_invocation(tmp_path):
    report_file = tmp_path / "test_report.md"
    cmd = [
        sys.executable,
        str(_ROOT / "scripts" / "rebenchmark_prices.py"),
        "--offline",
        "--region",
        "swedencentral",
        "--out",
        str(report_file),
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert proc.returncode == 0
    assert report_file.exists()
    assert "# Azure Pricing, SKU & CAF Quarterly Re-benchmark Report" in report_file.read_text(encoding="utf-8")

    parsed_json = json.loads(proc.stdout)
    assert parsed_json["status"] == "APPROVED"
    assert parsed_json["region"] == "swedencentral"
