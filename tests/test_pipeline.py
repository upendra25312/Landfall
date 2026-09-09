"""E13.2 / E12.8 — the guided pipeline-state endpoint + its front-end wiring."""
import datetime as _dt
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "web"))

_MT = _dt.datetime(2026, 9, 9, tzinfo=_dt.timezone.utc)


class _Down:
    def __init__(self, d):
        self._d = d

    def readall(self):
        return self._d


class _Blob:
    def __init__(self, name, rec):
        self.name = name
        self.size = len(rec["data"])
        self.last_modified = rec["mtime"]
        self.metadata = rec["metadata"]


class _Container:
    def __init__(self, store):
        self.store = store

    def download_blob(self, key):
        if key not in self.store:
            raise KeyError(key)
        return _Down(self.store[key]["data"])

    def list_blobs(self, name_starts_with="", include=None):
        for k, rec in list(self.store.items()):
            if k.startswith(name_starts_with):
                yield _Blob(k, rec)


def _rec(data: bytes):
    return {"data": data, "metadata": {}, "mtime": _MT}


def _inv_rec(rows: int):
    return {"data": b"hostname,vcpu\n" + b"a,2\n" * rows, "metadata": {"rows": str(rows)},
            "mtime": _MT}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example/api/projects/x")
    monkeypatch.setenv("STORAGE_URL", "https://s.blob.core.windows.net")
    import importlib
    import app as webapp
    importlib.reload(webapp)
    from fastapi.testclient import TestClient

    raw = {
        "engagements/contoso-ltd/dc-exit/_engagement.json": _rec(json.dumps(
            {"engagement": "contoso-ltd/dc-exit", "visibility": "all"}).encode()),
    }
    ans: dict = {}
    monkeypatch.setattr(webapp, "_raw_container", lambda: _Container(raw))
    monkeypatch.setattr(webapp, "_estimate_container", lambda: _Container(ans))
    return webapp, TestClient(webapp.app), raw, ans


def _pipe(c):
    r = c.get("/api/engagements/contoso-ltd/dc-exit/pipeline")
    assert r.status_code == 200, r.text
    return r.json()


def _steps(j):
    return {s["key"]: s for s in j["steps"]}


def test_empty_engagement_is_all_todo(client):
    _w, c, _raw, _ans = client
    j = _pipe(c)
    assert [s["done"] for s in j["steps"]] == [False, False, False, False]
    assert j["next"] == "uploads" and j["analysed"] is False
    assert _steps(j)["analysis"]["waiting_on"] == "uploads"


def test_inventory_uploaded_advances_to_analysis(client):
    _w, c, raw, _ans = client
    raw["engagements/contoso-ltd/dc-exit/inventory/servers.csv"] = _inv_rec(40)
    j = _pipe(c)
    st = _steps(j)
    assert st["uploads"]["done"] and "1 file" in st["uploads"]["detail"]
    assert not st["analysis"]["done"] and st["analysis"]["detail"] == "pending"
    assert st["analysis"]["waiting_on"] is None      # inventory is there, analysis can run
    assert j["next"] == "analysis"


def test_analysis_done_when_a_dq_report_has_rows(client):
    _w, c, raw, ans = client
    raw["engagements/contoso-ltd/dc-exit/inventory/servers.csv"] = _inv_rec(40)
    ans["engagements/contoso-ltd/dc-exit/_ingest/servers.dq.json"] = _rec(json.dumps(
        {"summary": {"file": "servers.csv", "table": "servers", "status": "ok",
                     "rows_loaded": 40, "confidence_hint": "Medium"}}).encode())
    j = _pipe(c)
    st = _steps(j)
    assert st["analysis"]["done"] and "40 rows" in st["analysis"]["detail"]
    assert j["analysed"] is True and j["next"] == "estimate"


def test_published_estimate_and_poe(client):
    _w, c, raw, ans = client
    raw["engagements/contoso-ltd/dc-exit/inventory/servers.csv"] = _inv_rec(40)
    ans["engagements/contoso-ltd/dc-exit/_ingest/servers.dq.json"] = _rec(json.dumps(
        {"summary": {"table": "servers", "status": "ok", "rows_loaded": 40}}).encode())
    ans["engagements/contoso-ltd/dc-exit/estimate/latest.json"] = _rec(b'{"meta":{}}')
    ans["engagements/contoso-ltd/dc-exit/estimate/landing_zone.json"] = _rec(
        json.dumps({"status": "ready"}).encode())
    j = _pipe(c)
    assert [s["done"] for s in j["steps"]] == [True, True, True, True]
    assert j["next"] is None


def test_poe_building_is_not_done(client):
    _w, c, raw, ans = client
    ans["engagements/contoso-ltd/dc-exit/estimate/latest.json"] = _rec(b"{}")
    ans["engagements/contoso-ltd/dc-exit/estimate/landing_zone.json"] = _rec(
        json.dumps({"status": "building"}).encode())
    j = _pipe(c)
    poe = _steps(j)["poe"]
    assert not poe["done"] and poe["detail"] == "building"


def test_pipeline_404_for_unknown_engagement(client):
    _w, c, _raw, _ans = client
    assert c.get("/api/engagements/acme/ghost/pipeline").status_code == 404


def test_chat_page_wires_the_strip(client):
    _w, c, _raw, _ans = client
    assert "<div id=pipeline" in c.get("/").text
    js = c.get("/static/chat.js").text
    assert "loadPipeline" in js and "/pipeline" in js
    assert "PIPE.analysed===false" in js                 # the non-blocking nudge
    assert ".pipe .step" in c.get("/static/chat.css").text
