"""Read-only service inventory/readiness in the authorized Landfall environment."""
import argparse
import datetime as dt
import json
from pathlib import Path

from smoke import _az, load_config

SUBSCRIPTION = "f609eb5b-df3e-4fab-9a1b-9a8fea2f157f"
GROUP = "rg-landfall"


def run():
    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    rc, account, _ = _az(["account", "show", "--query", "{id:id,state:state}"])
    check("subscription", rc == 0 and isinstance(account, dict) and account.get("id") == SUBSCRIPTION
          and account.get("state") == "Enabled", account)
    if not all(c["status"] == "PASS" for c in checks):
        return checks
    scope = ["--subscription", SUBSCRIPTION, "--resource-group", GROUP]
    rc, group, _ = _az(["group", "show", "--subscription", SUBSCRIPTION, "--name", GROUP,
                        "--query", "{name:name,location:location,state:properties.provisioningState}"])
    check("resource_group", rc == 0 and isinstance(group, dict) and group.get("location") == "swedencentral"
          and group.get("state") == "Succeeded", group)
    if checks[-1]["status"] != "PASS":
        return checks
    rc, apps, _ = _az(["containerapp", "list", *scope, "--query",
                       "[].{name:name,state:properties.provisioningState,revision:properties.latestRevisionName,ready:properties.latestReadyRevisionName}"])
    for service in ("web", "calc", "drawio"):
        found = [a for a in (apps if isinstance(apps, list) else []) if a["name"].startswith(f"ca-{service}-")]
        check(f"container_{service}", rc == 0 and len(found) == 1 and found[0]["state"] == "Succeeded"
              and bool(found[0]["ready"]) and found[0]["ready"] == found[0]["revision"], found)
    cfg = load_config()
    rc, functions, _ = _az(["functionapp", "function", "list", *scope, "--name", cfg.get("SERVICE_API_NAME", ""),
                            "--query", "[].name"])
    actual = {name.rsplit("/", 1)[-1] for name in (functions if isinstance(functions, list) else [])}
    # Index source without connecting to any Function data-plane dependencies.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/api"))
    import function_app
    expected = {function.get_function_name() for function in function_app.app.get_functions()}
    check("function_registration", rc == 0 and expected <= actual,
          {"expected": len(expected), "registered": len(actual), "missing": sorted(expected - actual)})
    rc, resources, _ = _az(["resource", "list", *scope, "--query", "[].{name:name,type:type}"])
    for label, kind in (("search", "Microsoft.Search/searchServices"),
                        ("foundry", "Microsoft.CognitiveServices/accounts"),
                        ("monitoring", "Microsoft.Insights/components"),
                        ("registry", "Microsoft.ContainerRegistry/registries")):
        found = [r for r in (resources if isinstance(resources, list) else []) if r["type"].lower() == kind.lower()]
        check(label + "_resource", rc == 0 and bool(found), found)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    checks = run()
    result = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "checks": checks,
              "scope": "read-only control-plane registration/readiness; not data-plane functional proof",
              "ok": all(c["status"] == "PASS" for c in checks)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for c in checks:
        print(f"{c['check']}: {c['status']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
