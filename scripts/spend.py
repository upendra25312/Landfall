"""Landfall spend check (PRD E13.4 / engagement-workspaces-prd.md §4.15).

*Am I on budget this month?* Reads the month-to-date **actual** cost for the
deployment's resource group from Cost Management, compares it to the budget, and
projects the full-month spend at the current burn rate. Also lists the top cost
by resource type so you can see what is running the meter.

`--budget` (and the MONTHLY_BUDGET Bicep param) are in the **subscription's
billing currency** — this script prints yours. On a non-USD subscription, pass
`--budget` in that currency (e.g. ~4200 INR for a $50 target).

The real cost controls are `azd down --purge` between sessions and never
`DEPLOYMENT_TIER=prod`; this is the "did I forget to tear down?" check and a way
to *see* Azure Cost Management (a learning goal).

Stdlib only. `az` must be on PATH and logged in.

    python scripts/spend.py                 # RG from `azd env get-values`
    python scripts/spend.py --rg rg-landfall --budget 50
    python scripts/spend.py --json          # machine-readable
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time


def _run(cmd: list[str], timeout: int = 90) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} timed out"


def _az():
    return shutil.which("az") or ("az.cmd" if os.name == "nt" else "az")


def _az_json(args: list[str], timeout: int = 120):
    rc, out, err = _run([_az(), *args, "-o", "json"], timeout=timeout)
    if rc != 0:
        raise RuntimeError(err or f"az {' '.join(args)} failed ({rc})")
    return json.loads(out) if out else None


def _rg_from_azd() -> str | None:
    azd = shutil.which("azd") or shutil.which("azd.exe")
    if not azd:
        return None
    rc, out, _ = _run([azd, "env", "get-values"], timeout=30)
    if rc != 0:
        return None
    for line in out.splitlines():
        k, _, v = line.partition("=")
        if k.strip() == "AZURE_RESOURCE_GROUP":
            return v.strip().strip('"')
    return os.environ.get("AZURE_RESOURCE_GROUP")


def _subscription_id() -> str:
    return _az_json(["account", "show", "--query", "id"]) or ""


_QUERY_API = "2023-11-01"


def month_to_date_cost(scope: str) -> tuple[float, str, list[tuple[str, float]]]:
    """(total, currency, [(resourceType, cost), …]) for the current calendar month.

    Uses the Cost Management *query* REST API via `az rest` — no `costmanagement`
    CLI extension needed (it isn't installed by default).
    """
    body = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ResourceType"}],
        },
    }
    url = (f"https://management.azure.com{scope}/providers/Microsoft.CostManagement"
           f"/query?api-version={_QUERY_API}")
    tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(body, tf)
        tf.close()
        cmd = [_az(), "rest", "--method", "post", "--url", url, "--body", f"@{tf.name}",
               "--headers", "Content-Type=application/json", "-o", "json"]
        rc, out, err = _run(cmd, timeout=120)
        if rc != 0 and "429" in err:            # Cost Management query API is heavily throttled
            time.sleep(25)
            rc, out, err = _run(cmd, timeout=120)
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass
    if rc != 0:
        raise RuntimeError(err or "cost query failed")
    data = json.loads(out) if out else {}
    props = data.get("properties", data)
    rows = props.get("rows", [])
    cols = [c["name"] for c in props.get("columns", [])]
    ci_cost = cols.index("Cost") if "Cost" in cols else 0
    ci_cur = cols.index("Currency") if "Currency" in cols else len(cols) - 1
    ci_type = cols.index("ResourceType") if "ResourceType" in cols else 1
    total = 0.0
    currency = "USD"
    by_type: dict[str, float] = {}
    for r in rows:
        c = float(r[ci_cost])
        total += c
        currency = r[ci_cur] if ci_cur < len(r) else currency
        by_type[str(r[ci_type])] = by_type.get(str(r[ci_type]), 0.0) + c
    top = sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)
    return total, currency, top


def project(total: float) -> tuple[float, int, int]:
    now = dt.datetime.now(dt.timezone.utc)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day = now.day
    projected = total / day * days_in_month if day else total
    return projected, day, days_in_month


def assess(rg: str, budget: float) -> dict:
    sub = _subscription_id()
    scope = f"/subscriptions/{sub}/resourceGroups/{rg}"
    total, currency, top = month_to_date_cost(scope)
    projected, day, dim = project(total)
    pct_now = 100.0 * total / budget if budget else 0.0
    pct_proj = 100.0 * projected / budget if budget else 0.0
    if pct_proj >= 100:
        verdict = "OVER — projected to exceed the budget"
    elif pct_proj >= 80:
        verdict = "WATCH — projected 80-100% of budget"
    else:
        verdict = "OK — on track"
    return {
        "resource_group": rg, "currency": currency, "budget": budget,
        "month_to_date": round(total, 2), "day_of_month": day, "days_in_month": dim,
        "projected_month": round(projected, 2),
        "pct_of_budget_now": round(pct_now, 1), "pct_of_budget_projected": round(pct_proj, 1),
        "verdict": verdict,
        "top_resource_types": [{"type": t, "cost": round(c, 2)} for t, c in top[:8]],
    }


def _print(a: dict) -> None:
    cur = a["currency"]
    print(f"\n  Resource group : {a['resource_group']}")
    print(f"  Budget         : {cur} {a['budget']:.0f} / month")
    print(f"  Month-to-date  : {cur} {a['month_to_date']:.2f}"
          f"   (day {a['day_of_month']}/{a['days_in_month']}, {a['pct_of_budget_now']:.0f}% of budget)")
    print(f"  Projected      : {cur} {a['projected_month']:.2f}"
          f"   ({a['pct_of_budget_projected']:.0f}% of budget) at the current burn rate")
    print(f"\n  {a['verdict']}\n")
    if a["top_resource_types"]:
        print("  Top cost by resource type (MTD):")
        for row in a["top_resource_types"]:
            print(f"    {cur} {row['cost']:8.2f}  {row['type']}")
    if cur != "USD":
        print(f"\n  NOTE: your subscription bills in {cur}. Pass --budget (and set the "
              f"MONTHLY_BUDGET\n        Bicep param) in {cur}, not USD.")
    print("\n  Tip: `azd down --purge` between sessions; never DEPLOYMENT_TIER=prod.\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Landfall month-to-date spend check (E13.4)")
    ap.add_argument("--rg", default=None, help="resource group (default: AZURE_RESOURCE_GROUP from azd)")
    ap.add_argument("--budget", type=float,
                    default=float(os.environ.get("MONTHLY_BUDGET", "50")),
                    help="monthly budget in the subscription currency (default 50 / MONTHLY_BUDGET)")
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args(argv)

    rg = args.rg or _rg_from_azd()
    if not rg:
        print("no resource group — pass --rg or run where `azd env get-values` works", file=sys.stderr)
        return 2
    if not _az():
        print("az CLI not found on PATH", file=sys.stderr)
        return 2

    try:
        a = assess(rg, args.budget)
    except Exception as exc:  # noqa: BLE001
        print(f"cost query failed: {exc}", file=sys.stderr)
        print("(Cost Management data lags ~8-24h and needs the 'Cost Management Reader' role.)",
              file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(a, indent=2))
    else:
        _print(a)
    return 0 if not a["verdict"].startswith("OVER") else 3


if __name__ == "__main__":
    raise SystemExit(main())
