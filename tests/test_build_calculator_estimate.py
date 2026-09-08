"""E11.16 — build_calculator_estimate Function: spec -> ca-calc -> stored POE."""
import base64
import io
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))


def _calc_xlsx_bytes(name="Contoso — DC Exit — Azure Landing Zone (POE)", monthly=4210.0):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Microsoft Azure Estimate"])
    ws.append([name])
    ws.append(["Service category", "Service type", "Custom name", "Region",
               "Description", "Estimated monthly cost", "Estimated upfront cost"])
    ws.append(["Compute", "Virtual Machines", "", "Sweden Central", "40 x D4s v5", monthly * 0.8, 0])
    ws.append(["Networking", "Azure Firewall", "", "Sweden Central", "1 deployment", monthly * 0.2, 0])
    ws.append([None, None, None, "Total", None, monthly, 0])
    ws.append(["This estimate was created at 9/8/2026 1:00:00 PM UTC"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


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

    calls = {}

    def _fake_urlopen(req, timeout=0):
        calls["spec"] = json.loads(req.data)

        class _R:
            def __enter__(_s):
                return _s

            def __exit__(*a):
                return False

            def read(_s):
                return json.dumps({
                    "xlsx_b64": base64.b64encode(_calc_xlsx_bytes()).decode(),
                    "screenshot_b64": base64.b64encode(b"\x89PNG\r\n").decode(),
                    "applied": [{"service": "virtual-machines"}],
                    "skipped": [{"what": "Oracle storage", "why": "no module"}],
                    "calculator": "https://azure.microsoft.com/pricing/calculator/",
                }).encode()
        return _R()

    monkeypatch.setattr(fn.urllib.request, "urlopen", _fake_urlopen)
    return fn, store, calls, prefix


def _req(body):
    import azure.functions as func
    return func.HttpRequest(method="POST", url="http://x/api/build_calculator_estimate",
                            body=json.dumps(body).encode(),
                            headers={"Content-Type": "application/json"})


def test_builds_spec_calls_calc_and_stores_poe(wired):
    fn, store, calls, prefix = wired
    resp = fn.build_calculator_estimate_route(_req({"engagement": "contoso/dc-exit"}))
    assert resp.status_code == 200
    out = json.loads(resp.get_body())
    assert out["engagement"] == "contoso/dc-exit"
    assert out["monthly_total"] == 4210.0
    assert out["currency"] == "USD"
    assert out["reconciliation"]["delta_pct"] is not None
    assert any("Oracle" in s["what"] for s in out["skipped"])

    # the spec handed to ca-calc is region-correct and price-free
    spec = calls["spec"]
    assert spec["region_default"] == "sweden-central"
    assert spec["estimate_name"].startswith("Contoso — DC Exit")
    assert all("price" not in json.dumps(li).lower() for li in spec["line_items"])

    # blobs stored
    assert f"{prefix}/landing_zone.xlsx" in store
    assert f"{prefix}/landing_zone.png" in store
    lz = json.loads(store[f"{prefix}/landing_zone.json"])
    assert lz["monthly_total"] == 4210.0
    assert lz["source"] == "azure-pricing-calculator"


def test_missing_engagement_is_400(wired):
    fn, *_ = wired
    resp = fn.build_calculator_estimate_route(_req({}))
    assert resp.status_code == 400


def test_no_calc_url_is_503(wired, monkeypatch):
    fn, *_ = wired
    monkeypatch.delenv("CALC_URL", raising=False)
    resp = fn.build_calculator_estimate_route(_req({"engagement": "contoso/dc-exit"}))
    assert resp.status_code == 503
