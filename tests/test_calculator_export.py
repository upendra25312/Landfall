"""E11.16/E11.17 — parse the Azure Pricing Calculator's own Excel export."""
import io
import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))

from lz.calculator_export import parse_calculator_export, reconcile  # noqa: E402

_FIXTURE = os.path.join(ROOT, "tests", "fixtures", "azure-pricing-calculator-export.xlsx")


def test_parses_the_real_calculator_export():
    parsed = parse_calculator_export(_FIXTURE)
    assert parsed["source"] == "azure-pricing-calculator-export"
    assert "Landing Zone POE" in parsed["estimate_name"]
    assert parsed["licensing_program"] == "Microsoft Customer Agreement (MCA)"
    assert parsed["line_count"] == 1
    li = parsed["line_items"][0]
    assert li["category"] == "Compute"
    assert li["service_type"] == "Virtual Machines"
    assert li["region"] == "Sweden Central"
    assert "D2 v3" in li["description"]
    assert li["monthly"] == 5664.8
    assert parsed["total_monthly"] == 5664.8
    assert parsed["annual"] == round(5664.8 * 12, 2)
    assert parsed["created_at"].startswith("9/8/2026")


def test_accepts_bytes():
    with open(_FIXTURE, "rb") as fh:
        parsed = parse_calculator_export(fh.read())
    assert parsed["total_monthly"] == 5664.8


def test_total_falls_back_to_sum_when_no_total_row(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Microsoft Azure Estimate"])
    ws.append(["My estimate"])
    ws.append(["Service category", "Service type", "Custom name", "Region",
               "Description", "Estimated monthly cost", "Estimated upfront cost"])
    ws.append(["Networking", "Azure Firewall", "", "Sweden Central", "1 deployment", 900, 0])
    ws.append(["Compute", "Virtual Machines", "", "Sweden Central", "10 x D4s v5", 2500, 0])
    buf = io.BytesIO()
    wb.save(buf)
    parsed = parse_calculator_export(buf.getvalue())
    assert parsed["line_count"] == 2
    assert parsed["total_monthly"] == 3400.0


def test_reconcile_flags_large_delta():
    parsed = {"total_monthly": 5664.8}
    assert reconcile(parsed, 5000.0)["within_tolerance"] is True
    r = reconcile(parsed, 2000.0)
    assert r["within_tolerance"] is False
    assert r["delta_pct"] > 100
    assert reconcile(parsed, None)["delta_pct"] is None
