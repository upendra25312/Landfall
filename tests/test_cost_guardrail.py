"""E13.4 — the cost guardrail: a default-ON resource-group budget + alerts, a Log
Analytics daily cap, a `ca-calc` min-replicas knob, and the `scripts/spend.py`
month-to-date check.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT

MAIN = os.path.join(ROOT, "infra", "main.bicep")
RES = os.path.join(ROOT, "infra", "resources.bicep")
PARAMS = os.path.join(ROOT, "infra", "main.parameters.json")

sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------- bicep (text)

def test_budget_params_declared_and_threaded():
    main, res, params = _read(MAIN), _read(RES), _read(PARAMS)
    assert "param monthlyBudget int = 50" in main
    assert "param budgetStartDate string = utcNow('yyyy-MM-01')" in main
    assert "param logAnalyticsDailyCapGb string = '0.5'" in main
    assert "param calcMinReplicas int = 1" in main
    for name in ("monthlyBudget", "budgetStartDate", "logAnalyticsDailyCapGb", "calcMinReplicas"):
        assert f"{name}: {name}" in main, name                 # passed to the module
        assert f"param {name} " in res, name
    assert '"monthlyBudget": { "value": "${MONTHLY_BUDGET=50}" }' in params
    assert '"calcMinReplicas": { "value": "${CALC_MIN_REPLICAS=1}" }' in params


def test_budget_resource_is_default_on_with_three_thresholds():
    res = _read(RES)
    assert "resource costBudget 'Microsoft.Consumption/budgets@" in res
    assert "var hasBudget = monthlyBudget > 0" in res
    assert "if (hasBudget)" in res
    # 50/80 actual + 100 forecast, and the RG Owner is always notified
    assert "threshold: 50" in res and "threshold: 80" in res and "threshold: 100" in res
    assert "thresholdType: 'Actual'" in res and "thresholdType: 'Forecasted'" in res
    assert "contactRoles: [ 'Owner' ]" in res
    assert "empty(alertEmail) ? [] : [ alertEmail ]" in res


def test_log_analytics_daily_cap_and_calc_knob():
    res = _read(RES)
    assert "workspaceCapping: {" in res
    assert "dailyQuotaGb: isProd ? json('-1') : json(logAnalyticsDailyCapGb)" in res
    assert "minReplicas: calcMinReplicas" in res               # the ca-calc scale block


def test_free_tier_defaults_keep_the_budget_realistic():
    # a regression that flipped a default to a paid SKU would blow the $40-50 target
    res = _read(RES)
    assert "isProd ? 'basic' : 'free'" in res                  # AI Search stays free
    assert "param deploymentTier string = 'free'" in res


# ------------------------------------------------------------- bicep (compile)

def _az():
    return shutil.which("az") or shutil.which("az.cmd")


@pytest.mark.skipif(not _az(), reason="az CLI not available")
def test_bicep_compiles_with_the_budget(tmp_path):
    out = tmp_path / "main.json"
    r = subprocess.run([_az(), "bicep", "build", "--file", MAIN, "--outfile", str(out)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    arm = json.loads(out.read_text(encoding="utf-8"))
    assert arm["parameters"]["monthlyBudget"]["defaultValue"] == 50
    assert arm["parameters"]["calcMinReplicas"]["defaultValue"] == 1
    blob = json.dumps(arm)
    assert "Microsoft.Consumption/budgets" in blob
    assert "Forecasted" in blob and "workspaceCapping" in blob


# ------------------------------------------------------------- scripts/spend.py

def test_cost_projection_math():
    import spend as cost
    # 10 spent on day 5 of a 30-day month -> projected 60
    proj, day, dim = cost.project(10.0)
    # project() uses the real 'now'; assert the formula, not the calendar
    assert abs(proj - (10.0 / day * dim)) < 1e-6


def test_cost_assess_verdicts(monkeypatch):
    import spend as cost
    monkeypatch.setattr(cost, "_subscription_id", lambda: "sub-1")
    monkeypatch.setattr(cost, "project", lambda total: (total * 3, 10, 30))  # 3x burn

    monkeypatch.setattr(cost, "month_to_date_cost",
                        lambda scope: (10.0, "USD", [("Microsoft.App/containerApps", 7.0)]))
    a = cost.assess("rg-landfall", 50)
    assert a["month_to_date"] == 10.0 and a["projected_month"] == 30.0
    assert a["verdict"].startswith("OK")
    assert a["top_resource_types"][0]["type"] == "Microsoft.App/containerApps"

    monkeypatch.setattr(cost, "month_to_date_cost", lambda scope: (20.0, "USD", []))
    assert cost.assess("rg", 50)["verdict"].startswith("OVER")   # 20*3 = 60 > 50

    monkeypatch.setattr(cost, "month_to_date_cost", lambda scope: (15.0, "USD", []))
    assert cost.assess("rg", 50)["verdict"].startswith("WATCH")  # 45 = 90%


def test_cost_main_needs_a_resource_group(monkeypatch, capsys):
    import spend as cost
    monkeypatch.setattr(cost, "_rg_from_azd", lambda: None)
    assert cost.main(["--budget", "50"]) == 2
