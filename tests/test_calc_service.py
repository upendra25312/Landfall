"""E11.16 — the ca-calc FastAPI service: async /build writes landing_zone.* itself."""
import base64
import importlib.util
import io
import json
import os
import sys

import pytest
from conftest import ROOT

# `src/calc` at the END of the path — `driver` / `calculator_export` / `adapters`
# are unique names; `app` collides with src/web so it is loaded by path below.
_CALC = os.path.join(ROOT, "src", "calc")
if _CALC not in sys.path:
    sys.path.append(_CALC)


def _load_calc_app():
    spec = importlib.util.spec_from_file_location("calc_service_app", os.path.join(_CALC, "app.py"))
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


class _FakeContainer:
    def __init__(self, store):
        self.store = store

    def upload_blob(self, name, data, overwrite=False, content_settings=None):
        self.store[name] = bytes(data) if not isinstance(data, str) else data.encode()


@pytest.fixture()
def client(monkeypatch):
    calc_app = _load_calc_app()
    from fastapi.testclient import TestClient

    store = {}
    monkeypatch.setattr(calc_app, "_container_client", lambda dest: _FakeContainer(store))

    async def _fake_build(spec):
        return {"xlsx_b64": base64.b64encode(_calc_xlsx()).decode(),
                "screenshot_b64": base64.b64encode(b"\x89PNG\r\n").decode(),
                "applied": [{"service": "virtual-machines"}],
                "skipped": [{"what": "Oracle", "why": "no module"}],
                "monthly_header": "$4,210",
                "calculator": "https://azure.microsoft.com/pricing/calculator/"}

    monkeypatch.setattr(calc_app, "build_estimate", _fake_build)
    return calc_app, TestClient(calc_app.app), store


_SPEC = {"engagement": "contoso/dc-exit",
         "estimate_name": "Contoso — DC Exit — Azure Landing Zone (POE)",
         "region_default": "sweden-central", "currency": "USD",
         "licensing_program_calc": "mca", "internal_monthly_estimate": 4000.0,
         "line_items": [{"service": "virtual-machines", "config": {}}]}
_DEST = {"storage_url": "https://st.blob.core.windows.net", "container": "answers",
         "prefix": "engagements/contoso/dc-exit/estimate"}


def test_healthz(client):
    _app, c, _store = client
    assert c.get("/healthz").json()["ok"] is True


def test_async_build_writes_landing_zone_blobs(client):
    _app, c, store = client
    r = c.post("/build", json={"spec": _SPEC, "dest": _DEST})
    assert r.status_code == 202
    assert r.json()["status"] == "building"

    # TestClient runs the BackgroundTask before returning — the artifacts are stored
    p = _DEST["prefix"]
    assert f"{p}/landing_zone.xlsx" in store
    assert f"{p}/landing_zone.png" in store
    lz = json.loads(store[f"{p}/landing_zone.json"])
    assert lz["status"] == "ready"
    assert lz["monthly_total"] == 4210.0
    assert lz["reconciliation"]["delta_pct"] is not None
    assert any("Oracle" in s["what"] for s in lz["skipped"])
    assert lz["spec"]["engagement"] == "contoso/dc-exit"


def test_build_failure_writes_failed_marker(client, monkeypatch):
    calc_app, c, store = client

    async def _boom(spec):
        raise RuntimeError("calculator DOM changed")

    monkeypatch.setattr(calc_app, "build_estimate", _boom)
    r = c.post("/build", json={"spec": _SPEC, "dest": _DEST})
    assert r.status_code == 202
    lz = json.loads(store[f"{_DEST['prefix']}/landing_zone.json"])
    assert lz["status"] == "failed"
    assert "calculator DOM changed" in lz["error"]


def test_sync_wait_returns_summary(client):
    _app, c, _store = client
    r = c.post("/build?wait=1", json={"spec": _SPEC, "dest": _DEST})
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "ready" and out["monthly_total"] == 4210.0
    assert "xlsx_b64" in out


def test_bare_spec_no_dest_runs_sync(client):
    _app, c, _store = client
    r = c.post("/build", json=_SPEC)          # no {spec,dest} envelope, no dest
    assert r.status_code == 200
    assert r.json()["monthly_total"] == 4210.0


def test_bad_body_is_400(client):
    _app, c, _store = client
    assert c.post("/build", json={"spec": {"line_items": []}, "dest": _DEST}).status_code == 400
    assert c.post("/build", json={"spec": _SPEC, "dest": {"container": "x"}}).status_code == 400
