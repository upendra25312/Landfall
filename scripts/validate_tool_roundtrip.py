"""Opt-in live text-to-SQL check: two count queries, no persistent test data."""
import argparse
import datetime as dt
import json
from pathlib import Path
import urllib.request

from smoke import _az, load_config
from validate_live import SUBSCRIPTION


def run():
    rc, account, _ = _az(["account", "show", "--query", "id"])
    if rc or account != SUBSCRIPTION:
        return {"status": "BLOCKED", "reason": "Wrong or unavailable Azure session"}
    cfg = load_config()
    audience = cfg.get("FUNCTION_AUTH_CLIENT_ID")
    if not audience:
        return {"status": "BLOCKED", "reason": "Function auth audience missing"}
    rc, token, _ = _az(["account", "get-access-token", "--subscription", SUBSCRIPTION,
                        "--resource", f"api://{audience}", "--query", "accessToken"])
    if rc or not isinstance(token, str) or not token:
        return {"status": "BLOCKED", "reason": "Azure CLI cannot obtain a delegated Function token; signed-in app session required"}
    checks = []
    for eid, populated in (("_default_/_default_", True), ("validation-c53/empty", False)):
        try:
            body = json.dumps({"engagement": eid, "question": "How many servers are in the inventory? Return only the total server count."}).encode()
            request = urllib.request.Request(f"https://{cfg['SERVICE_API_NAME']}.azurewebsites.net/api/query_inventory",
                method="POST", data=body, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read(1024 * 1024))
            rows = result.get("rows", [])
            assert result.get("row_count") == 1 and len(rows) == 1 and len(rows[0]) == 1
            count = rows[0][0]
            assert isinstance(count, (int, float)) and (count > 0 if populated else count == 0)
            checks.append({"engagement": eid, "status": "PASS", "server_count": count})
        except Exception as exc:
            checks.append({"engagement": eid, "status": "FAIL", "error": type(exc).__name__,
                           "http_status": getattr(exc, "code", None)})
    return {"status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL", "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), **run()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
