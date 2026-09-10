"""Live synthetic blob/Event Grid ingestion and optional calculator queue journey."""
import argparse
import datetime as dt
import json
from pathlib import Path
import time

from smoke import _az, load_config
from validate_live import SUBSCRIPTION


def wait_json(container, name, timeout):
    from azure.core.exceptions import ResourceNotFoundError
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            return json.loads(container.download_blob(name).readall())
        except ResourceNotFoundError:
            time.sleep(5)
    raise TimeoutError(f"artifact not produced: {name}")


def run(output, queue_job):
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient
    from azure.storage.queue import QueueClient
    rc, account, _ = _az(["account", "show", "--query", "{id:id,user:user.name}"])
    assert rc == 0 and account["id"] == SUBSCRIPTION
    cfg = load_config()
    account_name = cfg["AZURE_STORAGE_ACCOUNT"]
    credential = AzureCliCredential()
    blobs = BlobServiceClient(f"https://{account_name}.blob.core.windows.net", credential=credential)
    raw, answers = blobs.get_container_client("raw"), blobs.get_container_client("answers")
    eid = "validation-c54/pipeline-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    result = {"engagement": eid, "retained_test_data": True, "status": "IN_PROGRESS"}
    output.mkdir(parents=True, exist_ok=True)
    try:
        raw.upload_blob(f"engagements/{eid}/_engagement.json", json.dumps({"engagement": eid,
            "customer": "Validation C54", "project": "Pipeline validation", "visibility": "owner",
            "created_by": account["user"], "region": "swedencentral"}), overwrite=False)
        raw.upload_blob(f"engagements/{eid}/inventory/servers.csv",
            b"server_id,hostname,env,os_name,vcpu,ram_gb,provisioned_disk_gb,used_disk_gb,powerstate\n"
            b"c54-1,c54-web01,prod,Ubuntu,2,16,128,90,poweredOn\n", overwrite=False)
        report = wait_json(answers, f"engagements/{eid}/_ingest/servers.dq.json", 300)
        result["ingestion"] = report["summary"]
        assert report["summary"]["status"] == "ok" and report["summary"]["rows_loaded"] == 1
        print("PASS: blob -> Event Grid -> Function -> SQL -> DQ report", flush=True)
        if queue_job:
            prefix = f"engagements/{eid}/estimate"
            spec = {"engagement": eid, "estimate_name": "C54 synthetic queue validation", "currency": "USD",
                    "region_default": "sweden-central", "line_items": [
                        {"service": "load-balancer", "config": {"tier": "standard", "rules": 11, "data_processed_gb": 2048}},
                        {"service": "application-gateway", "config": {"tier": "standard", "capacity_units": 2, "hours": 100}},
                    ]}
            spec_blob = prefix + "/_calc_spec.json"
            answers.upload_blob(spec_blob, json.dumps(spec), overwrite=False)
            queue = QueueClient(f"https://{account_name}.queue.core.windows.net", "calc-jobs", credential=credential)
            queue.send_message(json.dumps({"engagement": eid, "container": "answers", "prefix": prefix, "spec_blob": spec_blob}))
            summary = wait_json(answers, prefix + "/landing_zone.json", 600)
            result["calculator"] = summary
            assert summary["status"] == "ready" and summary["line_count"] == 2
            workbook = answers.download_blob(prefix + "/landing_zone.xlsx").readall()
            assert workbook.startswith(b"PK")
            (output / "calculator.xlsx").write_bytes(workbook)
            print("PASS: queue -> deployed calculator worker -> real Excel export", flush=True)
        result["status"] = "PASS"
    except Exception as exc:
        result.update(status="FAIL", error=type(exc).__name__, detail=str(exc)[:300])
    (output / "RESULTS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--queue", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.queue))
