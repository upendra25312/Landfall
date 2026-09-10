"""Configure the narrowly scoped Azure controls required by browser uploads."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess

from smoke import _az
from validate_live import GROUP, SUBSCRIPTION

WEB_ORIGIN = "https://ca-web-tmglwfatwcsa2.lemonfield-4df18ff0.swedencentral.azurecontainerapps.io"
ACCOUNT = "sttmglwfatwcsa2"
WEB_APP = "ca-web-tmglwfatwcsa2"
API = "2023-05-01"


def az_rest(method: str, url: str, body: dict | None = None, allow_404=False):
    az = shutil.which("az") or "az.cmd"
    cmd = [az, "rest", "--method", method, "--url", url, "--output", "json"]
    if body is not None:
        cmd += ["--headers", "Content-Type=application/json", "--body", json.dumps(body)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode:
        if allow_404 and "NotFound" in proc.stderr:
            return None
        raise RuntimeError(proc.stderr[:500])
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def run(output: Path) -> int:
    rc, account, _ = _az(["account", "show", "--query", "id"])
    if rc or account != SUBSCRIPTION:
        raise RuntimeError("wrong Azure subscription")
    base = (f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"
            f"/providers/Microsoft.Storage/storageAccounts/{ACCOUNT}")
    blob_url = f"{base}/blobServices/default?api-version={API}"
    policy_url = f"{base}/managementPolicies/default?api-version={API}"

    blob = az_rest("get", blob_url)
    cors_rule = {
        "allowedOrigins": [WEB_ORIGIN],
        "allowedMethods": ["OPTIONS", "PUT"],
        "allowedHeaders": ["content-type", "x-ms-blob-type", "x-ms-version"],
        "exposedHeaders": ["etag", "x-ms-request-id"],
        "maxAgeInSeconds": 600,
    }
    properties = dict(blob.get("properties") or {})
    properties["cors"] = {"corsRules": [cors_rule]}
    az_rest("put", blob_url, {"properties": properties})

    policy = az_rest("get", policy_url, allow_404=True) or {"properties": {"policy": {"rules": []}}}
    policy_body = policy.get("properties", {}).get("policy", {})
    rules = [r for r in policy_body.get("rules", []) if r.get("name") != "landfall-abandoned-uploads"]
    rules.append({
        "enabled": True,
        "name": "landfall-abandoned-uploads",
        "type": "Lifecycle",
        "definition": {
            "actions": {"baseBlob": {"delete": {"daysAfterModificationGreaterThan": 1}}},
            "filters": {"blobTypes": ["blockBlob"],
                        "prefixMatch": ["raw/pending-uploads/", "raw/upload-tickets/"]},
        },
    })
    az_rest("put", policy_url, {"properties": {"policy": {"rules": rules}}})

    rc, _, err = _az(["containerapp", "update", "--subscription", SUBSCRIPTION,
                      "--resource-group", GROUP, "--name", WEB_APP,
                      "--set-env-vars", "DIRECT_UPLOADS_ENABLED=1"])
    if rc:
        raise RuntimeError(f"web update failed: {err[:300]}")

    current_blob = az_rest("get", blob_url)
    current_policy = az_rest("get", policy_url)
    actual_rules = current_blob.get("properties", {}).get("cors", {}).get("corsRules", [])
    lifecycle = current_policy.get("properties", {}).get("policy", {}).get("rules", [])
    evidence = {
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "subscription": SUBSCRIPTION, "resource_group": GROUP,
        "storage_account": ACCOUNT, "web_origin": WEB_ORIGIN,
        "cors_exact": actual_rules == [cors_rule],
        "lifecycle_rule": next((r for r in lifecycle if r.get("name") == "landfall-abandoned-uploads"), None),
        "web_flag": True,
    }
    evidence["ok"] = evidence["cors_exact"] and bool(evidence["lifecycle_rule"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("PASS" if evidence["ok"] else "FAIL")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.output))
