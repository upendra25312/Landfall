"""E11.16 — ca-calc: the queue worker writes landing_zone.* ; /build runs sync."""
import asyncio
import base64
import importlib.util
import io
import json
import os
import sys

import pytest
from conftest import ROOT

# `src/calc` at the END of the path — `driver` / `calculator_export` / `worker` /
# `adapters` are unique names; `app` collides with src/web so it is loaded by path.
_CALC = os.path.join(ROOT, "src", "calc")
if _CALC not in sys.path:
    sys.path.append(_CALC)


def _load(name):
    spec = importlib.util.spec_from_file_location(f"calc_{name}", os.path.join(_CALC, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _calc_xlsx(name="Contoso — DC Exit — Azure Landing Zone (POE)", monthly=4210.0):
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


async def _fake_run(spec):
    return {"xlsx_b64": base64.b64encode(_calc_xlsx()).decode(),
            "screenshot_b64": base64.b64encode(b"\x89PNG\r\n").decode(),
            "applied": [{"service": "virtual-machines"}],
            "skipped": [{"what": "Oracle", "why": "no module"}],
            "monthly_header": "$4,210",
            "calculator": "https://azure.microsoft.com/pricing/calculator/"}


_SPEC = {"engagement": "contoso/dc-exit",
         "estimate_name": "Contoso — DC Exit — Azure Landing Zone (POE)",
         "region_default": "sweden-central", "currency": "USD",
         "licensing_program_calc": "mca", "internal_monthly_estimate": 4000.0,
         "line_items": [{"service": "virtual-machines", "config": {}}]}
_PREFIX = "engagements/contoso/dc-exit/estimate"


# ---- fake blob + queue -------------------------------------------------------

class _Blob:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def download_blob(self):
        data = self.store[self.key]

        class _D:
            def readall(_s):
                return data
        return _D()


class _Container:
    def __init__(self, store):
        self.store = store

    def get_blob_client(self, name):
        return _Blob(self.store, name)

    def upload_blob(self, name, data, overwrite=False, content_settings=None):
        self.store[name] = bytes(data) if not isinstance(data, str) else data.encode()


class _BlobSvc:
    def __init__(self, store):
        self.store = store

    def get_container_client(self, c):
        return _Container(self.store)


# ---- worker ---------------------------------------------------------------

def test_worker_processes_job_and_writes_ready(monkeypatch):
    worker = _load("worker")
    store = {f"{_PREFIX}/_calc_spec.json": json.dumps(_SPEC).encode()}
    monkeypatch.setattr(worker, "build_estimate", _fake_run)

    asyncio.run(worker._process(_BlobSvc(store), {"container": "answers", "prefix": _PREFIX,
                                                  "spec_blob": f"{_PREFIX}/_calc_spec.json"}))
    lz = json.loads(store[f"{_PREFIX}/landing_zone.json"])
    assert lz["status"] == "ready"
    assert lz["monthly_total"] == 4210.0
    assert lz["reconciliation"]["delta_pct"] is not None
    assert any("Oracle" in s["what"] for s in lz["skipped"])
    assert f"{_PREFIX}/landing_zone.xlsx" in store
    assert f"{_PREFIX}/landing_zone.png" in store


def test_worker_writes_failed_marker_on_error(monkeypatch):
    worker = _load("worker")
    store = {f"{_PREFIX}/_calc_spec.json": json.dumps(_SPEC).encode()}

    async def _boom(spec):
        raise RuntimeError("calculator DOM changed")

    monkeypatch.setattr(worker, "build_estimate", _boom)

    asyncio.run(worker._process(_BlobSvc(store), {"container": "answers", "prefix": _PREFIX,
                                                  "spec_blob": f"{_PREFIX}/_calc_spec.json"}))
    lz = json.loads(store[f"{_PREFIX}/landing_zone.json"])
    assert lz["status"] == "failed"
    assert "calculator DOM changed" in lz["error"]


# ---- HTTP service (sync path) ------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    calc_app = _load("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(calc_app, "build_estimate", _fake_run)
    monkeypatch.delenv("STORAGE_QUEUE_URL", raising=False)   # don't start the consumer
    return calc_app, TestClient(calc_app.app)


def test_healthz(client):
    _app, c = client
    assert c.get("/healthz").json()["ok"] is True


def test_sync_build_returns_summary(client):
    _app, c = client
    r = c.post("/build", json=_SPEC)
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "ready" and out["monthly_total"] == 4210.0
    assert "xlsx_b64" in out


def test_bad_body_is_400(client):
    _app, c = client
    assert c.post("/build", json={"line_items": []}).status_code == 400
