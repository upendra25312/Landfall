"""Landfall pages helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response
import json
import os
import web_runtime
import web_storage

router = APIRouter()


@router.get("/healthz")
def health():
    return {"ok": True, "agent_configured": bool(web_runtime.AGENT_NAME),
            "storage_configured": bool(web_runtime.STORAGE_URL),
            "estimate_published": web_storage._read_estimate_blob("latest.json") is not None}


@router.get("/api/calc_regions")
def calc_regions():
    """Azure regions the Pricing Calculator can price — for the engagement region picker."""
    return JSONResponse({"regions": web_storage._calc_regions()})


@router.get("/api/prompt_cards")
def prompt_cards():
    """Intro + capability list + the clickable prompt cards for the chat UI (E11.7).
    Config so pre-sales can edit `src/web/prompt_cards.json` without a code change."""
    try:
        return JSONResponse(json.loads((web_runtime._HERE / "prompt_cards.json").read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        web_runtime.log.warning("prompt_cards.json unreadable: %s", exc)
        return JSONResponse({"intro": {"title": "Landfall — Migration Estimator",
                                       "body": "Ask about the client inventory, sizing, waves or cost.",
                                       "capabilities": []}, "cards": []})


@router.get("/", response_class=HTMLResponse)
def index():
    """The chat UI. Static shell + `/static/chat.{css,js}` — no inline script or
    style, so `/` can carry a strict `Content-Security-Policy` (E12.7). The
    security headers (CSP, nosniff, frame options) are added by `_security_headers`."""
    return (web_runtime._HERE / "chat.html").read_text(encoding="utf-8")


_STATIC = web_runtime._HERE / "static"


_STATIC_MIME = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}


@router.get("/static/{name}")
def static_file(name: str):
    """Serve the chat page's stylesheet + script. Whitelisted extensions, no
    path traversal — `name` is a single path segment and must resolve to a file
    directly inside `src/web/static/`."""
    ext = os.path.splitext(name)[1]
    if ext not in _STATIC_MIME:
        return Response(status_code=404)
    p = (_STATIC / name).resolve()
    if p.parent != _STATIC.resolve() or not p.is_file():
        return Response(status_code=404)
    return Response(p.read_text(encoding="utf-8"), media_type=_STATIC_MIME[ext],
                    headers={"Cache-Control": "public, max-age=300"})
