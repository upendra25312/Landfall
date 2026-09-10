"""Two bounded read-only queries through the deployed Foundry agent and its tool identity."""
import argparse
import datetime as dt
import json
from pathlib import Path

from smoke import _az, load_config
from validate_live import SUBSCRIPTION


def verify_output(items, eid):
    calls = [i for i in items if i.get("type") == "openapi_call" and "query_inventory" in i.get("name", "")]
    assert len(calls) == 1 and json.loads(calls[0]["arguments"])["engagement"] == eid
    results = [i for i in items if i.get("type") == "openapi_call_output" and i.get("call_id") == calls[0]["call_id"]]
    assert len(results) == 1, "missing actual query tool output"
    payload = json.loads(results[0]["output"])
    if "response" in payload:
        payload = json.loads(payload["response"]) if isinstance(payload["response"], str) else payload["response"]
    assert payload["row_count"] == 1 and len(payload["rows"][0]) == 1
    count = payload["rows"][0][0]
    assert isinstance(count, (int, float)) and (count > 0 if eid == "_default_/_default_" else count == 0)
    return count


def run(output):
    rc, subscription, _ = _az(["account", "show", "--query", "id"])
    if rc or subscription != SUBSCRIPTION:
        raise RuntimeError("wrong Azure subscription")
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    cfg = load_config()
    checks = []
    with AIProjectClient(endpoint=cfg["FOUNDRY_PROJECT_ENDPOINT"], credential=AzureCliCredential()) as project:
        with project.get_openai_client() as client:
            for eid in ("_default_/_default_", "validation-c54/empty"):
                try:
                    response = client.with_options(timeout=180, max_retries=0).responses.create(
                        input=f"[Active engagement: {eid}] Call query_inventory exactly once with engagement {eid} "
                              "to count servers. Return only the count and evidence. Do not call any write tools.",
                        max_output_tokens=1200,
                        extra_body={"agent_reference": {"type": "agent_reference", "name": cfg["AGENT_ID"]}})
                    items = [item.model_dump(mode="json") for item in response.output
                             if item.type not in ("mcp_list_tools", "message")]
                    # Tool calls/results contain this count query only; no token or headers.
                    checks.append({"engagement": eid, "status": response.status, "text": response.output_text,
                                   "output": items, "verified_count": verify_output(items, eid),
                                   "usage": response.usage.model_dump() if response.usage else None})
                except Exception as exc:
                    checks.append({"engagement": eid, "status": "FAIL", "error": type(exc).__name__,
                                   "http_status": getattr(exc, "status_code", None), "detail": str(exc)[:600]})
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps({"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                              "checks": checks}, indent=2), encoding="utf-8")
                print(eid, checks[-1]["status"], flush=True)
    return 0 if all(c["status"] == "completed" for c in checks) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-recorded", type=Path)
    args = parser.parse_args()
    if args.verify_recorded:
        recorded = json.loads(args.verify_recorded.read_text(encoding="utf-8"))
        verified = [{"engagement": c["engagement"], "count": verify_output(c["output"], c["engagement"])} for c in recorded["checks"]]
        args.output.write_text(json.dumps({"status": "PASS", "source": str(args.verify_recorded), "checks": verified}, indent=2), encoding="utf-8")
        print("PASS: actual scoped tool outputs verified")
    else:
        raise SystemExit(run(args.output))
