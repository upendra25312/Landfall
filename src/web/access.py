"""
Engagement visibility + Easy Auth principal decoding for the web app (PRD E11.10).

Kept as a tiny self-contained module (the web container does not ship `src/api`).
The rules match `src/api/engagement.py::can_view` / `principal_from_easyauth`.
"""
from __future__ import annotations

import base64
import json

VISIBILITY_ALL = "all"
VISIBILITY_OWNER = "owner"
_GROUP_PREFIX = "group:"

_GROUP_CLAIMS = ("groups",
                 "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups")
_NAME_CLAIMS = ("preferred_username", "upn",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
                "name",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
                "oid",
                "http://schemas.microsoft.com/identity/claims/objectidentifier")


def normalize_visibility(value) -> str:
    v = str(value or "").strip().lower()
    if v == VISIBILITY_ALL:
        return VISIBILITY_ALL
    if v.startswith(_GROUP_PREFIX) and v[len(_GROUP_PREFIX):].strip():
        return f"{_GROUP_PREFIX}{v[len(_GROUP_PREFIX):].strip()}"
    return VISIBILITY_OWNER


def principal(headers) -> tuple[str | None, list[str]]:
    """(name, group_ids) from request headers. Prefers the base64 `x-ms-client-principal`
    blob (has group claims); falls back to the plain name/id headers."""
    name, groups = None, []
    blob = headers.get("x-ms-client-principal")
    if blob:
        try:
            doc = json.loads(base64.b64decode(blob).decode("utf-8"))
            claims = {}
            for c in doc.get("claims") or []:
                typ, val = c.get("typ"), c.get("val")
                if not typ or val is None:
                    continue
                if typ in _GROUP_CLAIMS:
                    groups.append(val)
                else:
                    claims.setdefault(typ, val)
            name = doc.get("userDetails") or next(
                (claims[c] for c in _NAME_CLAIMS if c in claims), None)
        except Exception:  # noqa: BLE001
            name, groups = None, []
    if not name:
        name = (headers.get("x-ms-client-principal-name")
                or headers.get("x-ms-client-principal-id"))
    return name, groups


def can_view(manifest: dict, viewer: str | None, groups=()) -> bool:
    if not isinstance(manifest, dict):
        return False
    if viewer in (None, "", "unknown", "anonymous"):
        return True
    vis = normalize_visibility(manifest.get("visibility"))
    if vis == VISIBILITY_ALL:
        return True
    if manifest.get("created_by") and manifest.get("created_by") == viewer:
        return True
    if vis.startswith(_GROUP_PREFIX):
        return vis[len(_GROUP_PREFIX):] in set(groups or ())
    return False
