"""Landfall FastAPI composition root. Start with ``uvicorn app:app``.

Routes own HTTP handlers; web_runtime, web_storage, web_access, and chat_state
own shared dependencies. Azure clients stay lazy and page assets stay in src/web.
"""
import logging

from fastapi import FastAPI, Request
import telemetry as _obs

logging.basicConfig(level=logging.INFO)
_obs.configure_telemetry()

from routes import (  # noqa: E402 - configure telemetry before importing handlers
    analysis, chat, dashboard, engagements, pages, questionnaire, transfers, uploads,
)

app = FastAPI(title="Landfall")

# E12.7 — response hardening. The chat page (`/`) and its assets are fully static
# with no inline script/style, so they get a strict CSP; the dashboard and
# questionnaire still carry inline `<style>`/handlers, so they get a CSP that
# keeps `unsafe-inline` for now (tracked as an E12.7 follow-up). Every response
# gets nosniff + frame + referrer regardless.
_CSP_STRICT = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)
_CSP_RELAXED = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
_STRICT_CSP_PATHS = ("/", "/healthz")


async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    path = request.url.path
    strict = path in _STRICT_CSP_PATHS or path.startswith("/static/")
    resp.headers.setdefault("Content-Security-Policy", _CSP_STRICT if strict else _CSP_RELAXED)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp

app.middleware("http")(_security_headers)

for router in (
    pages.router, chat.router, engagements.router, uploads.router,
    analysis.router, transfers.router, questionnaire.router, dashboard.router,
):
    app.include_router(router)
