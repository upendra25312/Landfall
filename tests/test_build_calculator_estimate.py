"""E11.16 — build_calculator_estimate: async start + poll.

The Function builds the calculator spec, writes a `building` marker, kicks the
`ca-calc` container fire-and-forget and returns 202. `ca-calc` writes the real
`landing_zone.{xlsx,json,png}` itself (covered by tests/test_calc_service.py).
"""
import json
import os
import sys
import urllib.error

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))


class _FakeBlobClient:
    def __init__(self, store, key):
        self._store, self._key = store, key

    def download_blob(self):
        if self._key not in self._store:
            raise KeyError(self._key)
        data = self._store[self._key]

        class _D:
            def readall(_s):
                return data
        return _D()

    def upload_blob(self, data, overwrite=False):
        self._store[self._key] = bytes(data) if not isinstance(data, str) else data.encode()


class _FakeContainer:
    def __init__(self, store):
        self._store = store

    def upload_blob(self, name, data, overwrite=False):
        self._store[name] = bytes(data) if not isinstance(data, str) else data.encode()


class _FakeSvc:
    def __init__(self, store):
        self._store = store

    def get_blob_client(self, container, name):
        return _FakeBlobClient(self._store, name)

    def get_container_client(self, container):
        return _FakeContainer(self._store)


@pytest.fixture()
def wired(monkeypatch):
    from lz import functions as fn
    import engagement as eng

    eid = "contoso/dc-exit"
    prefix = eng.estimate_prefix(eid)
    store = {
        f"{prefix}/latest.json": json.dumps({"meta": {"region": "swedencentral",
                                                      "currency": "USD", "generated_on": "2026-09-08"}}).encode(),
        f"{prefix}/tools_raw.json": json.dumps({
            "compute_cost": {"region": "swedencentral", "reserved_term": "3yr", "line_items": [
                {"server_id": "s1", "env": "prod", "os": "windows", "sku": "Standard_D4s_v5",
                 "ahb_applied": True, "disk_tier": "P20", "total_monthly": 200.0}]},
            "storage_cost": {"line_items": []},
            "landing_zone": {"region": "swedencentral", "regulated": False, "spokes": [{"name": "corp"}],
                             "connectivity": {"model": "vpn"},
                             "hub": {"components": ["Hub VNet", "Azure Bastion"]}},
        }).encode(),
        eng.engagement_file(eid): json.dumps({"customer": "Contoso", "project": "DC Exit",
                                              "target_region": "swedencentral", "dr_region": None,
                                              "currency": "USD", "licensing_program": "MCA"}).encode(),
    }
    monkeypatch.setattr(fn, "_blob", lambda: _FakeSvc(store))
    monkeypatch.setenv("CALC_URL", "http://ca-calc.internal")
    monkeypatch.setenv("STORAGE_URL", "https://st.blob.core.windows.net")

    calls = {}

    def _fake_urlopen(req, timeout=0):
        calls["payload"] = json.loads(req.data)
        calls["url"] = req.full_url

        class _R:
            def __enter__(_s):
                return _s

            def __exit__(*a):
                return False

            def read(_s):
                return json.dumps({"status": "building", "prefix": prefix}).encode()
        return _R()

    monkeypatch.setattr(fn.urllib.request, "urlopen", _fake_urlopen)
    return fn, store, calls, prefix


def _post(body):
    import azure.functions as func
    return func.HttpRequest(method="POST", url="http://x/api/build_calculator_estimate",
                            body=json.dumps(body).encode(),
                            headers={"Content-Type": "application/json"})


def _get(engagement):
    import azure.functions as func
    return func.HttpRequest(method="GET", url="http://x/api/build_calculator_estimate",
                            params={"engagement": engagement}, body=b"", headers={})


def test_post_starts_run_and_returns_202(wired):
    fn, store, calls, prefix = wired
    resp = fn.build_calculator_estimate_route(_post({"engagement": "contoso/dc-exit"}))
    assert resp.status_code == 202
    out = json.loads(resp.get_body())
    assert out["engagement"] == "contoso/dc-exit"
    assert out["status"] == "building"
    assert out["spec_line_count"] >= 1
    assert "dashboard" in out["dashboard_hint"].lower()

    # a building marker was written for the dashboard / poll to read
    marker = json.loads(store[f"{prefix}/landing_zone.json"])
    assert marker["status"] == "building"
    assert marker["internal_monthly_estimate"] is not None

    # ca-calc got {spec, dest} with the right blob destination and a price-free spec
    payload = calls["payload"]
    assert payload["dest"] == {"storage_url": "https://st.blob.core.windows.net",
                               "container": "answers", "prefix": prefix}
    spec = payload["spec"]
    assert spec["region_default"] == "sweden-central"
    assert spec["estimate_name"].startswith("Contoso")
    assert all("price" not in json.dumps(li).lower() for li in spec["line_items"])
    assert calls["url"].endswith("/build")


def test_get_returns_status(wired):
    fn, store, calls, prefix = wired
    fn.build_calculator_estimate_route(_post({"engagement": "contoso/dc-exit"}))
    resp = fn.build_calculator_estimate_route(_get("contoso/dc-exit"))
    assert resp.status_code == 200
    assert json.loads(resp.get_body())["status"] == "building"

    # ca-calc later writes a ready doc; GET reflects it
    store[f"{prefix}/landing_zone.json"] = json.dumps({
        "engagement": "contoso/dc-exit", "status": "ready", "monthly_total": 4210.0,
        "annual": 50520.0, "line_count": 5, "currency": "USD",
        "reconciliation": {"delta_pct": 2.1, "within_tolerance": True}}).encode()
    resp = fn.build_calculator_estimate_route(_get("contoso/dc-exit"))
    out = json.loads(resp.get_body())
    assert out["status"] == "ready" and out["monthly_total"] == 4210.0


def test_get_404_when_nothing_started(wired):
    fn, *_ = wired
    resp = fn.build_calculator_estimate_route(_get("contoso/dc-exit"))
    assert resp.status_code == 404
    assert json.loads(resp.get_body())["status"] == "none"


def test_missing_engagement_is_400(wired):
    fn, *_ = wired
    resp = fn.build_calculator_estimate_route(_post({}))
    assert resp.status_code == 400


def test_no_calc_url_is_503(wired, monkeypatch):
    fn, *_ = wired
    monkeypatch.delenv("CALC_URL", raising=False)
    resp = fn.build_calculator_estimate_route(_post({"engagement": "contoso/dc-exit"}))
    assert resp.status_code == 503


def test_no_published_estimate_is_409(wired):
    fn, store, calls, prefix = wired
    store.pop(f"{prefix}/latest.json")
    store.pop(f"{prefix}/tools_raw.json")
    resp = fn.build_calculator_estimate_route(_post({"engagement": "contoso/dc-exit"}))
    assert resp.status_code == 409


def test_ca_calc_unreachable_is_502(wired, monkeypatch):
    fn, store, calls, prefix = wired

    def _boom(req, timeout=0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(fn.urllib.request, "urlopen", _boom)
    resp = fn.build_calculator_estimate_route(_post({"engagement": "contoso/dc-exit"}))
    assert resp.status_code == 502
