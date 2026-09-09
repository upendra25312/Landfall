"""C19 / E11.5 — engagement-scoped tools reject a call with no `engagement`
(no shared `_default_` fallback). The pure-compute tools are unaffected.
"""
import json
import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))


def _post(route, body):
    import azure.functions as func
    return func.HttpRequest(method="POST", url=f"http://x/api/{route}",
                            body=json.dumps(body).encode(),
                            headers={"Content-Type": "application/json"})


def test_query_inventory_requires_engagement():
    from tools import query_inventory
    resp = query_inventory(_post("query_inventory", {"question": "how many servers?"}))
    assert resp.status_code == 400
    assert "engagement" in json.loads(resp.get_body())["error"]


def test_assemble_estimate_requires_engagement():
    from deliverable.functions import assemble_estimate_route
    resp = assemble_estimate_route(_post("assemble_estimate", {"inventory_summary": {"servers": 1}}))
    assert resp.status_code == 400
    assert "engagement" in json.loads(resp.get_body())["error"]


def test_publish_estimate_requires_engagement():
    from deliverable.functions import publish_estimate_route
    resp = publish_estimate_route(_post("publish_estimate", {"inventory_summary": {"servers": 1}}))
    assert resp.status_code == 400
    assert "engagement" in json.loads(resp.get_body())["error"]


def test_design_landing_zone_does_not_require_engagement():
    """Pure transform — no engagement needed (it never touches per-engagement state)."""
    from lz.functions import design_landing_zone_route
    resp = design_landing_zone_route(_post("design_landing_zone", {
        "applications": [{"app_id": "a1", "criticality": 1, "internet_facing": 0}]}))
    assert resp.status_code == 200


def test_query_inventory_scopes_the_connection_to_the_caller_engagement(monkeypatch):
    """E11.13 — the RLS session context is set to the (normalized) caller engagement
    before any SQL runs, and two engagements never share it."""
    import tools

    seen = {}

    class _Cur:
        description = [("n",)]

        def execute(self, sql, *a):
            seen.setdefault("order", []).append(("execute", sql[:12]))

        def fetchmany(self, n):
            return [[1]]

    class _Conn:
        def cursor(self):
            return _Cur()

        def close(self):
            pass

    monkeypatch.setattr(tools, "_sql_for", lambda q: "SELECT COUNT(*) AS n FROM servers")
    monkeypatch.setattr(tools, "_sql_connect", lambda: _Conn())
    monkeypatch.setattr(tools, "_set_engagement",
                        lambda cur, eng: seen.setdefault("order", []).append(("set_engagement", eng)))

    for raw, norm in (("/contoso/dc-exit/", "contoso/dc-exit"), ("globex/move", "globex/move")):
        seen["order"] = []
        resp = tools.query_inventory(_post("query_inventory", {"engagement": raw, "question": "count"}))
        assert resp.status_code == 200
        # set_engagement(<normalized>) happens, and before the query executes
        assert seen["order"][0] == ("set_engagement", norm)
        assert ("execute", "SELECT COUNT") in seen["order"]
