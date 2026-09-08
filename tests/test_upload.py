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

    def list_blobs(self, name_starts_with=""):
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
