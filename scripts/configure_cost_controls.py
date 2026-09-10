"""Activate Landfall's scoped INR budget and telemetry ingestion cap."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from configure_direct_uploads import az_rest
from smoke import _az
from validate_live import GROUP, SUBSCRIPTION

BUDGET_INR = 4200
WORKSPACE = "log-tmglwfatwcsa2"
BUDGET_NAME = "landfall-monthly-tmglwfatwcsa2"


def run(output: Path) -> int:
    rc, account, _ = _az(["account", "show", "--query", "id"])
    if rc or account != SUBSCRIPTION:
        raise RuntimeError("wrong Azure subscription")
    start = dt.date.today().replace(day=1)
    end = start.replace(year=start.year + 10)
    scope = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"
    url = (f"https://management.azure.com{scope}/providers/Microsoft.Consumption"
           f"/budgets/{BUDGET_NAME}?api-version=2023-11-01")
    notifications = {
        "actual_50": {"enabled": True, "operator": "GreaterThanOrEqualTo", "threshold": 50,
                      "thresholdType": "Actual", "contactEmails": [], "contactRoles": ["Owner"],
                      "contactGroups": []},
        "actual_80": {"enabled": True, "operator": "GreaterThanOrEqualTo", "threshold": 80,
                      "thresholdType": "Actual", "contactEmails": [], "contactRoles": ["Owner"],
                      "contactGroups": []},
        "forecast_100": {"enabled": True, "operator": "GreaterThanOrEqualTo", "threshold": 100,
                         "thresholdType": "Forecasted", "contactEmails": [], "contactRoles": ["Owner"],
                         "contactGroups": []},
    }
    az_rest("put", url, {"properties": {
        "category": "Cost", "amount": BUDGET_INR, "timeGrain": "Monthly",
        "timePeriod": {"startDate": start.isoformat(), "endDate": end.isoformat()},
        "notifications": notifications,
    }})
    rc, _, err = _az(["monitor", "log-analytics", "workspace", "update",
                      "--subscription", SUBSCRIPTION, "--resource-group", GROUP,
                      "--workspace-name", WORKSPACE, "--quota", "0.5"])
    if rc:
        raise RuntimeError(f"workspace cap update failed: {err[:300]}")
    budget = az_rest("get", url)
    rc, workspaces, err = _az(["monitor", "log-analytics", "workspace", "show",
                               "--subscription", SUBSCRIPTION, "--resource-group", GROUP,
                               "--workspace-name", WORKSPACE])
    if rc:
        raise RuntimeError(f"workspace verification failed: {err[:300]}")
    p = budget.get("properties", {})
    evidence = {
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "subscription": SUBSCRIPTION, "resource_group": GROUP,
        "billing_currency": "INR", "budget_amount": p.get("amount"),
        "time_grain": p.get("timeGrain"),
        "notifications": sorted((p.get("notifications") or {}).keys()),
        "log_analytics_daily_quota_gb": (workspaces.get("workspaceCapping") or {}).get("dailyQuotaGb"),
    }
    evidence["ok"] = (evidence["budget_amount"] == BUDGET_INR
                       and evidence["time_grain"] == "Monthly"
                       and evidence["log_analytics_daily_quota_gb"] == 0.5
                       and len(evidence["notifications"]) == 3)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("PASS" if evidence["ok"] else "FAIL")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.output))
