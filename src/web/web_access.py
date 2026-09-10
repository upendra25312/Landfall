"""Landfall web access helpers.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
import access as _acl
import json
import web_storage

_SEG_RE = __import__("re").compile(r"^[a-z0-9_][a-z0-9_-]{0,49}$")


def _slug(v: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (v or "").strip().lower()).strip("-")
    return s[:40] or "x"


def _seg(v: str) -> str | None:
    v = (v or "").strip().lower()
    return v if _SEG_RE.match(v) else None


def _principal_name(request: Request) -> str:
    return _acl.principal(request.headers)[0] or "anonymous"


def _principal(request: Request) -> tuple[str | None, list[str]]:
    return _acl.principal(request.headers)


def _engagement(customer: str, project: str,
                request: Request | None = None) -> tuple[str, str] | None:
    """Validate the path pair -> ('<c>/<p>', 'engagements/<c>/<p>'). None if malformed,
    if the engagement doesn't exist (no `_engagement.json`), or — when `request` is
    given — if its `visibility` doesn't admit the caller (E11.10; a 404, not a 403,
    so an engagement the caller can't see is indistinguishable from one that isn't
    there)."""
    c, p = _seg(customer), _seg(project)
    if not c or not p:
        return None
    eid = f"{c}/{p}"
    try:
        raw = web_storage._raw_container().download_blob(f"engagements/{eid}/_engagement.json").readall()
    except Exception:  # noqa: BLE001
        return None
    if request is not None:
        try:
            manifest = json.loads(raw)
        except Exception:  # noqa: BLE001
            manifest = {}
        name, groups = _principal(request)
        if not _acl.can_view(manifest, name, groups):
            return None
    return eid, f"engagements/{eid}"


def _guard_eid(request: Request, e: str | None):
    """Authorize the requested or implicit default dashboard scope, failing closed."""
    eid = (e or "").strip().strip("/") or "_default_/_default_"
    parts = eid.split("/")
    if len(parts) != 2 or not all(_seg(p) == p for p in parts):
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    try:
        m = json.loads(web_storage._raw_container().download_blob(
            f"engagements/{eid}/_engagement.json").readall())
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "engagement manifest unavailable"}, status_code=404)
    name, groups = _principal(request)
    if _acl.can_view(m, name, groups):
        return None
    return JSONResponse({"error": "not visible to you"}, status_code=403)
