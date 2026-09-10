"""Bounded, non-persistent service operations; never print credentials or content."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.request

from smoke import _az, load_config
from validate_live import SUBSCRIPTION, GROUP


def run():
    rc, account, _ = _az(["account", "show", "--query", "id"])
    if rc or account != SUBSCRIPTION:
        return [{"check": "subscription", "status": "FAIL", "detail": "Wrong or unavailable Azure session"}]
    cfg = load_config()
    # azd stores the renderer key locally; read it only into memory.
    cfg.update({k: v for k, v in os.environ.items() if k.startswith("DRAWIO_")})
    checks = []

    def probe(name, operation):
        try:
            detail = operation()
            checks.append({"check": name, "status": "PASS", "detail": detail})
        except Exception as exc:
            # Service messages can contain URLs/headers; retain only safe classification.
            checks.append({"check": name, "status": "BLOCKED" if isinstance(exc, ModuleNotFoundError) else "FAIL", "detail": type(exc).__name__,
                           "http_status": getattr(exc, "status_code", getattr(exc, "code", None))})

    from azure.identity import AzureCliCredential
    credential = AzureCliCredential(process_timeout=30)

    def agent():
        from azure.ai.projects import AIProjectClient
        with AIProjectClient(endpoint=cfg["FOUNDRY_PROJECT_ENDPOINT"], credential=credential,
                             connection_timeout=20, read_timeout=30, retry_total=0) as client:
            found = client.agents.get(cfg["AGENT_ID"])
            assert found is not None
        return "Configured agent definition retrieved; no inference performed"

    def search():
        from azure.search.documents import SearchClient
        with SearchClient(cfg["AZURE_SEARCH_ENDPOINT"], cfg["AZURE_SEARCH_INDEX_NAME"], credential,
                          connection_timeout=20, read_timeout=30, retry_total=0) as client:
            count = client.get_document_count()
            assert isinstance(count, int) and count >= 0
        return {"indexed_documents": count, "operation": "authenticated index document count"}

    def render():
        rc, host, _ = _az(["containerapp", "show", "--subscription", SUBSCRIPTION,
                            "-g", GROUP, "-n", "ca-drawio-tmglwfatwcsa2",
                            "--query", "properties.configuration.ingress.fqdn"])
        assert rc == 0 and isinstance(host, str)
        key = cfg["DRAWIO_RENDER_KEY"]
        assert key
        request = urllib.request.Request(f"https://{host}/render", method="POST",
            data=b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="blue"/></svg>',
            headers={"Content-Type": "image/svg+xml", "X-Drawio-Key": key})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(1024 * 1024)
            assert response.status == 200 and data.startswith(b"\x89PNG\r\n\x1a\n")
        return {"operation": "authenticated SVG to PNG", "bytes": len(data)}

    probe("foundry_agent_read", agent)
    probe("search_index_read", search)
    probe("drawio_render", render)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = run()
    result = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "checks": checks,
              "ok": all(c["status"] == "PASS" for c in checks),
              "not_validated": ["Signed-in web journeys", "Live SQL/tool and model round-trip", "Calculator queue job"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for check in checks:
        print(f"{check['check']}: {check['status']}", flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
