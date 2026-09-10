"""C27b / E11.22 — the ca-drawio SVG->PNG rasteriser client + the .pptx / .docx embed.

The container itself (src/drawio/app.py, CairoSVG) isn't imported here — cairosvg is
not a test dependency. We test the Function-side client (`lz.render.rasterize`,
best-effort over a fixed URL) and that the exporters embed a PNG when one is present.
"""
import ast
import io
import os
import struct
import sys
import zlib

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))
sys.path.insert(0, os.path.join(ROOT, "evals"))

from lz.render import rasterize  # noqa: E402


def _png_bytes(w=4, h=4) -> bytes:
    """A minimal valid 1x1-ish PNG (signature + IHDR + IDAT + IEND)."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(typ, data):
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_rasterize_is_a_noop_without_the_url(monkeypatch):
    monkeypatch.delenv("DRAWIO_RENDER_URL", raising=False)
    assert rasterize("<svg/>") is None


def test_rasterize_posts_and_returns_png(monkeypatch):
    monkeypatch.setenv("DRAWIO_RENDER_URL", "https://ca-drawio.example")
    monkeypatch.setenv("DRAWIO_RENDER_KEY", "s3cr3t")
    png = _png_bytes()
    seen = {}

    class _Resp:
        def read(self):
            return png

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["key"] = req.headers.get("X-drawio-key")
        seen["body"] = req.data
        return _Resp()

    monkeypatch.setattr("lz.render.urllib.request.urlopen", _fake_urlopen)
    out = rasterize("<svg xmlns='http://www.w3.org/2000/svg'/>")
    assert out == png
    assert seen["url"].startswith("https://ca-drawio.example/render?scale=")
    assert seen["key"] == "s3cr3t"
    assert seen["body"].startswith(b"<svg")


def test_rasterize_swallows_errors(monkeypatch):
    monkeypatch.setenv("DRAWIO_RENDER_URL", "https://ca-drawio.example")
    monkeypatch.setattr("lz.render.time.sleep", lambda *_: None)
    calls = []

    def _boom(req, timeout=None):
        calls.append(1)
        raise OSError("connection refused")

    monkeypatch.setattr("lz.render.urllib.request.urlopen", _boom)
    assert rasterize("<svg/>") is None
    assert len(calls) == 2   # one retry to absorb a ca-drawio cold start


def test_rasterize_rejects_a_non_png_body(monkeypatch):
    monkeypatch.setenv("DRAWIO_RENDER_URL", "https://ca-drawio.example")

    class _Resp:
        def read(self):
            return b"<html>error</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("lz.render.time.sleep", lambda *_: None)
    monkeypatch.setattr("lz.render.urllib.request.urlopen", lambda *a, **k: _Resp())
    assert rasterize("<svg/>") is None


# --------------------------------------------------------------- export embed

def test_diagram_png_helper_decodes_b64_and_bytes():
    from deliverable.export import _diagram_png
    png = _png_bytes()
    import base64
    assert _diagram_png({"landing_zone_png_b64": base64.b64encode(png).decode()}) == png
    assert _diagram_png({"landing_zone_png": png}) == png
    assert _diagram_png({}) is None
    assert _diagram_png({"landing_zone_png_b64": "not-base64!!!"}) is None
    assert _diagram_png({"landing_zone_png": b"not a png"}) is None


def test_pptx_and_docx_embed_the_png_when_present():
    import pipeline as P
    from deliverable.export import to_docx, to_pptx

    import zipfile

    pkg = P.run()
    png = _png_bytes(600, 300)
    pkg_with = {**pkg, "landing_zone_png_b64": __import__("base64").b64encode(png).decode()}

    def _pngs(blob):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            return [n for n in z.namelist() if n.lower().endswith(".png") and "media" in n.lower()]

    d0, d1 = to_docx(pkg), to_docx(pkg_with)
    p0, p1 = to_pptx(pkg), to_pptx(pkg_with)
    # still valid office files
    for b in (d0, d1, p0, p1):
        assert b[:2] == b"PK" and len(b) > 5000
    # the rendered diagram lands as an embedded PNG only when it was supplied
    assert _pngs(d1) and not _pngs(d0)
    assert _pngs(p1) and not _pngs(p0)


def test_drawio_container_app_is_wellformed():
    src = open(os.path.join(ROOT, "src", "drawio", "app.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    routes = [d.func.attr for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              for d in n.decorator_list
              if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
    assert "get" in routes and "post" in routes           # /healthz + /render
    assert "cairosvg" in src and "DRAWIO_KEY" in src
    reqs = open(os.path.join(ROOT, "src", "drawio", "requirements.txt")).read()
    assert "cairosvg" in reqs and "fastapi" in reqs
