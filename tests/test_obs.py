"""E9.4 — answer-quality telemetry helper. Structured, hashed, never load-bearing."""
import logging
import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))
import obs  # noqa: E402


def test_eng_hash_is_stable_opaque_and_case_folded():
    h = obs.eng_hash("Contoso/DC-Exit")
    assert h == obs.eng_hash("contoso/dc-exit ")     # trimmed + lower-cased
    assert len(h) == 12 and "contoso" not in h
    assert obs.eng_hash(None) == "none" and obs.eng_hash("") == "none"


def test_event_emits_structured_custom_dimensions(caplog):
    with caplog.at_level(logging.INFO, logger="landfall.obs"):
        obs.event("query_inventory", engagement="abc123", status="ok", rows=5,
                  shape=None, ms=42)
    rec = next(r for r in caplog.records if r.name == "landfall.obs")
    cd = rec.custom_dimensions
    assert cd["event"] == "query_inventory"
    assert cd["status"] == "ok" and cd["rows"] == 5 and cd["ms"] == 42
    assert "shape" not in cd                          # None dropped
    assert "_name" not in cd


def test_event_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("logging is down")

    monkeypatch.setattr(obs._log, "info", _boom)
    obs.event("x", a=1)                               # must not raise


def test_non_scalar_dims_are_stringified(caplog):
    with caplog.at_level(logging.INFO, logger="landfall.obs"):
        obs.event("estimate_assembled", tables=["a", "b"], count=3)
    cd = next(r for r in caplog.records if r.name == "landfall.obs").custom_dimensions
    assert cd["tables"] == "['a', 'b']" and cd["count"] == 3


# ---------------------------------------------------------------- wired in

def test_query_inventory_emits_an_event_on_a_rejected_query(monkeypatch):
    """The obs.event call in tools.py fires without breaking the tool."""
    import json as _json

    import azure.functions as func
    import tools

    monkeypatch.setattr(tools, "_sql_for", lambda q: (_ for _ in ()).throw(ValueError("no")))
    seen = []
    monkeypatch.setattr("obs.event", lambda name, **d: seen.append((name, d)))

    req = func.HttpRequest(method="POST", url="http://x/api/query_inventory",
                           body=_json.dumps({"engagement": "acme/x", "question": "hi"}).encode(),
                           headers={"Content-Type": "application/json"})
    resp = tools.query_inventory(req)
    assert resp.status_code == 400
    assert seen and seen[0][0] == "query_inventory"
    assert seen[0][1]["status"] == "rejected" and seen[0][1]["engagement"] != "acme/x"


# ---------------------------------------------------------------- infra

def test_workbook_json_is_valid_and_queries_the_right_tables():
    import json

    with open(os.path.join(ROOT, "infra", "workbook-answer-quality.json"), encoding="utf-8") as fh:
        wb = json.load(fh)
    assert wb["version"] == "Notebook/1.0"
    queries = "\n".join(i["content"].get("query", "") for i in wb["items"] if i["type"] == 3)
    assert "operation_Name" in queries and "customDimensions.event == 'query_inventory'" in queries
    assert "estimate_assembled" in queries and "severityLevel >= 3" in queries
    assert all(ord(c) < 128 for c in json.dumps(wb)), "non-ASCII breaks az bicep on Windows"


def test_observability_bicep_is_wired():
    res = open(os.path.join(ROOT, "infra", "resources.bicep"), encoding="utf-8").read()
    assert "Microsoft.Insights/workbooks@" in res
    assert "loadTextContent('./workbook-answer-quality.json')" in res
    assert "var hasAlert = !empty(alertEmail)" in res
    assert "scheduledQueryRules@" in res and "if (hasAlert)" in res
    main = open(os.path.join(ROOT, "infra", "main.bicep"), encoding="utf-8").read()
    assert "param alertEmail string = ''" in main and "alertEmail: alertEmail" in main
    params = open(os.path.join(ROOT, "infra", "main.parameters.json"), encoding="utf-8").read()
    assert '"alertEmail": { "value": "${ALERT_EMAIL=}" }' in params
