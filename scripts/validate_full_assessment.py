"""Run one retained synthetic assessment through Foundry and deployed Functions."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re

from smoke import _az, load_config
from validate_live import SUBSCRIPTION


def run(output: Path) -> int:
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient

    rc, account, _ = _az(["account", "show", "--query", "{id:id,user:user.name}"])
    assert rc == 0 and account["id"] == SUBSCRIPTION
    cfg = load_config()
    credential = AzureCliCredential()
    blobs = BlobServiceClient(
        f"https://{cfg['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net",
        credential=credential,
    )
    raw = blobs.get_container_client("raw")
    answers = blobs.get_container_client("answers")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    eid = f"validation-c58/full-{stamp}"
    assert re.fullmatch(r"validation-c58/full-[0-9]{14}", eid)
    result = {"engagement": eid, "retained_test_data": True, "status": "IN_PROGRESS"}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        manifest = {
            "engagement": eid, "customer": "Validation C58",
            "project": "Full assessment validation", "visibility": "owner",
            "created_by": account["user"], "region": "swedencentral",
        }
        prefix = f"engagements/{eid}"
        raw.upload_blob(prefix + "/_engagement.json", json.dumps(manifest), overwrite=False)
        raw.upload_blob(prefix + "/inventory/servers.csv", (
            "server_id,hostname,app_id,env,os_name,vcpu,ram_gb,provisioned_disk_gb,used_disk_gb,powerstate\n"
            "c58-s1,c58-web01,c58-app,prod,Ubuntu 22.04,2,8,128,80,poweredOn\n"
        ).encode(), overwrite=False)
        raw.upload_blob(prefix + "/inventory/applications.csv", (
            "app_id,app_name,criticality,internet_facing,compliance_scope,tech_stack\n"
            "c58-app,C58 Store,2,1,,python\n"
        ).encode(), overwrite=False)

        with AIProjectClient(endpoint=cfg["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as project:
            with project.get_openai_client() as client:
                response = client.with_options(timeout=300, max_retries=0).responses.create(
                    input=(f"[Active engagement: {eid}] Run the complete assessment now. "
                           "Call run_assessment exactly once. Do not call any other tool."),
                    max_output_tokens=1200,
                    extra_body={"agent_reference": {"type": "agent_reference", "name": cfg["AGENT_ID"]}},
                )
        items = [i.model_dump(mode="json") for i in response.output
                 if i.type in ("openapi_call", "openapi_call_output")]
        calls = [i for i in items if i["type"] == "openapi_call" and "run_assessment" in i.get("name", "")]
        assert len(calls) == 1 and json.loads(calls[0]["arguments"])["engagement"] == eid
        latest = json.loads(answers.download_blob(prefix + "/assessment/latest.json").readall())
        result.update(agent_status=response.status, tool_output=items,
                      assessment={"status": latest.get("status"),
                                  "failed_stage": latest.get("failed_stage"),
                                  "stages": latest.get("stages")})
        assert latest["status"] == "completed", latest.get("error") or latest.get("failed_stage")
        names = {b.name for b in answers.list_blobs(name_starts_with=prefix + "/estimate/")}
        expected = {prefix + "/estimate/latest.json", prefix + "/estimate/latest.xlsx",
                    prefix + "/estimate/latest.docx", prefix + "/estimate/latest.pptx"}
        assert expected <= names, sorted(expected - names)
        result["published_files"] = sorted(expected)
        result["status"] = "PASS"
    except Exception as exc:
        result.update(status="FAIL", error=type(exc).__name__, detail=str(exc)[:800])
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["status"], eid, flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.output))
