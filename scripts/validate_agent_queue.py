"""Submit synthetic calculator work through the real agent/Function identity path."""
import argparse
import json
from pathlib import Path
import re
import time

from smoke import _az, load_config
from validate_live import SUBSCRIPTION


def run(eid, output):
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient
    assert re.fullmatch(r"validation-c54/pipeline-[0-9]{14}", eid)
    rc, account, _ = _az(["account", "show", "--query", "{id:id,user:user.name}"])
    assert rc == 0 and account["id"] == SUBSCRIPTION
    cfg = load_config()
    credential = AzureCliCredential()
    blob = BlobServiceClient(f"https://{cfg['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net", credential=credential)
    manifest = json.loads(blob.get_blob_client("raw", f"engagements/{eid}/_engagement.json").download_blob().readall())
    assert manifest["created_by"] == account["user"]
    answers = blob.get_container_client("answers")
    prefix = f"engagements/{eid}/estimate"
    output.mkdir(parents=True, exist_ok=True)
    result = {"engagement": eid, "retained_test_data": True}
    try:
        # A deliberately small synthetic published source: four platform services.
        answers.upload_blob(prefix + "/tools_raw.json", json.dumps({"landing_zone": {
            "hub": {"components": ["bastion"]}, "spokes": [{}]},
            "run_rate_extras": {"run_rate_monthly": {"egress": {"billable_gb": 1024}}}}), overwrite=True)
        with AIProjectClient(endpoint=cfg["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as project:
            with project.get_openai_client() as client:
                response = client.with_options(timeout=180, max_retries=0).responses.create(
                    input=f"[Active engagement: {eid}] The synthetic published tools_raw source is already staged. "
                          "Call build_calculator_estimate exactly once for this engagement now. Do not call "
                          "publish_estimate or any other mutating tool. Return the start status; do not poll.",
                    max_output_tokens=1200,
                    extra_body={"agent_reference": {"type": "agent_reference", "name": cfg["AGENT_ID"]}})
        result["tool_output"] = [i.model_dump(mode="json") for i in response.output if i.type in ("openapi_call", "openapi_call_output")]
        assert any(i.get("type") == "openapi_call" and "build_calculator_estimate" in i.get("name", "")
                   and json.loads(i["arguments"]).get("engagement") == eid for i in result["tool_output"])
        print("Agent invoked the calculator Function; waiting for the queued export.", flush=True)
        end = time.monotonic() + 600
        while time.monotonic() < end:
            summary = json.loads(answers.download_blob(prefix + "/landing_zone.json").readall())
            if summary.get("status") != "building":
                break
            time.sleep(5)
        result["calculator"] = summary
        assert summary["status"] == "ready" and summary["line_count"] == 4 and summary["monthly_total"] > 0
        workbook = answers.download_blob(prefix + "/landing_zone.xlsx").readall()
        assert workbook.startswith(b"PK")
        (output / "calculator.xlsx").write_bytes(workbook)
        result["status"] = "PASS"
    except Exception as exc:
        result.update(status="FAIL", error=type(exc).__name__, detail=str(exc)[:500])
    (output / "RESULTS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engagement", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.engagement, args.output))
