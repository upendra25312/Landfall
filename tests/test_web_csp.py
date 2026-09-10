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


def test_security_headers_on_every_response(monkeypatch):
    webapp, c = _client()
    import web_storage
    # This checks response headers, not Azure connectivity. Runtime/storage now
    # live outside app.py, so reloading the entrypoint no longer resets clients.
    monkeypatch.setattr(web_storage, "_read_estimate_blob", lambda *_args: None)
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


def test_static_js_has_no_double_escape_artefacts():
    """C41 extracted an inline `<script>` from a Python triple-quoted string into
    chat.js — and `\\'` / `\\n` (meaning `\\'` / newline inside the Python string)
    were pasted verbatim, so a JS single-quoted string ended early: `'...client\\''`
    -> SyntaxError -> the whole file failed to parse -> the chat page was dead from
    C41 to C48. `\\\\` followed by a quote or an escape letter is the fingerprint and
    is never legitimate in the hand-written assets here."""
    static = os.path.join(ROOT, "src", "web", "static")
    offenders = []
    for name in os.listdir(static):
        if name == 'purify.min.js':
            # Vendored sanitizer uses intentional RegExp string escapes. Its
            # exact release bytes are checked separately below.
            continue
        if not name.endswith((".js", ".css")):
            continue
        src = open(os.path.join(static, name), encoding="utf-8").read()
        for m in re.finditer(r"\\\\[\"'nrt]", src):
            line = src[:m.start()].count("\n") + 1
            offenders.append(f"{name}:{line}: {src[m.start()-25:m.start()+15]!r}")
    assert not offenders, "double-escape artefacts in static assets:\n" + "\n".join(offenders)


def test_vendored_sanitizer_integrity():
    import hashlib
    from pathlib import Path
    data = (Path(ROOT) / 'src/web/static/purify.min.js').read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha256(data).hexdigest() == 'c2f26ea4fc0d88141c9aa430eb515ac86fce59418ceebd85fa475b87a8d6c3e6'


def test_static_js_parses_when_node_is_available():
    """`node --check` on every static .js — a real syntax check when Node is on the
    box (dev machines + GitHub runners have it). Skipped otherwise; the Playwright
    harness (tests/browser/) is the browser-grade guard, E13.16 puts it in CI."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node not installed")
    static = os.path.join(ROOT, "src", "web", "static")
    bad = []
    for name in sorted(n for n in os.listdir(static) if n.endswith(".js")):
        r = subprocess.run([node, "--check", os.path.join(static, name)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            bad.append(f"{name}: {r.stderr.strip().splitlines()[-1] if r.stderr else 'failed'}")
    assert not bad, "static JS does not parse:\n" + "\n".join(bad)
