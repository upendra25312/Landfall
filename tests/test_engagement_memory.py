"""E11.26 — per-engagement conversation persistence + engagement export / import."""
import datetime as _dt
import io
import json
import os
import sys
import zipfile

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "web"))


class _Down:
    def __init__(self, d):
        self._d = d

    def readall(self):
        return self._d


class _BlobClient:
    def __init__(self, store, key):
        self.store, self.key, self._staged = store, key, {}

    def stage_block(self, bid, data):
        self._staged[bid] = bytes(data)

    def commit_block_list(self, blocks, metadata=None, content_settings=None):
        self.store[self.key] = {"data": b"".join(self._staged[b.id] for b in blocks),
                                "metadata": dict(metadata or {}),
                                "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)}

    def upload_blob(self, data, overwrite=False):
        self.store[self.key] = {"data": data if isinstance(data, bytes) else data.encode(),
                                "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)}

    def download_blob(self):
        if self.key not in self.store:
            raise KeyError(self.key)
        return _Down(self.store[self.key]["data"])


class _Blob:
    def __init__(self, name, rec):
        self.name = name
        self.size = len(rec["data"])
        self.last_modified = rec["mtime"]
        self.metadata = rec["metadata"]


class _Container:
    def __init__(self, store):
        self.store = store

    def get_blob_client(self, key):
        return _BlobClient(self.store, key)

    def upload_blob(self, name, data, overwrite=False, metadata=None, content_settings=None):
        self.store[name] = {"data": data if isinstance(data, bytes) else data.encode(),
                            "metadata": dict(metadata or {}),
                            "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)}

    def download_blob(self, key):
        if key not in self.store:
            raise KeyError(key)
        return _Down(self.store[key]["data"])

    def list_blobs(self, name_starts_with="", include=None):
        for k, rec in list(self.store.items()):
            if k.startswith(name_starts_with):
                yield _Blob(k, rec)

    def delete_blob(self, key):
        del self.store[key]


class _Resp:
    def __init__(self, rid, text):
        self.id, self.output_text, self.status, self.output = rid, text, "completed", []


@pytest.fixture()
def app_client(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://x/api/projects/x")
    monkeypatch.setenv("STORAGE_URL", "https://s.blob.core.windows.net")
    import importlib
    import app as webapp
    import web_runtime
    import web_storage
    importlib.reload(webapp)
    from fastapi.testclient import TestClient

    raw_store = {
        "engagements/contoso-ltd/dc-exit/_engagement.json": {
            "data": json.dumps({"engagement": "contoso-ltd/dc-exit", "customer": "Contoso Ltd",
                                "project": "DC Exit", "visibility": "all", "created_by": "bob"}).encode(),
            "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)},
    }
    ans_store = {}
    raw, ans = _Container(raw_store), _Container(ans_store)
    monkeypatch.setattr(web_storage, "_raw_container", lambda: raw)
    monkeypatch.setattr(web_storage, "_estimate_container", lambda: ans)
    monkeypatch.setattr(web_runtime, "AGENT_NAME", "landfall-migration-estimator")

    seq = {"n": 0}

    class _OAI:
        class responses:
            @staticmethod
            def create(**kw):
                seq["n"] += 1
                _OAI._last = kw
                return _Resp(f"resp_{seq['n']}", f"answer {seq['n']}")
    monkeypatch.setattr(web_runtime, "_openai_client", lambda: _OAI())
    return webapp, TestClient(webapp.app, headers={"x-ms-client-principal-name": "bob"}), raw_store, ans_store, _OAI


def test_chat_persists_per_engagement_and_chains(app_client):
    _w, c, _raw, ans, oai = app_client
    r = c.post("/api/chat", json={"message": "how many prod servers?",
                                  "engagement": "contoso-ltd/dc-exit"})
    assert r.json()["answer"] == "answer 1"
    # first turn: no previous_response_id
    assert "previous_response_id" not in oai._last

    r = c.post("/api/chat", json={"message": "and their vCPU?",
                                  "engagement": "contoso-ltd/dc-exit"})
    assert r.json()["answer"] == "answer 2"
    # second turn chains off the stored pointer
    assert oai._last["previous_response_id"] == "resp_1"

    saved = json.loads(ans["engagements/contoso-ltd/dc-exit/_chat.json"]["data"])
    assert saved["current_response_id"] == "resp_2"
    assert [t["text"] for t in saved["turns"]] == [
        "how many prod servers?", "answer 1", "and their vCPU?", "answer 2"]


def test_chat_get_returns_transcript(app_client):
    _w, c, _raw, _ans, _oai = app_client
    c.post("/api/chat", json={"message": "hi", "engagement": "contoso-ltd/dc-exit"})
    j = c.get("/api/engagements/contoso-ltd/dc-exit/chat").json()
    assert j["current_response_id"] == "resp_1"
    assert len(j["turns"]) == 2


def test_new_chat_archives_not_destroys(app_client):
    _w, c, _raw, ans, oai = app_client
    c.post("/api/chat", json={"message": "hi", "engagement": "contoso-ltd/dc-exit"})
    r = c.post("/api/engagements/contoso-ltd/dc-exit/chat/new")
    assert r.json()["archived"] == 1
    doc = json.loads(ans["engagements/contoso-ltd/dc-exit/_chat.json"]["data"])
    assert doc["turns"] == [] and doc["current_response_id"] is None
    assert doc["archived"][0]["last_response_id"] == "resp_1"
    # next turn starts a fresh chain (no previous_response_id)
    c.post("/api/chat", json={"message": "again", "engagement": "contoso-ltd/dc-exit"})
    assert "previous_response_id" not in oai._last


def test_export_then_import_roundtrips(app_client):
    webapp, c, raw, ans, _oai = app_client
    # give the engagement an upload + an estimate + a chat
    raw["engagements/contoso-ltd/dc-exit/inventory/servers.csv"] = {
        "data": b"hostname,vcpu\na,2\n", "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)}
    ans["engagements/contoso-ltd/dc-exit/estimate/latest.json"] = {
        "data": b'{"meta":{"package_id":"P1"}}', "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)}
    c.post("/api/chat", json={"message": "hi", "engagement": "contoso-ltd/dc-exit"})

    z = c.get("/api/engagements/contoso-ltd/dc-exit/export")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    names = set(zf.namelist())
    assert "raw/_engagement.json" in names
    assert "raw/inventory/servers.csv" in names
    assert "answers/estimate/latest.json" in names
    assert "answers/_chat.json" in names
    assert json.loads(zf.read("export.json"))["engagement"] == "contoso-ltd/dc-exit"

    # wipe it, re-import
    for k in list(raw):
        if k.startswith("engagements/contoso-ltd/dc-exit/"):
            del raw[k]
    for k in list(ans):
        del ans[k]

    r = c.post("/api/engagements/import",
               files={"file": ("e.zip", z.content, "application/zip")})
    assert r.status_code == 201, r.text
    assert r.json()["engagement"] == "contoso-ltd/dc-exit"
    assert "engagements/contoso-ltd/dc-exit/_engagement.json" in raw
    assert "engagements/contoso-ltd/dc-exit/inventory/servers.csv" in raw
    assert "engagements/contoso-ltd/dc-exit/estimate/latest.json" in ans


def test_import_refuses_existing_without_overwrite(app_client):
    _w, c, _raw, _ans, _oai = app_client
    c.post("/api/chat", json={"message": "hi", "engagement": "contoso-ltd/dc-exit"})
    z = c.get("/api/engagements/contoso-ltd/dc-exit/export").content
    r = c.post("/api/engagements/import", files={"file": ("e.zip", z, "application/zip")})
    assert r.status_code == 409
    r = c.post("/api/engagements/import", data={"overwrite": "true"},
               files={"file": ("e.zip", z, "application/zip")})
    assert r.status_code == 201


def test_import_rejects_non_zip(app_client):
    _w, c, *_ = app_client
    r = c.post("/api/engagements/import", files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert r.status_code == 400
