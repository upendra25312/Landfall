"""Activate and prove the event-driven calculator Job without provisioning."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import time

from smoke import _az, load_config
from validate_live import GROUP, SUBSCRIPTION

APP = "ca-calc-tmglwfatwcsa2"
JOB = "ca-calc-tmglwfatwcsa2"
QUEUE = "calc-jobs"


def run(output: Path) -> int:
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient
    from azure.ai.projects import AIProjectClient

    rc, app, err = _az(["containerapp", "show", "--subscription", SUBSCRIPTION,
                         "--resource-group", GROUP, "--name", APP])
    if rc:
        raise RuntimeError(err[:400])
    p = app["properties"]
    revision = p["latestReadyRevisionName"]
    container = p["template"]["containers"][0]
    identity = next(iter(app["identity"]["userAssignedIdentities"]))
    env = {x["name"]: x.get("value", "") for x in container.get("env", [])}
    required = ("APPLICATIONINSIGHTS_CONNECTION_STRING", "AZURE_CLIENT_ID", "STORAGE_URL",
                "STORAGE_QUEUE_URL", "CALC_QUEUE")
    if any(not env.get(k) for k in required):
        raise RuntimeError("legacy calculator is missing required environment configuration")

    rc, jobs, _ = _az(["containerapp", "job", "list", "--subscription", SUBSCRIPTION,
                        "--resource-group", GROUP])
    exists = rc == 0 and any(x.get("name") == JOB for x in (jobs or []))
    if not exists:
        az = shutil.which("az") or "az.cmd"
        cmd = [az, "containerapp", "job", "create", "--subscription", SUBSCRIPTION,
               "--resource-group", GROUP, "--name", JOB,
               "--environment", p["managedEnvironmentId"], "--trigger-type", "Event",
               "--replica-timeout", "1800", "--replica-retry-limit", "1",
               "--replica-completion-count", "1", "--parallelism", "1",
               "--polling-interval", "30", "--min-executions", "0", "--max-executions", "3",
               "--scale-rule-name", "calc-queue", "--scale-rule-type", "azure-queue",
               "--scale-rule-metadata", f"accountName={load_config()['AZURE_STORAGE_ACCOUNT']}",
               f"queueName={QUEUE}", "queueLength=1",
               "--scale-rule-identity", identity, "--mi-user-assigned", identity,
               "--registry-server", container["image"].split("/", 1)[0],
               "--registry-identity", identity, "--image", container["image"],
               "--cpu", "2", "--memory", "4Gi", "--command", "python", "job.py",
               "--env-vars", *[f"{k}={env[k]}" for k in required], "--output", "none"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode:
            raise RuntimeError(f"job create failed: {proc.stderr[:500]}")

    # Stop the old queue consumer only after the replacement exists. Reactivation
    # below is the rollback if the proof job does not complete.
    rc, _, err = _az(["containerapp", "revision", "deactivate", "--subscription", SUBSCRIPTION,
                      "--resource-group", GROUP, "--name", APP, "--revision", revision])
    if rc:
        raise RuntimeError(f"legacy revision deactivation failed: {err[:400]}")

    cfg = load_config()
    credential = AzureCliCredential()
    answers = BlobServiceClient(
        f"https://{cfg['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net",
        credential=credential).get_container_client("answers")
    eid = "validation-c58/calc-job-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    prefix = f"engagements/{eid}/estimate"
    summary = None
    deadline = time.monotonic() + 600
    try:
        from azure.core.exceptions import ResourceNotFoundError
        # Use the deployed managed-identity Function path to enqueue work. The
        # operator identity deliberately has no queue-write permission.
        answers.upload_blob(prefix + "/tools_raw.json", json.dumps({
            "landing_zone": {"hub": {"components": ["load-balancer"]}, "spokes": [{}]},
            "run_rate_extras": {"run_rate_monthly": {"egress": {"billable_gb": 100}}},
        }), overwrite=False)
        with AIProjectClient(endpoint=cfg["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as project:
            with project.get_openai_client() as client:
                response = client.with_options(timeout=180, max_retries=0).responses.create(
                    input=f"[Active engagement: {eid}] The synthetic tools_raw source is staged. "
                          "Call build_calculator_estimate exactly once for this engagement. "
                          "Do not call publish_estimate or any other tool and do not poll.",
                    max_output_tokens=1200,
                    extra_body={"agent_reference": {"type": "agent_reference", "name": cfg["AGENT_ID"]}})
        calls = [x.model_dump(mode="json") for x in response.output if x.type == "openapi_call"]
        if not any("build_calculator_estimate" in x.get("name", "") for x in calls):
            raise RuntimeError("agent did not enqueue the calculator work")
        while time.monotonic() < deadline:
            try:
                summary = json.loads(answers.download_blob(prefix + "/landing_zone.json").readall())
                if summary.get("status") != "building":
                    break
            except ResourceNotFoundError:
                pass
            time.sleep(5)
        if not summary or summary.get("status") != "ready":
            raise RuntimeError(f"calculator Job did not produce a ready result: {summary}")
        rc, executions, err = _az(["containerapp", "job", "execution", "list",
                                   "--subscription", SUBSCRIPTION, "--resource-group", GROUP,
                                   "--name", JOB])
        if rc or not executions:
            raise RuntimeError(f"no Job execution evidence: {err[:300]}")
        statuses = [x.get("properties", {}).get("status") for x in executions]
        evidence = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "subscription": SUBSCRIPTION, "resource_group": GROUP,
                    "job": JOB, "trigger": "Event", "min_executions": 0,
                    "legacy_revision": revision, "legacy_revision_active": False,
                    "engagement": eid, "calculator_status": summary.get("status"),
                    "line_count": summary.get("line_count"), "monthly_total": summary.get("monthly_total"),
                    "execution_statuses": statuses, "ok": "Succeeded" in statuses}
        if not evidence["ok"]:
            raise RuntimeError(f"Job execution did not succeed: {statuses}")
    except Exception:
        _az(["containerapp", "revision", "activate", "--subscription", SUBSCRIPTION,
             "--resource-group", GROUP, "--name", APP, "--revision", revision])
        raise
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("PASS")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.output))
