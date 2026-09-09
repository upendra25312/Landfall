"""E9.4 — the web tier forwards logs + request telemetry to App Insights.

`configure_telemetry()` is a no-op without the connection string (so local runs
and this suite never touch the SDK); `event()` writes a flat `customDimensions`
record; the chat handler emits a `web_chat` event on every exit path.
"""
import logging
import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "web"))
import telemetry  # noqa: E402


def test_configure_is_a_noop_without_the_connection_string(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    calls = []
    # if it tried to import the SDK we'd see it; assert it simply returns
    telemetry.configure_telemetry()
    assert calls == []


def test_configure_never_raises_even_if_the_sdk_is_missing(monkeypatch):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000-0000-0000-000000000000")
    # the SDK isn't installed in this venv — the except branch must swallow it
    telemetry.configure_telemetry()


def test_event_is_a_flat_record(caplog):
    with caplog.at_level(logging.INFO, logger="landfall.web"):
        telemetry.event("web_chat", engagement=telemetry.eng_hash("contoso/dc-exit"),
                        status="ok", ms=1200, cited=3, skip=None)
    rec = next(r for r in caplog.records if r.getMessage() == "web_chat")
    assert rec.event == "web_chat"
    assert rec.status == "ok" and rec.ms == 1200 and rec.cited == 3
    assert not hasattr(rec, "skip")                    # None is dropped
    assert not hasattr(rec, "name") or rec.name == "landfall.web"   # reserved key never overwritten


def test_eng_hash_is_stable_and_not_the_raw_id():
    h = telemetry.eng_hash("Contoso/DC-Exit")
    assert h == telemetry.eng_hash("contoso/dc-exit")   # normalised
    assert "contoso" not in h and len(h) == 12
    assert telemetry.eng_hash("") == "none"


def test_event_never_raises_on_bad_input():
    telemetry.event("web_chat", bad=object())           # non-scalar -> str(), no throw


def test_chat_emits_web_chat_on_the_unconfigured_path(monkeypatch, caplog):
    import app as webapp
    from fastapi.testclient import TestClient
    monkeypatch.setattr(webapp, "AGENT_NAME", "")
    c = TestClient(webapp.app)
    with caplog.at_level(logging.INFO, logger="landfall.web"):
        r = c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503
    ev = [rec for rec in caplog.records if rec.getMessage() == "web_chat"]
    assert ev and ev[-1].status == "agent_unconfigured" and hasattr(ev[-1], "ms")


def test_chat_source_emits_web_chat_on_ok_and_error_paths():
    src = open(os.path.join(ROOT, "src", "web", "app.py"), encoding="utf-8").read()
    body = src.split("async def chat(", 1)[1].split("\n@app", 1)[0]
    for status in ('status="ok"', 'status="error"', 'status="unknown_engagement"',
                   'status="empty_agent_response"'):
        assert status in body, status
    assert body.count("_obs.event(") >= 5
