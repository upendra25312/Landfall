"""Serve `src/web/app.py` locally with **offline stubs** — no Azure, no live model —
for the Playwright browser-automation harness (PRD §4.17 / E13.15).

    python tests/browser/serve.py --port 8850 [--seed full|empty]

- blob storage  -> an in-memory store (`_Store`), pre-seeded with one demo
  engagement `contoso-ltd/dc-exit` (an `_engagement.json`, an uploaded inventory
  file with row metadata, a data-quality report, and a published estimate) so the
  guided pipeline strip has real state to render.
- the Foundry agent -> a canned response, so `/api/chat` answers without a model.

`tests/browser/conftest.py` launches this as a subprocess for the pytest specs;
you can also run it by hand and drive it with the Playwright MCP.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import os
import re
import sys
from types import SimpleNamespace

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path[:0] = [os.path.join(_ROOT, "src", "web"), os.path.join(_ROOT, "src", "api")]

_MT = _dt.datetime(2026, 9, 9, 12, 0, tzinfo=_dt.timezone.utc)


class _Down:
    def __init__(self, data: bytes):
        self._d = data

    def readall(self) -> bytes:
        return self._d


class _Blob:
    def __init__(self, name: str, rec: dict):
        self.name = name
        self.size = len(rec["data"])
        self.last_modified = rec["mtime"]
        self.metadata = rec["metadata"]


class _BlobClient:
    """Enough of BlobClient for the streamed upload path (stage_block / commit)."""
    def __init__(self, store: "_Store", key: str):
        self.store = store
        self.key = key
        self._blocks: list[bytes] = []

    def stage_block(self, block_id, data, **_kw):
        self._blocks.append(data.read() if hasattr(data, "read") else bytes(data))

    def commit_block_list(self, _block_list, metadata=None, **_kw):
        self.store.put(self.key, b"".join(self._blocks), metadata or {})

    def upload_blob(self, data, overwrite=True, metadata=None, **_kw):
        raw = data.read() if hasattr(data, "read") else (
            data if isinstance(data, (bytes, bytearray)) else str(data).encode())
        self.store.put(self.key, bytes(raw), metadata or {})

    def download_blob(self, **_kw):
        return _Down(self.store.get(self.key))

    def get_blob_properties(self):
        raise KeyError(self.key)


class _Store:
    def __init__(self):
        self.d: dict[str, dict] = {}

    def put(self, key: str, data: bytes, metadata: dict | None = None):
        self.d[key] = {"data": data, "metadata": {k: str(v) for k, v in (metadata or {}).items()},
                       "mtime": _MT}

    def get(self, key: str) -> bytes:
        if key not in self.d:
            raise KeyError(key)
        return self.d[key]["data"]

    # --- container-client surface -------------------------------------------
    def download_blob(self, key: str):
        return _Down(self.get(key))

    def list_blobs(self, name_starts_with: str = "", include=None):
        for k, rec in list(self.d.items()):
            if k.startswith(name_starts_with):
                yield _Blob(k, rec)

    def upload_blob(self, key: str, data, overwrite=True, metadata=None, **_kw):
        raw = data.read() if hasattr(data, "read") else (
            data if isinstance(data, (bytes, bytearray)) else str(data).encode())
        self.put(key, bytes(raw), metadata or {})

    def delete_blob(self, key: str):
        self.d.pop(key, None)

    def get_blob_client(self, key: str):
        return _BlobClient(self, key)


class _FakeResp:
    def __init__(self, text: str):
        self.output_text = text
        self.status = "completed"
        self.id = "resp_offline_1"
        self.output = [SimpleNamespace(type="openapi_call", call_id="offline-query", name="query_inventory_query_inventory"), SimpleNamespace(
            type="openapi_call_output", call_id="offline-query", output={"response": json.dumps({
                "columns": ["hostname", "vcpu"], "rows": [["web01", 4]],
                "sql": "SELECT hostname, vcpu FROM servers",
            })})]


class _FakeResponses:
    def __init__(self, raw=None, answers=None):
        self.raw, self.answers = raw, answers

    def create(self, **kwargs):
        q = str(kwargs.get("input", "")).lower()
        if "call run_engagement" in q and self.raw is not None:
            from ingest.core import normalize
            from ingest.dq import build_report
            eid = re.search(r"\[active engagement: ([^\s.]+)", q).group(1)
            for blob in self.raw.list_blobs(name_starts_with=f"engagements/{eid}/inventory/"):
                if blob.name.endswith("/.keep"):
                    continue
                filename = blob.name.rsplit("/", 1)[-1]
                normalized = normalize(filename, self.raw.get(blob.name))
                report = build_report([normalized])
                summary = {"file": filename, "table": normalized.table, "profile": normalized.profile,
                           "rows_in": normalized.row_count_in, "rows_loaded": len(normalized.rows),
                           "rows_rejected": 0, "status": "ok", "confidence_hint": report["confidence_hint"],
                           "findings": report["findings"]}
                self.answers.put(f"engagements/{eid}/_ingest/{filename.rsplit('.', 1)[0]}.dq.json",
                                 json.dumps({"summary": summary}).encode())
        if "estimate" in q or "assessment" in q:
            body = ("Here is the full estimate for this engagement.\n\n"
                    "Answer | Basis: assemble_estimate (F1-F12) | Assumptions: house "
                    "defaults | Data gaps: none | Confidence: Medium")
        else:
            body = ("This engagement has an uploaded inventory and a completed analysis.\n\n"
                    "Answer | Basis: query_inventory | Assumptions: none | Data gaps: "
                    "none | Confidence: Medium")
        return _FakeResp(body)


class _FakeOpenAI:
    def __init__(self, raw=None, answers=None):
        self.responses = _FakeResponses(raw, answers)

    def with_options(self, **_kw):
        return self


def _seed(raw: _Store, ans: _Store, mode: str):
    if mode == "empty":
        return
    eid = "contoso-ltd/dc-exit"
    raw.put(f"engagements/{eid}/_engagement.json", json.dumps({
        "engagement": eid, "customer": "Contoso Ltd", "project": "DC Exit",
        "visibility": "all", "target_region": "swedencentral", "dr_region": "norwayeast",
        "currency": "USD", "licensing_program": "MCA", "status": "draft",
        "created_by": "demo@contoso.test", "created_at": "2026-09-08T09:00:00+00:00",
    }).encode())
    raw.put(f"engagements/{eid}/inventory/servers.csv",
            b"hostname,vcpu,ram_gb\n" + b"web01,4,16\n" * 40,
            {"profile": "server inventory", "rows": "40", "columns": "3",
             "uploaded_by": "demo@contoso.test"})
    ans.put(f"engagements/{eid}/_ingest/servers.dq.json", json.dumps({
        "summary": {"file": "servers.csv", "table": "servers", "status": "ok",
                    "profile": "server inventory", "rows_in": 40, "rows_loaded": 40,
                    "rows_rejected": 0, "confidence_hint": "Medium", "findings": []},
    }).encode())
    ans.put(f"engagements/{eid}/estimate/latest.json", json.dumps({
        "meta": {"engagement": eid}, "figures": [{"id": "F1", "key": "run_rate_monthly"}],
        "summary_markdown": "# Contoso — DC Exit\nRun-rate ~$119,000/mo (F1).",
    }).encode())
    # a second engagement so the picker has something to switch to
    raw.put("engagements/northwind/pilot/_engagement.json", json.dumps({
        "engagement": "northwind/pilot", "customer": "Northwind", "project": "Pilot",
        "visibility": "all", "created_at": "2026-09-07T09:00:00+00:00",
    }).encode())


def build_app(seed: str = "full"):
    # Scope process configuration to the standalone harness, not fixture imports.
    os.environ.setdefault("STORAGE_URL", "https://offline.blob.core.windows.net")
    os.environ.setdefault("FOUNDRY_PROJECT_ENDPOINT", "https://offline/api/projects/x")
    os.environ.setdefault("AGENT_ID", "landfall-migration-estimator")
    os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)
    import app as webapp
    import web_runtime
    import web_storage

    raw, ans = _Store(), _Store()
    _seed(raw, ans, seed)
    web_storage._raw_container = lambda: raw
    web_storage._estimate_container = lambda: ans
    web_runtime._openai_client = lambda: _FakeOpenAI(raw, ans)
    web_storage._blob_state.clear()
    return webapp.app, raw, ans


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8850)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--seed", choices=("full", "empty"), default="full")
    args = ap.parse_args(argv)

    import uvicorn
    application, _raw, _ans = build_app(args.seed)
    uvicorn.run(application, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
