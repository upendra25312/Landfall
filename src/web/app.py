"""Landfall FastAPI composition root. Start with ``uvicorn app:app``.

Routes own HTTP handlers; web_runtime, web_storage, web_access, and chat_state
own shared dependencies. Azure clients stay lazy and page assets stay in src/web.
"""
import logging
import os
import access
import re
import web_runtime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import telemetry as _obs

logging.basicConfig(level=logging.INFO)
_obs.configure_telemetry()

from routes import (  # noqa: E402 - configure telemetry before importing handlers
    analysis, chat, dashboard, engagements, pages, questionnaire, transfers, uploads,
)

app = FastAPI(title="Landfall")

# E12.7 — one strict policy for chat, dashboard and questionnaire. All pages
# load local assets. Every response also gets nosniff, frame and referrer headers.
_CSP_STRICT = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)


async def _security_headers(request: Request, call_next):
    public = request.url.path in ('/', '/healthz', '/signin', '/data-handling') or request.url.path.startswith('/static/')
    if not public and os.environ.get('LANDFALL_LOCAL_AUTH') != '1' and not access.principal(request.headers)[0]:
        resp = JSONResponse({'error': 'Sign in to access Landfall'}, status_code=401)
    else:
        resp = await call_next(request)
    policy = _CSP_STRICT
    storage = web_runtime.STORAGE_URL.rstrip('/')
    if os.environ.get('DIRECT_UPLOADS_ENABLED') == '1' and re.fullmatch(r'https://[a-z0-9]+\.blob\.core\.windows\.net', storage):
        policy = policy.replace("connect-src 'self'", "connect-src 'self' " + storage)
    resp.headers.setdefault("Content-Security-Policy", policy)
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
