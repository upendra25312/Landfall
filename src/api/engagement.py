"""
Engagement identity + per-engagement ADLS layout (PRD E11.1 / E11.2).

An *engagement* is one client + one project. Its id is ``<customer>/<project>``,
each segment slugged to ``^[a-z0-9][a-z0-9-]{0,39}$``. That id keys everything:

    raw/engagements/<customer>/<project>/inventory/…   client uploads
    raw/engagements/<customer>/<project>/docs/…        narrative docs
    raw/engagements/<customer>/<project>/_engagement.json
    answers/engagements/<customer>/<project>/_ingest/…  data-quality reports
    answers/engagements/<customer>/<project>/estimate/… latest.json + exports
    answers/engagements/<customer>/<project>/history/<utc-ts>/…

and, in Azure SQL, an ``engagement_id`` column on every table plus a Row-Level
Security policy (see scripts/schema.sql). Pure helpers here — no Azure imports.
"""
from __future__ import annotations

import re
import unicodedata

RAW_CONTAINER = "raw"
ANSWERS_CONTAINER = "answers"
ENGAGEMENTS_ROOT = "engagements"
INVENTORY_DIR = "inventory"
DOCS_DIR = "docs"
ESTIMATE_DIR = "estimate"
INGEST_DIR = "_ingest"
HISTORY_DIR = "history"
ENGAGEMENT_FILE = "_engagement.json"
MAPPING_FILE = "_mapping.json"

_SEG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_ENGAGEMENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}/[a-z0-9][a-z0-9-]{0,39}$")

# the single-tenant layout in cycles 1-17 folds into this engagement
DEFAULT_ENGAGEMENT = "_default_/_default_"


def slug(value: str) -> str:
    """A display string -> a URL/path/SQL-safe segment. Empty -> 'x'."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if not text:
        return "x"
    return text[:40].rstrip("-") or "x"


def valid_segment(seg: str) -> bool:
    return bool(_SEG.match(seg or ""))


def valid_engagement_id(engagement_id: str) -> bool:
    """True for '<customer>/<project>' with both segments well-formed. Also accepts
    the reserved '_default_/_default_'."""
    if engagement_id == DEFAULT_ENGAGEMENT:
        return True
    return bool(_ENGAGEMENT_ID.match(engagement_id or ""))


def normalize_engagement(engagement_id: str) -> str:
    """Validate + return the canonical id, or raise ValueError. Trims a leading slash
    and collapses accidental doubles."""
    eid = (engagement_id or "").strip().strip("/")
    eid = re.sub(r"/{2,}", "/", eid)
    if not valid_engagement_id(eid):
        raise ValueError(
            "engagement must be '<customer>/<project>', each segment "
            "[a-z0-9-], 1-40 chars, starting alphanumeric"
        )
    return eid


def make_engagement_id(customer: str, project: str) -> str:
    return f"{slug(customer)}/{slug(project)}"


# --------------------------------------------------------------- access control
# PRD E11.10 — `_engagement.json` records `created_by` (the Entra user) and
# `visibility`: one of `owner` (only the creator), `all` (anyone who can sign in),
# or `group:<id>` (the creator + members of that Entra group). The engagements
# list — and every engagement-scoped read — filters by this. Fail-closed: an
# unrecognised value is treated as `owner`.

VISIBILITY_OWNER = "owner"
VISIBILITY_ALL = "all"
_GROUP_PREFIX = "group:"


def normalize_visibility(value) -> str:
    """A client-supplied visibility -> a canonical one. `owner` for anything odd."""
    v = str(value or "").strip().lower()
    if v == VISIBILITY_ALL:
        return VISIBILITY_ALL
    if v.startswith(_GROUP_PREFIX):
        gid = v[len(_GROUP_PREFIX):].strip()
        if gid:
            return f"{_GROUP_PREFIX}{gid}"
    return VISIBILITY_OWNER


def can_view(manifest: dict, viewer: str | None, groups=()) -> bool:
    """Is `viewer` (an Entra user id/name, plus their group ids) allowed to see the
    engagement described by `manifest`?

    - `all`                -> yes for any signed-in caller
    - `owner`              -> only `created_by`
    - `group:<id>`         -> `created_by`, or `<id>` in `groups`
    - unknown viewer ("unknown"/"anonymous"/"" — no Easy Auth header) -> yes, so a
      local / unauthenticated deployment is not locked out of its own data.
    """
    if not isinstance(manifest, dict):
        return False
    if viewer in (None, "", "unknown", "anonymous"):
        return True
    vis = normalize_visibility(manifest.get("visibility"))
    if vis == VISIBILITY_ALL:
        return True
    owner = manifest.get("created_by")
    if owner and viewer and owner == viewer:
        return True
    if vis.startswith(_GROUP_PREFIX):
        return vis[len(_GROUP_PREFIX):] in set(groups or ())
    return False


def principal_from_easyauth(header_b64: str | None) -> tuple[str | None, list[str]]:
    """Decode an Azure Easy Auth `x-ms-client-principal` header (base64 JSON) into
    ``(name, group_ids)``. Returns ``(None, [])`` if absent or unparseable.

    The header carries a `claims` list of `{typ, val}`; the name is the UPN /
    preferred_username / name / oid claim, groups are every `groups` claim value
    (Entra emits one claim per group when the token is configured for it)."""
    import base64
    import json as _json

    if not header_b64:
        return None, []
    try:
        raw = base64.b64decode(header_b64).decode("utf-8")
        doc = _json.loads(raw)
    except Exception:                              # noqa: BLE001
        return None, []
    claims = {}
    groups: list[str] = []
    for c in doc.get("claims") or []:
        typ, val = c.get("typ"), c.get("val")
        if not typ or val is None:
            continue
        if typ in ("groups", "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"):
            groups.append(val)
        else:
            claims.setdefault(typ, val)
    name = (doc.get("userDetails")
            or claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn")
            or claims.get("name")
            or claims.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
            or claims.get("oid")
            or claims.get("http://schemas.microsoft.com/identity/claims/objectidentifier"))
    return (name or None), groups


def split(engagement_id: str) -> tuple[str, str]:
    eid = normalize_engagement(engagement_id)
    customer, project = eid.split("/", 1)
    return customer, project


# --------------------------------------------------------------- blob prefixes

def _base(container_root: str, engagement_id: str) -> str:
    return f"{ENGAGEMENTS_ROOT}/{normalize_engagement(engagement_id)}"


def raw_prefix(engagement_id: str) -> str:
    """Path within the `raw` container for this engagement (no container name)."""
    return _base(RAW_CONTAINER, engagement_id)


def inventory_prefix(engagement_id: str) -> str:
    return f"{raw_prefix(engagement_id)}/{INVENTORY_DIR}"


def docs_prefix(engagement_id: str) -> str:
    return f"{raw_prefix(engagement_id)}/{DOCS_DIR}"


def engagement_file(engagement_id: str) -> str:
    return f"{raw_prefix(engagement_id)}/{ENGAGEMENT_FILE}"


def mapping_file(engagement_id: str) -> str:
    return f"{raw_prefix(engagement_id)}/{MAPPING_FILE}"


def answers_prefix(engagement_id: str) -> str:
    """Path within the `answers` container for this engagement."""
    return f"{ENGAGEMENTS_ROOT}/{normalize_engagement(engagement_id)}"


def ingest_report_prefix(engagement_id: str) -> str:
    return f"{answers_prefix(engagement_id)}/{INGEST_DIR}"


def estimate_prefix(engagement_id: str) -> str:
    return f"{answers_prefix(engagement_id)}/{ESTIMATE_DIR}"


def history_prefix(engagement_id: str, stamp: str) -> str:
    return f"{answers_prefix(engagement_id)}/{HISTORY_DIR}/{stamp}"


# ------------------------------------------------------ parse an event/blob name

_INV_PATH = re.compile(
    rf"(?:^|/){ENGAGEMENTS_ROOT}/"
    r"([a-z0-9][a-z0-9-]{0,39})/([a-z0-9][a-z0-9-]{0,39})/"
    rf"(?:{INVENTORY_DIR}|{DOCS_DIR})/([^/]+)$"
)


def parse_inventory_blob(blob_name: str) -> tuple[str, str] | None:
    """('<customer>/<project>', '<file>') for a blob under an engagement's
    inventory/ or docs/ folder, else None. Accepts a bare path or a full
    '/blobServices/…/blobs/raw/engagements/…' Event Grid subject."""
    m = _INV_PATH.search(blob_name or "")
    if not m:
        return None
    customer, project, filename = m.groups()
    return f"{customer}/{project}", filename
