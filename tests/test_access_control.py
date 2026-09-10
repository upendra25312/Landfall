"""C23 / E11.10 — engagement visibility (`owner` | `group:<id>` | `all`) filters
the engagements list and every engagement-scoped read; Easy Auth principal +
group claims are decoded from `x-ms-client-principal`.
"""
import base64
import importlib
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))
sys.path.insert(0, os.path.join(ROOT, "src", "web"))


def _easyauth(name, groups=()):
    claims = [{"typ": "preferred_username", "val": name}]
    claims += [{"typ": "groups", "val": g} for g in groups]
    doc = {"userDetails": name, "claims": claims}
    return base64.b64encode(json.dumps(doc).encode()).decode()


# ---------------------------------------------------------------- pure can_view

@pytest.mark.parametrize("mod_name", ["engagement", "access"])
@pytest.mark.parametrize("vis, viewer, groups, ok", [
    ("all", "alice", (), True),
    ("owner", "alice", (), True),               # alice is the creator
    ("owner", "bob", (), False),
    ("group:sales", "bob", ("sales",), True),
    ("group:sales", "bob", ("eng",), False),
    ("group:sales", "alice", (), True),         # creator always
    ("weird-value", "bob", (), False),          # unknown -> fail closed (owner)
    ("owner", None, (), True),                  # unauthenticated deploy sees its own data
    ("owner", "anonymous", (), True),
])
def test_can_view_matrix(mod_name, vis, viewer, groups, ok):
    mod = importlib.import_module(mod_name)
    m = {"created_by": "alice", "visibility": vis}
    assert mod.can_view(m, viewer, groups) is ok


def test_normalize_visibility():
    import engagement as eng
    assert eng.normalize_visibility("ALL") == "all"
    assert eng.normalize_visibility("Group:Sales ") == "group:sales"
    assert eng.normalize_visibility("group:") == "owner"
    assert eng.normalize_visibility(None) == "owner"
    assert eng.normalize_visibility("nonsense") == "owner"


def test_principal_decode_api_and_web():
    import engagement as eng
    import access as acl
    hdr = _easyauth("dana@contoso.com", ["g1", "g2"])
    assert eng.principal_from_easyauth(hdr) == ("dana@contoso.com", ["g1", "g2"])
    assert acl.principal({"x-ms-client-principal": hdr}) == ("dana@contoso.com", ["g1", "g2"])
    # no header -> nothing
    assert eng.principal_from_easyauth(None) == (None, [])
    assert acl.principal({}) == (None, [])
    # plain name header fallback
    assert acl.principal({"x-ms-client-principal-name": "e@x"})[0] == "e@x"


# ---------------------------------------------------------------- Function _list

class _FBlob:
    def __init__(self, store, key):
        self._s, self._k = store, key

    def download_blob(self):
        data = self._s[self._k]

        class _D:
            def readall(_s):
                return data
        return _D()

    def get_blob_properties(self):
        if self._k not in self._s:
            raise KeyError(self._k)
        return {}

    def upload_blob(self, data, overwrite=False):
        self._s[self._k] = data if isinstance(data, bytes) else str(data).encode()


class _FCont:
    def __init__(self, store):
        self._s = store

    def list_blobs(self, name_starts_with=""):
        class _B:
            def __init__(_s, n):
                _s.name = n
        return [_B(k) for k in sorted(self._s) if k.startswith(name_starts_with)]

    def get_blob_client(self, name):
        return _FBlob(self._s, name)


class _FSvc:
    def __init__(self, store):
        self._s = store

    def get_container_client(self, _c):
        return _FCont(self._s)


@pytest.fixture()
def eng_bp(monkeypatch):
    monkeypatch.setenv("STORAGE_URL", "https://s.blob.core.windows.net")
    import engagements as e
    importlib.reload(e)
    store = {}
    for eid, m in {
        "alice/a": {"created_by": "alice", "visibility": "owner"},
        "bob/b": {"created_by": "bob", "visibility": "owner"},
        "carol/shared": {"created_by": "carol", "visibility": "group:sales"},
        "dave/public": {"created_by": "dave", "visibility": "all"},
    }.items():
        m["engagement"] = eid
        store[f"engagements/{eid}/_engagement.json"] = json.dumps(m).encode()
    monkeypatch.setattr(e, "_svc", lambda: _FSvc(store))
    return e, store


def _get(headers=None, params=None):
    import azure.functions as func
    return func.HttpRequest(method="GET", url="http://x/api/engagements",
                            params=params or {}, body=b"", headers=headers or {})


def test_list_filters_by_viewer_and_groups(eng_bp):
    e, _ = eng_bp
    body = json.loads(e.engagements_route(_get({"x-ms-client-principal": _easyauth("bob")})).get_body())
    got = {x["engagement"] for x in body["engagements"]}
    assert got == {"bob/b", "dave/public"}          # own + public, not alice's, not the sales group

    body = json.loads(e.engagements_route(
        _get({"x-ms-client-principal": _easyauth("bob", ["sales"])})).get_body())
    got = {x["engagement"] for x in body["engagements"]}
    assert got == {"bob/b", "carol/shared", "dave/public"}   # + the sales-group one


def test_list_unauthenticated_sees_all(eng_bp):
    e, _ = eng_bp
    body = json.loads(e.engagements_route(_get()).get_body())
    assert len(body["engagements"]) == 4


def test_engagement_one_403_when_not_visible(eng_bp):
    e, _ = eng_bp
    import azure.functions as func
    req = func.HttpRequest(method="GET", url="http://x/api/engagements/alice/a",
                           route_params={"customer": "alice", "project": "a"},
                           body=b"", headers={"x-ms-client-principal": _easyauth("bob")})
    assert e.engagement_one(req).status_code == 403
    req2 = func.HttpRequest(method="GET", url="http://x/api/engagements/alice/a",
                            route_params={"customer": "alice", "project": "a"},
                            body=b"", headers={"x-ms-client-principal": _easyauth("alice")})
    assert e.engagement_one(req2).status_code == 200


# ---------------------------------------------------------------- web app guard

class _WDown:
    def __init__(self, d):
        self._d = d

    def readall(self):
        return self._d


class _WContainer:
    def __init__(self, store):
        self.store = store

    def download_blob(self, key):
        if key not in self.store:
            raise KeyError(key)
        return _WDown(self.store[key])

    def upload_blob(self, key, data, overwrite=False):
        self.store[key] = data if isinstance(data, (bytes, bytearray)) else str(data).encode()

    def list_blobs(self, name_starts_with="", include=None):
        for k in list(self.store):
            if k.startswith(name_starts_with):
                b = type("B", (), {})()
                b.name, b.size, b.last_modified, b.metadata = k, len(self.store[k]), None, {}
                yield b


@pytest.fixture()
def webapp(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example/api/projects/x")
    monkeypatch.setenv("STORAGE_URL", "https://s.blob.core.windows.net")
    import importlib
    import app as wa
    import web_storage
    importlib.reload(wa)
    from fastapi.testclient import TestClient

    store = {
        "engagements/alice/a/_engagement.json":
            json.dumps({"engagement": "alice/a", "created_by": "alice", "visibility": "owner"}).encode(),
        "engagements/dave/pub/_engagement.json":
            json.dumps({"engagement": "dave/pub", "created_by": "dave", "visibility": "all"}).encode(),
    }
    cont = _WContainer(store)
    monkeypatch.setattr(web_storage, "_raw_container", lambda: cont)
    monkeypatch.setattr(web_storage, "_estimate_container", lambda: cont)
    return wa, TestClient(wa.app), store


def test_web_list_filters_by_principal(webapp):
    _wa, c, _ = webapp
    r = c.get("/api/engagements", headers={"x-ms-client-principal": _easyauth("bob")})
    got = {x["engagement"] for x in r.json()["engagements"]}
    assert got == {"dave/pub"}                        # not alice's owner-only one


def test_web_engagement_route_404_when_not_visible(webapp):
    _wa, c, _ = webapp
    r = c.get("/api/engagements/alice/a/files", headers={"x-ms-client-principal": _easyauth("bob")})
    assert r.status_code == 404
    r2 = c.get("/api/engagements/alice/a/files", headers={"x-ms-client-principal": _easyauth("alice")})
    assert r2.status_code == 200


def test_web_dashboard_data_403_when_not_visible(webapp):
    _wa, c, store = webapp
    store["engagements/alice/a/estimate/latest.json"] = b'{"ok": 1}'
    r = c.get("/dashboard/data?e=alice/a", headers={"x-ms-client-principal": _easyauth("bob")})
    assert r.status_code == 403
    ra = c.get("/dashboard/data?e=alice/a", headers={"x-ms-client-principal": _easyauth("alice")})
    assert ra.status_code == 200


# --- E8.6 — chat is bound to the caller's access on the engagement ----------

def _stub_agent(wa, monkeypatch):
    import web_runtime
    class _Resp:
        id = "resp_leaked_from_alice"
        status = "completed"
        output_text = "ok"
        output = []
    monkeypatch.setattr(web_runtime, "AGENT_NAME", "agent")
    monkeypatch.setattr(web_runtime, "_openai_client",
                        lambda: type("O", (), {"responses": type("R", (), {
                            "create": staticmethod(lambda **kw: (_SEEN.update(kw) or _Resp()))})()})())


_SEEN: dict = {}


def test_chat_404_for_an_engagement_the_caller_cannot_see(webapp, monkeypatch):
    wa, c, _ = webapp
    _stub_agent(wa, monkeypatch)
    r = c.post("/api/chat", json={"message": "hi", "engagement": "alice/a"},
               headers={"x-ms-client-principal": _easyauth("bob")})
    assert r.status_code == 404


def test_chat_ignores_a_client_supplied_thread_id(webapp, monkeypatch):
    wa, c, _ = webapp
    _SEEN.clear()
    _stub_agent(wa, monkeypatch)
    # unscoped chat, caller tries to resume someone else's response id
    r = c.post("/api/chat", json={"message": "continue", "thread_id": "resp_alice_private"},
               headers={"x-ms-client-principal": _easyauth("bob")})
    assert r.status_code == 200
    assert "previous_response_id" not in _SEEN         # the leaked id was not honoured


def test_chat_scoped_to_a_visible_engagement_records_the_actor(webapp, monkeypatch):
    wa, c, store = webapp
    _stub_agent(wa, monkeypatch)
    r = c.post("/api/chat", json={"message": "hi", "engagement": "dave/pub"},
               headers={"x-ms-client-principal": _easyauth("bob")})
    assert r.status_code == 200
    saved = json.loads(store["engagements/dave/pub/_chat.json"])
    assert saved["last_actor"] == "bob"
    assert saved["turns"][0]["actor"] == "bob"


def test_web_audit_route_reads_jsonl(webapp):
    _wa, c, store = webapp
    store["engagements/dave/pub/_audit.jsonl"] = (
        b'{"at":"2026-09-09T00:00:00+00:00","actor":"dave","event":"engagement_created"}\n'
        b'{"at":"2026-09-09T01:00:00+00:00","actor":"dave","event":"publish_estimate"}\n')
    r = c.get("/api/engagements/dave/pub/audit")
    assert r.status_code == 200
    j = r.json()
    assert j["count"] == 2
    assert j["entries"][0]["event"] == "publish_estimate"    # newest first

