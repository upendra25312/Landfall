"""C19 / E11.4 + E11.5 — run_engagement bulk-ingest + hard engagement scoping.

Offline: the blob store and the SQL loader are faked; `normalize` + the DQ
report run for real.
"""
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))

_SERVERS_CSV = (
    "server_id,hostname,env,os_name,vcpu,ram_gb,provisioned_disk_gb,used_disk_gb,powerstate\n"
    "srv-1,web1,prod,Ubuntu,2,16,128,90,poweredOn\n"
    "srv-2,web2,prod,Windows,4,32,256,140,poweredOn\n"
)
_APPS_CSV = (
    "app_id,app_name,criticality,internet_facing,compliance_scope\n"
    "app-1,Store,1,1,PCI-DSS\n"
    "app-2,Back office,3,0,\n"
)


class _Blob:
    def __init__(self, store, key):
        self._store, self._key = store, key

    def download_blob(self):
        data = self._store[self._key]

        class _D:
            def readall(_s):
                return data
        return _D()

    def upload_blob(self, data, overwrite=False):
        self._store[self._key] = data.encode() if isinstance(data, str) else bytes(data)


class _Container:
    def __init__(self, store):
        self._store = store

    def list_blobs(self, name_starts_with=""):
        class _B:
            def __init__(_s, name):
                _s.name = name
        return [_B(k) for k in sorted(self._store) if k.startswith(name_starts_with)]

    def get_blob_client(self, name):
        return _Blob(self._store, name)

    def upload_blob(self, name, data, overwrite=False):
        self._store[name] = data.encode() if isinstance(data, str) else bytes(data)


class _Svc:
    def __init__(self, store):
        self._store = store

    def get_container_client(self, container):
        return _Container(self._store)

    def get_blob_client(self, container, name):
        return _Blob(self._store, name)


@pytest.fixture()
def wired(monkeypatch):
    from ingest import functions as ing
    import engagement as eng

    store = {}
    inv = eng.inventory_prefix("acme/dc-exit")
    store[f"{inv}/servers.csv"] = _SERVERS_CSV.encode()
    store[f"{inv}/apps.csv"] = _APPS_CSV.encode()
    store[f"{inv}/_mapping.json"] = b"{}"          # underscore -> must be skipped
    # a second engagement's file must never be touched by an acme run
    store[f"{eng.inventory_prefix('globex/move')}/servers.csv"] = _SERVERS_CSV.encode()

    loaded = []
    monkeypatch.setattr(ing, "_blob", lambda: _Svc(store))
    monkeypatch.setattr(ing.loader, "existing_keys", lambda e: {})
    monkeypatch.setattr(ing.loader, "write_log", lambda rec: None)
    monkeypatch.setattr(ing.loader, "load",
                        lambda table, rows, engagement: loaded.append((table, len(rows), engagement)) or len(rows))
    return ing, store, loaded


def _post(body=None, params=None):
    import azure.functions as func
    return func.HttpRequest(method="POST", url="http://x/api/run_engagement",
                            params=params or {},
                            body=json.dumps(body).encode() if body is not None else b"",
                            headers={"Content-Type": "application/json"})


def test_run_engagement_ingests_every_non_underscore_file(wired):
    ing, store, loaded = wired
    resp = ing.run_engagement(_post({"engagement": "acme/dc-exit"}))
    assert resp.status_code == 200
    out = json.loads(resp.get_body())

    assert out["engagement"] == "acme/dc-exit"
    assert out["file_count"] == 2                     # servers.csv + apps.csv, not _mapping.json
    assert {f["file"] for f in out["files"]} == {"servers.csv", "apps.csv"}
    assert out["rows_loaded"] == 4                    # 2 + 2
    assert out["ran_at"]


def test_run_engagement_stamps_only_its_own_engagement(wired):
    ing, store, loaded = wired
    ing.run_engagement(_post({"engagement": "acme/dc-exit"}))
    assert loaded, "loader.load was never called"
    assert {e for _, _, e in loaded} == {"acme/dc-exit"}    # never globex/move


def test_run_engagement_writes_dq_reports_under_that_engagement(wired):
    ing, store, loaded = wired
    ing.run_engagement(_post({"engagement": "acme/dc-exit"}))
    import engagement as eng
    rp = eng.ingest_report_prefix("acme/dc-exit")
    assert f"{rp}/servers.dq.md" in store
    assert f"{rp}/_runs.jsonl" in store
    audit = json.loads(store[f"{rp}/_runs.jsonl"].splitlines()[0])
    assert audit["op"] == "run_engagement" and audit["file_count"] == 2
    # nothing was written under the other engagement
    assert not any(k.startswith(eng.ingest_report_prefix("globex/move")) for k in store)


def test_run_engagement_requires_engagement(wired):
    ing, store, loaded = wired
    resp = ing.run_engagement(_post({}))
    assert resp.status_code == 400
    assert "engagement" in json.loads(resp.get_body())["error"]


def test_run_engagement_rejects_malformed_engagement(wired):
    ing, store, loaded = wired
    resp = ing.run_engagement(_post({"engagement": "Acme Corp/DC Exit!"}))
    assert resp.status_code == 400


def test_run_engagement_empty_folder_is_ok(wired):
    ing, store, loaded = wired
    resp = ing.run_engagement(_post({"engagement": "empty/eng"}))
    assert resp.status_code == 200
    out = json.loads(resp.get_body())
    assert out["file_count"] == 0 and out["rows_loaded"] == 0
    assert "hint" in out
