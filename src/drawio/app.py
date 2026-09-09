"""
ca-drawio — a tiny stateless SVG → PNG rasteriser (PRD E11.22 / C27b).

`src/api/lz/diagram.py` already produces the landing-zone diagram as `.drawio`
XML *and* a self-contained `.svg` in-process. The only thing that still needs a
container is turning that SVG into a raster the `.pptx` / `.docx` exporters can
embed (python-pptx / python-docx cannot place an SVG).

So this is not the draw.io MCP engine — it is one endpoint, `POST /render`, that
takes SVG bytes and returns a PNG via CairoSVG. No browser, ~30 MB image, scale
to zero. Guarded by a shared key (`DRAWIO_KEY`) because it has to be externally
reachable (the Function App shares no VNet with the Container Apps environment).
"""
from __future__ import annotations

import hmac
import os

import cairosvg
from fastapi import FastAPI, Header, HTTPException, Request, Response

app = FastAPI(title="ca-drawio")
_KEY = os.environ.get("DRAWIO_KEY", "")
_MAX = 2 * 1024 * 1024


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "ca-drawio", "renderer": "cairosvg"}


@app.post("/render")
async def render(request: Request,
                 x_drawio_key: str = Header(default=""),
                 scale: float = 2.0):
    if _KEY and not hmac.compare_digest(x_drawio_key, _KEY):
        raise HTTPException(status_code=401, detail="bad or missing X-Drawio-Key")
    svg = await request.body()
    if not svg or len(svg) > _MAX:
        raise HTTPException(status_code=413, detail=f"svg must be 1..{_MAX} bytes")
    if b"<svg" not in svg[:512]:
        raise HTTPException(status_code=415, detail="body is not an SVG document")
    try:
        png = cairosvg.svg2png(bytestring=svg, scale=max(1.0, min(4.0, scale)))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"cannot rasterise: {exc}") from exc
    return Response(png, media_type="image/png")
