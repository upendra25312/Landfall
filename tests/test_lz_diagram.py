"""C27 / E11.22 — deterministic target landing-zone diagram (draw.io XML) from
design_landing_zone output, plus the build_landing_zone_diagram Function route.
"""
import json
import os
import sys
import xml.dom.minidom as _md

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))

from lz.design import design_landing_zone  # noqa: E402
from lz.diagram import build_drawio, build_svg, mcp_plan, diagram_meta  # noqa: E402

_APPS = [
    {"app_id": "a1", "app_name": "Storefront", "criticality": "1", "internet_facing": "1",
     "compliance_scope": "PCI-DSS"},
    {"app_id": "a2", "app_name": "ERP", "criticality": "2"},
]
_SS = {"total_servers": 40, "by_env": {"prod": 20, "nonprod": 20}, "total_vcpu": 300}


def _design(apps=_APPS, ss=_SS, **lz):
    from cost.config import load_config
    cfg = load_config()
    if lz:
        cfg = {**cfg, "landing_zone": {**cfg["landing_zone"], **lz}}
    return design_landing_zone(apps, ss, cfg)


def test_build_drawio_is_valid_xml_with_the_expected_structure():
    d = _design()
    xml = build_drawio(d)
    dom = _md.parseString(xml)                       # parses -> well-formed
    assert xml.startswith("<mxfile")
    assert '<mxCell id="0"/>' in xml and '<mxCell id="1" parent="0"/>' in xml
    assert "swimlane" in xml                          # VNet containers
    assert xml.count('edge="1"') >= 2                 # at least hub->spoke + hybrid
    assert d["region"] in xml and d["dr_region"] in xml
    # every non-base cell has a parent
    for cell in dom.getElementsByTagName("mxCell"):
        cid = cell.getAttribute("id")
        if cid not in ("0", "1"):
            assert cell.getAttribute("parent")


def test_deterministic():
    d = _design()
    assert build_drawio(d) == build_drawio(d)
    assert build_svg(d) == build_svg(d)


def test_build_svg_is_valid_self_contained_svg():
    d = _design()
    svg = build_svg(d)
    dom = _md.parseString(svg)
    assert dom.documentElement.tagName == "svg"
    assert svg.startswith("<svg") and 'viewBox="0 0 ' in svg
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "")  # no external refs
    assert d["region"] in svg and d["dr_region"] in svg
    assert "#B4009E" in svg                          # regulated spoke colour carries through


def test_build_svg_thin_and_no_dr():
    _md.parseString(build_svg({}))
    svg = build_svg(_design(dr_region=None))
    _md.parseString(svg)
    assert "DR region" not in svg


def test_no_dr_region_still_renders():
    d = _design(dr_region=None)
    xml = build_drawio(d)
    _md.parseString(xml)
    assert "DR region" not in xml
    assert d["region"] in xml


def test_thin_design_does_not_crash():
    xml = build_drawio({})
    _md.parseString(xml)
    assert "Hub VNet" in xml


def test_regulated_spoke_uses_the_regulated_colour():
    d = _design()                                    # a1 has PCI-DSS
    xml = build_drawio(d)
    assert "#B4009E" in xml                           # regulated palette colour


def test_xml_escaping():
    d = _design()
    d["hub"]["components"] = ['Firewall <policy> & "rules"']
    xml = build_drawio(d)
    _md.parseString(xml)                              # would raise if < & " leaked raw
    assert "&lt;policy&gt;" in xml


def test_mcp_plan_and_meta():
    d = _design()
    plan = mcp_plan(d)
    assert plan[0]["tool"] == "create-group"
    assert plan[-1]["tool"] == "export-xml"
    assert any(s["tool"] == "add-edge" for s in plan)

    m = diagram_meta(d)
    assert m["region"] == d["region"] and m["dr_region"] == d["dr_region"]
    assert m["spoke_count"] == len(d["spokes"])
    assert m["regulated"] is True
    assert isinstance(m["hub_components"], list) and m["hub_components"]


# --------------------------------------------------------------- Function route

class _Blob:
    def __init__(self, store, key):
        self._s, self._k = store, key

    def download_blob(self):
        if self._k not in self._s:
            raise KeyError(self._k)
        data = self._s[self._k]

        class _D:
            def readall(_s2):
                return data
        return _D()

    def upload_blob(self, data, overwrite=False):
        self._s[self._k] = data if isinstance(data, bytes) else str(data).encode()


class _Cont:
    def __init__(self, store):
        self._s = store

    def get_blob_client(self, name):
        return _Blob(self._s, name)

    def upload_blob(self, name, data, overwrite=False):
        self._s[name] = data if isinstance(data, bytes) else str(data).encode()


class _Svc:
    def __init__(self, store):
        self._s = store

    def get_container_client(self, _c):
        return _Cont(self._s)

    def get_blob_client(self, _c, name):
        return _Blob(self._s, name)


def _req(body, method="POST", params=None):
    import azure.functions as func
    return func.HttpRequest(method=method, url="http://x/api/build_landing_zone_diagram",
                            params=params or {},
                            body=json.dumps(body).encode() if body is not None else b"",
                            headers={"Content-Type": "application/json"})


@pytest.fixture()
def fn(monkeypatch):
    from lz import functions as f
    store = {}
    monkeypatch.setattr(f, "_blob", lambda: _Svc(store))
    return f, store


def test_route_renders_inline_from_a_design(fn):
    f, _store = fn
    d = _design()
    resp = f.build_landing_zone_diagram_route(_req({"design": d}))
    assert resp.status_code == 200
    out = json.loads(resp.get_body())
    assert out["stored"] == [] and out["drawio"].startswith("<mxfile")
    assert out["meta"]["spoke_count"] == len(d["spokes"])


def test_route_stores_for_an_engagement(fn):
    f, store = fn
    import engagement as eng
    d = _design()
    prefix = eng.estimate_prefix("contoso/dc-exit")
    store[f"{prefix}/tools_raw.json"] = json.dumps({"landing_zone": d}).encode()

    resp = f.build_landing_zone_diagram_route(_req({"engagement": "contoso/dc-exit"}))
    assert resp.status_code == 200
    out = json.loads(resp.get_body())
    assert "landing_zone.drawio" in out["stored"] and "landing_zone.svg" in out["stored"]
    assert store[f"{prefix}/landing_zone.drawio"].startswith(b"<mxfile")
    assert store[f"{prefix}/landing_zone.svg"].startswith(b"<svg")
    meta = json.loads(store[f"{prefix}/landing_zone_diagram.json"])
    assert meta["engagement"] == "contoso/dc-exit" and meta["built_at"]

    # GET returns the meta
    g = f.build_landing_zone_diagram_route(_req(None, method="GET", params={"engagement": "contoso/dc-exit"}))
    assert g.status_code == 200 and json.loads(g.get_body())["region"] == d["region"]


def test_route_409_without_a_design(fn):
    f, _store = fn
    resp = f.build_landing_zone_diagram_route(_req({"engagement": "no/estimate"}))
    assert resp.status_code == 409


def test_route_designs_from_applications_when_asked(fn):
    f, _store = fn
    resp = f.build_landing_zone_diagram_route(_req({"applications": _APPS, "server_summary": _SS}))
    assert resp.status_code == 200
    assert json.loads(resp.get_body())["drawio"].startswith("<mxfile")


def test_publish_estimate_regenerates_the_diagram(monkeypatch):
    from deliverable import functions as d
    store = {}

    class _PubCont(_Cont):
        pass

    monkeypatch.setattr(d, "_container_client", lambda: _PubCont(store))
    monkeypatch.setattr(d, "export", lambda pkg, fmt: (b"x", f"n.{fmt}", "m"))
    monkeypatch.setattr(d, "_snapshot_previous", lambda *a, **k: None)
    monkeypatch.setattr(d, "_discovery_for", lambda e: None)

    import azure.functions as func
    lz = _design()
    body = {"engagement": "acme/x", "inventory_summary": {"servers": 5, "applications": 2},
            "landing_zone": lz}
    req = func.HttpRequest(method="POST", url="http://x/api/publish_estimate",
                           body=json.dumps(body).encode(),
                           headers={"Content-Type": "application/json"})
    resp = d.publish_estimate_route(req)
    assert resp.status_code == 200
    import engagement as eng
    p = eng.estimate_prefix("acme/x")
    assert store[f"{p}/landing_zone.drawio"].startswith(b"<mxfile")
    assert store[f"{p}/landing_zone.svg"].startswith(b"<svg")


# --------------------------------------------------------------- web serving

def test_web_serves_the_drawio_and_dashboard_embeds_it(monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "src", "web"))
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://x/api/projects/p")
    monkeypatch.setenv("STORAGE_URL", "https://s.blob.core.windows.net")
    import importlib
    import app as webapp
    import web_runtime
    import web_storage
    importlib.reload(webapp)
    from fastapi.testclient import TestClient

    d = _design()
    blobs = {"landing_zone.drawio": build_drawio(d).encode(),
             "landing_zone.svg": build_svg(d).encode()}

    class _C:
        def download_blob(self, key):
            for name, data in blobs.items():
                if key.endswith(name):
                    class _D:
                        def readall(_s):
                            return data
                    return _D()
            raise KeyError(key)

    monkeypatch.setattr(web_storage, "_estimate_container", lambda: _C())
    c = TestClient(webapp.app)

    r = c.get("/dashboard/landing-zone-diagram")                       # default = svg
    assert r.status_code == 200 and r.text.startswith("<svg")
    assert r.headers["content-type"].startswith("image/svg+xml")
    r2 = c.get("/dashboard/landing-zone-diagram?fmt=drawio&download=1")
    assert r2.text.startswith("<mxfile") and r2.headers["content-disposition"].endswith('.drawio"')

    html = (web_runtime._HERE / "dashboard.html").read_text(encoding="utf-8")
    assert "landing-zone-diagram" in html and "renderLZDiagram" in html
