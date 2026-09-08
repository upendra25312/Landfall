"""Cycle 14 — assessment dashboard web app + publish_estimate (E5.5)."""
import io
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "web"))
sys.path.insert(0, os.path.join(ROOT, "evals"))

import pipeline as P  # noqa: E402


# --- publish_estimate (Function) --------------------------------------

class _FakeContainer:
    def __init__(self):
        self.blobs = {}

    def upload_blob(self, name, data, overwrite=False):
        self.blobs[name] = data if isinstance(data, bytes) else bytes(data)


def _req(body: dict):
    import azure.functions as func
    return func.HttpRequest(method="POST", url="http://x/api/publish_estimate",
                            body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})


def test_publish_estimate_writes_package_and_three_exports(monkeypatch):
    from deliverable import functions as dfn

    fake = _FakeContainer()
    monkeypatch.setattr(dfn, "_container_client", lambda: fake)

    pkg = P.run()
    resp = dfn.publish_estimate_route(_req({"package": pkg}))
    assert resp.status_code == 200
    out = json.loads(resp.get_body())
    assert set(out["published"]) == {"latest.json", "latest.xlsx", "latest.docx", "latest.pptx"}

    base = "engagements/_default_/_default_/estimate"
    assert set(fake.blobs) == {f"{base}/latest.{x}" for x in ("json", "xlsx", "docx", "pptx")}
    back = json.loads(fake.blobs[f"{base}/latest.json"])
    assert back["meta"]["package_id"] == pkg["meta"]["package_id"]
    assert back["meta"]["engagement"] == "_default_/_default_"
    assert len(back["figures"]) == len(pkg["figures"])

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(fake.blobs[f"{base}/latest.xlsx"]))
    assert "Calculation appendix" in wb.sheetnames


def test_publish_estimate_scopes_by_engagement(monkeypatch):
    from deliverable import functions as dfn
    fake = _FakeContainer()
    monkeypatch.setattr(dfn, "_container_client", lambda: fake)
    pkg = P.run()
    resp = dfn.publish_estimate_route(_req({"package": pkg, "engagement": "contoso-ltd/dc-exit"}))
    assert resp.status_code == 200
    out = json.loads(resp.get_body())
    assert out["engagement"] == "contoso-ltd/dc-exit"
    assert all(n.startswith("engagements/contoso-ltd/dc-exit/estimate/") for n in fake.blobs)
    assert json.loads(fake.blobs["engagements/contoso-ltd/dc-exit/estimate/latest.json"])["meta"]["engagement"] == "contoso-ltd/dc-exit"


def test_publish_estimate_rejects_empty_body(monkeypatch):
    from deliverable import functions as dfn
    monkeypatch.setattr(dfn, "_container_client", lambda: _FakeContainer())
    resp = dfn.publish_estimate_route(_req({}))
    assert resp.status_code == 400


# --- dashboard web app ------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example/api/projects/x")
    import importlib
    import app as webapp
    importlib.reload(webapp)
    from fastapi.testclient import TestClient
    return webapp, TestClient(webapp.app)


def test_dashboard_page_serves_the_html(client):
    _webapp, c = client
    r = c.get("/dashboard")
    assert r.status_code == 200
    assert "Migration Assessment" in r.text
    assert "/dashboard/data" in r.text
    for fmt in ("xlsx", "docx", "pptx"):
        assert f"/dashboard/download/{fmt}" in r.text


def test_chat_page_has_new_chat_working_indicator_and_cards(client):
    _webapp, c = client
    r = c.get("/")
    assert r.status_code == 200
    assert "New chat" in r.text                       # clear / new session
    assert "The estimator is working" in r.text       # progress indicator
    assert "/api/prompt_cards" in r.text and "cardgrid" in r.text


def test_prompt_cards_endpoint_returns_intro_and_cards(client):
    _webapp, c = client
    j = c.get("/api/prompt_cards").json()
    assert j["intro"]["title"] and j["intro"]["body"]
    assert isinstance(j["intro"]["capabilities"], list) and j["intro"]["capabilities"]
    labels = [card["label"] for card in j["cards"]]
    assert "Full estimate" in labels and "Landing zone" in labels
    assert all(card.get("prompt") for card in j["cards"])


def test_dashboard_data_404_when_nothing_published(client):
    webapp, c = client
    webapp._blob_state.clear()
    from unittest.mock import patch
    with patch.object(webapp, "_read_estimate_blob", return_value=None):
        assert c.get("/dashboard/data").status_code == 404


def test_dashboard_data_returns_the_package(client):
    webapp, c = client
    pkg = P.run()
    from unittest.mock import patch
    with patch.object(webapp, "_read_estimate_blob",
                      return_value=json.dumps(pkg).encode()):
        r = c.get("/dashboard/data")
        assert r.status_code == 200
        assert r.json()["meta"]["package_id"] == pkg["meta"]["package_id"]


def test_dashboard_download_streams_blob_with_right_mime(client):
    webapp, c = client
    from unittest.mock import patch
    with patch.object(webapp, "_read_estimate_blob", return_value=b"PK\x03\x04fake"):
        r = c.get("/dashboard/download/xlsx")
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
    assert c.get("/dashboard/download/pdf").status_code == 400


def test_healthz_reports_publish_state(client):
    webapp, c = client
    from unittest.mock import patch
    with patch.object(webapp, "_read_estimate_blob", return_value=b"{}"):
        j = c.get("/healthz").json()
    assert j["ok"] and j["estimate_published"] is True
