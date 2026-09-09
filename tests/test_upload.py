"""E11.6 / E11.24 — engagement upload panel: validation, peek, and the web routes."""
import datetime as _dt
import io
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "web"))

import uploads as up  # noqa: E402


# --- pure: classify + peek --------------------------------------------------

def _xlsx_bytes(headers, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_classify_accepts_csv_and_xlsx():
    ok, kind, _ = up.classify("servers.csv", b"hostname,vcpu,ram_gb\n")
    assert ok and kind == "inventory"
    ok, kind, _ = up.classify("RVTools.xlsx", b"PK\x03\x04rest")
    assert ok and kind == "inventory"
    ok, kind, _ = up.classify("network-diagram.pdf", b"%PDF-1.7")
    assert ok and kind == "docs"


def test_classify_rejects_macro_and_fakes():
    ok, _, reason = up.classify("book.xlsm", b"PK\x03\x04")
    assert not ok and "macro" in reason
    ok, _, reason = up.classify("evil.exe", b"MZ")
    assert not ok
    ok, _, reason = up.classify("notreally.xlsx", b"<html>")
    assert not ok and "doesn't look like" in reason
    ok, _, reason = up.classify("blob.csv", b"\x00\x01\x02\x03binary")
    assert not ok


def test_peek_csv_profile_and_rowcount():
    data = b"VM,Powerstate,CPUs,Memory\nweb01,poweredOn,4,8192\nweb02,poweredOn,2,4096\n"
    info = up.peek("vinfo.csv", data)
    assert info["rows"] == 2 and info["columns"] == 4
    assert "RVTools" in info["profile"]


def test_peek_xlsx():
    data = _xlsx_bytes(["hostname", "vcpu", "ram_gb"], [["a", 2, 4], ["b", 4, 8], ["c", 8, 16]])
    info = up.peek("servers.xlsx", data)
    assert info["rows"] == 3 and info["columns"] == 3
    assert "server" in info["profile"]


# --- web routes ------------------------------------------------------------

class _Down:
    def __init__(self, data):
        self._d = data

    def readall(self):
        return self._d


class _BlobClient:
    def __init__(self, store, key):
        self.store, self.key, self._staged = store, key, {}

    def stage_block(self, block_id, data):
        self._staged[block_id] = bytes(data)

    def commit_block_list(self, blocks, metadata=None, content_settings=None):
        data = b"".join(self._staged[b.id] for b in blocks)
        self.store[self.key] = {"data": data, "metadata": dict(metadata or {}),
                                "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)}


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

    def download_blob(self, key):
        if key not in self.store:
            raise KeyError(key)
        return _Down(self.store[key]["data"])

    def list_blobs(self, name_starts_with="", include=None):
        for k, rec in list(self.store.items()):
            if k.startswith(name_starts_with):
                yield _Blob(k, rec)

    def delete_blob(self, key):
        if key not in self.store:
            raise KeyError(key)
        del self.store[key]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example/api/projects/x")
    monkeypatch.setenv("STORAGE_URL", "https://s.blob.core.windows.net")
    import importlib
    import app as webapp
    importlib.reload(webapp)
    from fastapi.testclient import TestClient

    store = {
        "engagements/contoso-ltd/dc-exit/_engagement.json": {
            "data": json.dumps({"engagement": "contoso-ltd/dc-exit", "customer": "Contoso Ltd",
                                "project": "DC Exit", "visibility": "all"}).encode(),
            "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)},
    }
    cont = _Container(store)
    monkeypatch.setattr(webapp, "_raw_container", lambda: cont)
    return webapp, TestClient(webapp.app), store


def test_upload_lands_in_engagement_inventory_folder(client):
    _w, c, store = client
    data = b"hostname,vcpu,ram_gb\nweb01,4,8\nweb02,2,4\n"
    r = c.post("/api/engagements/contoso-ltd/dc-exit/upload",
               files={"file": ("servers.csv", data, "text/csv")}, data={"kind": "auto"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["kind"] == "inventory" and j["rows"] == 2 and j["size"] == len(data)
    assert j["path"] == "raw/engagements/contoso-ltd/dc-exit/inventory/servers.csv"
    assert "engagements/contoso-ltd/dc-exit/inventory/servers.csv" in store
    # ... and nowhere else
    assert not any("/docs/" in k for k in store)


def test_upload_rejects_unknown_engagement(client):
    _w, c, _s = client
    r = c.post("/api/engagements/acme/ghost/upload",
               files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 404


def test_upload_rejects_macro_office(client):
    _w, c, _s = client
    r = c.post("/api/engagements/contoso-ltd/dc-exit/upload",
               files={"file": ("bad.xlsm", b"PK\x03\x04stuff", "application/octet-stream")})
    assert r.status_code == 415
    assert "macro" in r.json()["error"]


def test_upload_path_traversal_is_blocked(client):
    _w, c, _s = client
    r = c.post("/api/engagements/..%2f..%2fetc/passwd/upload",
               files={"file": ("x.csv", b"a\n1\n", "text/csv")})
    assert r.status_code == 404


def test_files_manifest_and_delete(client):
    _w, c, _s = client
    c.post("/api/engagements/contoso-ltd/dc-exit/upload",
           files={"file": ("servers.csv", b"hostname,vcpu\na,2\n", "text/csv")})
    c.post("/api/engagements/contoso-ltd/dc-exit/upload", data={"kind": "docs"},
           files={"file": ("dr-plan.pdf", b"%PDF-1.4 stuff", "application/pdf")})
    j = c.get("/api/engagements/contoso-ltd/dc-exit/files").json()
    assert j["count"] == 2
    names = {f["name"]: f for f in j["files"]}
    assert names["servers.csv"]["kind"] == "inventory"
    assert names["dr-plan.pdf"]["kind"] == "docs"

    d = c.request("DELETE", "/api/engagements/contoso-ltd/dc-exit/files/servers.csv")
    assert d.status_code == 200 and d.json()["deleted"] == "servers.csv"
    assert c.get("/api/engagements/contoso-ltd/dc-exit/files").json()["count"] == 1


def test_chat_page_has_upload_panel(client):
    _w, c, _s = client
    html = c.get("/").text
    assert "uploadpanel" in html and "Drop files here" in html
    assert "/upload" in html and "showUpload" in html


# --- C20 / E11.6+E11.24: Start analysis + data-quality summary -------------

def _dq_report(file, table, rows_loaded, confidence="Medium", findings=None, rows_rejected=0):
    return json.dumps({"summary": {
        "file": file, "table": table, "profile": table + "-like",
        "rows_in": rows_loaded + rows_rejected, "rows_loaded": rows_loaded,
        "rows_rejected": rows_rejected, "status": "ok",
        "confidence_hint": confidence, "findings": findings or [],
    }}).encode()


@pytest.fixture()
def analysed(client, monkeypatch):
    webapp, c, store = client
    answers = {
        "engagements/contoso-ltd/dc-exit/_ingest/servers.dq.json":
            {"data": _dq_report("servers.csv", "servers", 250, "Medium",
                                ["3 servers (100%) have no utilisation history — LOW confidence right-sizing."])},
        "engagements/contoso-ltd/dc-exit/_ingest/apps.dq.json":
            {"data": _dq_report("apps.csv", "applications", 40, "High")},
    }
    acont = _Container({k: {"data": v["data"], "metadata": {},
                            "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)}
                        for k, v in answers.items()})
    monkeypatch.setattr(webapp, "_estimate_container", lambda: acont)
    return webapp, c, store


def test_analysis_reads_the_dq_reports(analysed):
    _w, c, _s = analysed
    j = c.get("/api/engagements/contoso-ltd/dc-exit/analysis").json()
    assert j["summary"]["files_ingested"] == 2
    assert j["summary"]["rows_loaded"] == 290
    assert j["summary"]["tables"] == {"servers": 250, "applications": 40}
    assert j["summary"]["confidence"] == "Medium"          # lowest across files
    assert any("utilisation history" in f for f in j["summary"]["findings"])
    assert {r["file"] for r in j["reports"]} == {"servers.csv", "apps.csv"}


def test_analyze_returns_summary_and_skips_agent_when_unconfigured(analysed):
    _w, c, _s = analysed
    c.post("/api/engagements/contoso-ltd/dc-exit/upload",
           files={"file": ("servers.csv", b"hostname,vcpu\na,2\n", "text/csv")})
    j = c.post("/api/engagements/contoso-ltd/dc-exit/analyze").json()
    assert j["triggered"] is False                          # AGENT_ID not set in the test env
    assert j["summary"]["files_ingested"] == 2
    assert j["summary"]["pending"] == []                    # servers.csv has a report


def test_analyze_400_without_inventory(analysed):
    _w, c, _s = analysed
    r = c.post("/api/engagements/contoso-ltd/dc-exit/analyze")
    assert r.status_code == 400


def test_pending_lists_uploaded_files_with_no_report_yet(analysed):
    _w, c, _s = analysed
    c.post("/api/engagements/contoso-ltd/dc-exit/upload",
           files={"file": ("extra.csv", b"a,b\n1,2\n", "text/csv")})
    j = c.get("/api/engagements/contoso-ltd/dc-exit/analysis").json()
    assert j["summary"]["pending"] == ["extra.csv"]


def test_chat_page_has_start_analysis(client):
    _w, c, _s = client
    html = c.get("/").text
    assert "startanalysis" in html and "Start analysis" in html and "/analyze" in html


# --- C21 / E11.8: published-version history -------------------------------

def test_history_lists_snapshots(client, monkeypatch):
    webapp, c, _s = client
    hp = "engagements/contoso-ltd/dc-exit/history"
    store = {
        f"{hp}/20260908T120000Z/latest.json": {
            "data": json.dumps({"meta": {"published_at": "2026-09-08T12:00:00+00:00",
                                         "package_id": "PKG-1"}}).encode(),
            "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)},
        f"{hp}/20260908T120000Z/latest.xlsx": {
            "data": b"xlsxbytes", "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)},
        f"{hp}/20260909T090000Z/latest.json": {
            "data": json.dumps({"meta": {"published_at": "2026-09-09T09:00:00+00:00",
                                         "package_id": "PKG-2"}}).encode(),
            "metadata": {}, "mtime": _dt.datetime(2026, 9, 9, tzinfo=_dt.timezone.utc)},
    }
    monkeypatch.setattr(webapp, "_estimate_container", lambda: _Container(store))
    j = c.get("/api/engagements/contoso-ltd/dc-exit/history").json()
    assert j["count"] == 2
    assert [v["stamp"] for v in j["versions"]] == ["20260909T090000Z", "20260908T120000Z"]  # newest first
    assert j["versions"][0]["package_id"] == "PKG-2"


def test_dashboard_data_reads_a_snapshot(client, monkeypatch):
    webapp, c, _s = client
    store = {
        "engagements/contoso-ltd/dc-exit/history/20260908T120000Z/latest.json": {
            "data": json.dumps({"meta": {"package_id": "OLD"}, "figures": []}).encode(),
            "metadata": {}, "mtime": _dt.datetime(2026, 9, 8, tzinfo=_dt.timezone.utc)},
    }
    monkeypatch.setattr(webapp, "_estimate_container", lambda: _Container(store))
    r = c.get("/dashboard/data?e=contoso-ltd/dc-exit&snapshot=20260908T120000Z")
    assert r.status_code == 200 and r.json()["meta"]["package_id"] == "OLD"


def test_dashboard_has_version_picker(client):
    _w, c, _s = client
    html = c.get("/dashboard").text
    assert "verSel" in html and "loadVersions" in html and "snapshot" in html


# --- C21 / E11.14: ask & export to Excel ---------------------------------

def test_answer_to_xlsx_returns_a_workbook(client):
    _w, c, _s = client
    r = c.post("/api/answer_to_xlsx", json={
        "engagement": "contoso-ltd/dc-exit",
        "question": "how many prod windows servers?",
        "answer": "42 servers.",
        "tables": [{"name": "prod win", "columns": ["os", "n"], "rows": [["WS2019", 42]]}],
        "sql": "SELECT 1",
    })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.content[:2] == b"PK"                       # a real xlsx (zip) container
    assert "contoso-ltd-dc-exit-answer.xlsx" in r.headers.get("content-disposition", "")


def test_answer_to_xlsx_requires_an_answer(client):
    _w, c, _s = client
    r = c.post("/api/answer_to_xlsx", json={"question": "q?"})
    assert r.status_code == 400


def test_chat_page_has_excel_download(client):
    _w, c, _s = client
    html = c.get("/").text
    assert "xlsxFromAnswer" in html and "/api/answer_to_xlsx" in html and "Download as Excel" in html
