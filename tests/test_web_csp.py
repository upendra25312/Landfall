"""E12.7 — the chat page is a static shell + served assets, and `/` carries a
strict Content-Security-Policy with no `unsafe-inline`."""
import os
import re
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "web"))


def _client():
    import app as webapp
    from fastapi.testclient import TestClient
    return webapp, TestClient(webapp.app)


def test_index_serves_the_static_file_not_an_inline_string():
    webapp, c = _client()
    r = c.get("/")
    assert r.status_code == 200
    body = r.text.split("<body", 1)[1]
    assert "<style" not in r.text                      # no inline stylesheet
    assert "<script src=\"/static/chat.js\">" in r.text
    assert re.search(r"<script>(?!\s*</script>)", r.text) is None   # no inline script
    assert " style=" not in body                       # no inline style attributes
    assert 'href="/static/chat.css"' in r.text
    # it really is the file on disk
    disk = open(os.path.join(ROOT, "src", "web", "chat.html"), encoding="utf-8").read()
    assert r.text == disk


def test_strict_csp_on_the_chat_page_and_its_assets():
    webapp, c = _client()
    for path in ("/", "/static/chat.css", "/static/chat.js"):
        csp = c.get(path).headers.get("content-security-policy", "")
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp
        assert "unsafe-inline" not in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'none'" in csp


def test_security_headers_on_every_response():
    webapp, c = _client()
    for path in ("/", "/dashboard", "/healthz", "/static/chat.css"):
        h = c.get(path).headers
        assert h.get("x-content-type-options") == "nosniff", path
        assert h.get("x-frame-options") == "DENY", path
        assert h.get("referrer-policy") == "strict-origin-when-cross-origin", path
        assert "content-security-policy" in h, path


def test_dashboard_keeps_a_csp_even_though_it_still_has_inline_style():
    # the dashboard/questionnaire refactor is a follow-up; until then they get the
    # relaxed CSP so at least framing / base-uri / object-src are locked down.
    webapp, c = _client()
    csp = c.get("/dashboard").headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_static_route_rejects_traversal_and_unknown_extensions():
    webapp, c = _client()
    assert c.get("/static/x.py").status_code == 404
    assert c.get("/static/prompt_cards.json").status_code == 404   # real file, wrong ext
    assert c.get("/static/nope.css").status_code == 404
    ok = c.get("/static/chat.css")
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/css")


def test_assets_have_no_inline_style_attributes_either():
    js = open(os.path.join(ROOT, "src", "web", "static", "chat.js"), encoding="utf-8").read()
    # `el.style.x = ...` (a DOM property) is fine under CSP; a `style="..."` string
    # baked into innerHTML is not.
    assert 'style="' not in js
