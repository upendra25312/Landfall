"""
Engagement provisioning HTTP tools (PRD E11.1). Registered from function_app.py.

  POST /api/engagements
        {"customer": "Contoso Ltd", "project": "DC Exit 2027",
         "region": "swedencentral"?, "notes": ""?, "visibility": "owner"?}
        -> slugs the pair, guarantees uniqueness, writes
           raw/engagements/<c>/<p>/_engagement.json and the folder skeleton,
           returns {"engagement": "<c>/<p>", ...}

  GET  /api/engagements            list (optionally ?created_by= / ?visible_to=)
  GET  /api/engagements/{customer}/{project}   one engagement's manifest
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

import engagement as eng

engagements_bp = func.Blueprint()
_cred = DefaultAzureCredential()
_state: dict = {}

_SKELETON = ("inventory/.keep", "docs/.keep")


def _svc() -> BlobServiceClient:
    if "svc" not in _state:
        _state["svc"] = BlobServiceClient(os.environ["STORAGE_URL"], credential=_cred)
    return _state["svc"]


def _raw():
    return _svc().get_container_client(eng.RAW_CONTAINER)


def _exists(engagement_id: str) -> bool:
    try:
        _raw().get_blob_client(eng.engagement_file(engagement_id)).get_blob_properties()
        return True
    except Exception:                       # noqa: BLE001
        return False


def _unique_id(customer: str, project: str) -> str:
    base = eng.make_engagement_id(customer, project)
    c, p = base.split("/", 1)
    if not _exists(base):
        return base
    for n in range(2, 50):
        cand = f"{c}/{p}-{n}"
        if not _exists(cand):
            return cand
    raise RuntimeError("too many engagements with this name")


def _principal(req: func.HttpRequest) -> str:
    """The Entra user behind EasyAuth, if present."""
    for h in ("x-ms-client-principal-name", "x-ms-client-principal-id"):
        v = req.headers.get(h)
        if v:
            return v
    return "unknown"


@engagements_bp.route(route="engagements", methods=["POST", "GET"],
                      auth_level=func.AuthLevel.ANONYMOUS)
def engagements_route(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "GET":
        return _list(req)

    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    customer = (body.get("customer") or "").strip()
    project = (body.get("project") or "").strip()
    if not customer or not project:
        return _json({"error": 'body needs {"customer": "...", "project": "..."}'}, 400)

    try:
        engagement_id = _unique_id(customer, project)
    except Exception as exc:                # noqa: BLE001
        logging.exception("engagement id allocation failed")
        return _json({"error": f"could not allocate an engagement id: {exc}"}, 500)

    manifest = {
        "engagement": engagement_id,
        "customer": customer,
        "project": project,
        "customer_slug": engagement_id.split("/", 1)[0],
        "project_slug": engagement_id.split("/", 1)[1],
        "region": body.get("region") or os.environ.get("AZURE_LOCATION") or "swedencentral",
        "notes": body.get("notes") or "",
        "visibility": body.get("visibility") if body.get("visibility") in
        (None, "owner", "all") or str(body.get("visibility", "")).startswith("group:")
        else "owner",
        "status": "new",
        "created_by": _principal(req),
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    manifest["visibility"] = manifest["visibility"] or "owner"

    try:
        raw = _raw()
        raw.get_blob_client(eng.engagement_file(engagement_id)).upload_blob(
            json.dumps(manifest, indent=2).encode(), overwrite=True)
        base = eng.raw_prefix(engagement_id)
        for rel in _SKELETON:
            raw.get_blob_client(f"{base}/{rel}").upload_blob(b"", overwrite=True)
    except Exception as exc:                # noqa: BLE001
        logging.exception("engagement provisioning failed")
        return _json({"error": f"provisioning failed: {exc}"}, 500)

    logging.info("engagement created: %s by %s", engagement_id, manifest["created_by"])
    return _json(manifest, 201)


@engagements_bp.route(route="engagements/{customer}/{project}", methods=["GET"],
                      auth_level=func.AuthLevel.ANONYMOUS)
def engagement_one(req: func.HttpRequest) -> func.HttpResponse:
    engagement_id = f"{req.route_params.get('customer')}/{req.route_params.get('project')}"
    try:
        engagement_id = eng.normalize_engagement(engagement_id)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    try:
        blob = _raw().get_blob_client(eng.engagement_file(engagement_id)).download_blob().readall()
        return _json(json.loads(blob))
    except Exception:                       # noqa: BLE001
        return _json({"error": f"no engagement {engagement_id}"}, 404)


def _list(req: func.HttpRequest) -> func.HttpResponse:
    created_by = req.params.get("created_by")
    viewer = req.params.get("visible_to") or _principal(req)
    out = []
    try:
        raw = _raw()
        prefix = f"{eng.ENGAGEMENTS_ROOT}/"
        for b in raw.list_blobs(name_starts_with=prefix):
            if not b.name.endswith(f"/{eng.ENGAGEMENT_FILE}"):
                continue
            try:
                m = json.loads(raw.get_blob_client(b.name).download_blob().readall())
            except Exception:               # noqa: BLE001
                continue
            if created_by and m.get("created_by") != created_by:
                continue
            vis = m.get("visibility", "owner")
            if vis == "all" or m.get("created_by") == viewer or viewer == "unknown":
                out.append({k: m.get(k) for k in
                            ("engagement", "customer", "project", "region", "status",
                             "created_by", "created_at", "visibility")})
    except Exception as exc:                # noqa: BLE001
        logging.exception("engagement list failed")
        return _json({"error": f"list failed: {exc}"}, 500)
    out.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return _json({"engagements": out, "count": len(out)})


def _json(body, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
