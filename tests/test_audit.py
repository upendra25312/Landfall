"""C23 / E11.10 — the per-engagement audit trail: every run_engagement /
publish_estimate / engagement create appends an attributable line to
answers/engagements/<c>/<p>/_audit.jsonl.
"""
import json
import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))


class _Blob:
    def __init__(self, store, key):
        self._s, self._k = store, key

    def download_blob(self):
        if self._k not in self._s:
            raise KeyError(self._k)
        data = self._s[self._k]

        class _D:
            def readall(_s):
                return data
        return _D()

    def upload_blob(self, data, overwrite=False):
        self._s[self._k] = data if isinstance(data, bytes) else bytes(data)


class _Container:
    def __init__(self, store):
        self._s = store

    def get_blob_client(self, name):
        return _Blob(self._s, name)

    def upload_blob(self, name, data, overwrite=False):
        self._s[name] = data if isinstance(data, bytes) else bytes(data)


def test_record_and_read_roundtrip():
    import audit
    store = {}
    cc = _Container(store)
    audit.record(cc, "acme/dc-exit", "run_engagement", actor="alice", rows_loaded=10)
    audit.record(cc, "acme/dc-exit", "publish_estimate", actor="bob", package_id="p1")

    key = "engagements/acme/dc-exit/_audit.jsonl"
    assert key in store
    lines = store[key].decode().splitlines()
    assert len(lines) == 2

    entries = audit.read(cc, "acme/dc-exit")
    assert [e["event"] for e in entries] == ["publish_estimate", "run_engagement"]   # newest first
    assert entries[0]["actor"] == "bob" and entries[0]["package_id"] == "p1"
    assert entries[1]["rows_loaded"] == 10
    assert all(e["at"] for e in entries)


def test_read_missing_is_empty():
    import audit
    assert audit.read(_Container({}), "no/thing") == []


def test_record_never_raises_on_broken_container():
    import audit

    class _Boom:
        def get_blob_client(self, name):
            raise RuntimeError("nope")

    audit.record(_Boom(), "x/y", "run_engagement")   # must not raise


def test_publish_estimate_writes_an_audit_line(monkeypatch):
    from deliverable import functions as d
    store = {}
    cc = _Container(store)
    monkeypatch.setattr(d, "_container_client", lambda: cc)
    monkeypatch.setattr(d, "export", lambda pkg, fmt: (b"x", f"n.{fmt}", "m"))
    monkeypatch.setattr(d, "_snapshot_previous", lambda *a, **k: None)

    import azure.functions as func
    pkg = {"meta": {"package_id": "pkg-9"}, "figures": []}
    req = func.HttpRequest(method="POST", url="http://x/api/publish_estimate",
                           body=json.dumps({"engagement": "acme/x", "package": pkg}).encode(),
                           headers={"Content-Type": "application/json",
                                    "x-ms-client-principal-name": "carol@x"})
    resp = d.publish_estimate_route(req)
    assert resp.status_code == 200
    entries = json.loads(store["engagements/acme/x/_audit.jsonl"].decode().splitlines()[0])
    assert entries["event"] == "publish_estimate"
    assert entries["actor"] == "carol@x"
    assert entries["package_id"] == "pkg-9"
