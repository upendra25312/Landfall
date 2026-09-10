"""Landfall engagements helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import access as _acl
import datetime as _dt
import json
import web_access
import web_runtime
import web_storage

router = APIRouter()


@router.get("/api/engagements")
def engagements_list(request: Request):
    """List engagements from blob (`raw/engagements/<c>/<p>/_engagement.json`), filtered
    by the caller's visibility (E11.6). The chat page uses this for its engagement picker
    so the user never types the `<customer>/<project>` id."""
    me, groups = web_access._principal(request)
    me = me or "anonymous"
    out = []
    try:
        cc = web_storage._raw_container()
        for b in cc.list_blobs(name_starts_with="engagements/"):
            if not b.name.endswith("/_engagement.json"):
                continue
            try:
                m = json.loads(cc.download_blob(b.name).readall())
            except Exception:  # noqa: BLE001
                continue
            if not _acl.can_view(m, None if me == "anonymous" else me, groups):
                continue
            out.append({k: m.get(k) for k in
                        ("engagement", "customer", "project", "target_region", "dr_region",
                         "currency", "licensing_program", "status", "created_by", "created_at",
                         "target_region_calculator_supported", "visibility")})
    except Exception as exc:  # noqa: BLE001
        web_runtime.log.warning("engagements_list failed: %s", exc)
        return JSONResponse({"engagements": [], "error": str(exc)})
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return JSONResponse({"engagements": out})


@router.post("/api/engagements")
async def engagements_create(request: Request):
    """Create an engagement: slug (customer, project), write `_engagement.json` +
    the folder skeleton, return the id. Mirrors the Function's `engagements` blueprint
    so the web app can provision without a Function-to-Function token."""
    import datetime as _dt
    body = await request.json()
    customer = (body.get("customer") or "").strip()
    project = (body.get("project") or "").strip()
    if not customer or not project:
        return JSONResponse({"error": 'need {"customer": "...", "project": "..."}'}, status_code=400)
    c, p = web_access._slug(customer), web_access._slug(project)
    cc = web_storage._raw_container()
    eid = f"{c}/{p}"
    for n in range(2, 50):
        try:
            cc.download_blob(f"engagements/{eid}/_engagement.json")
            eid = f"{c}/{p}-{n}"
        except Exception:  # noqa: BLE001
            break
    tr = (body.get("target_region") or "swedencentral").strip().lower()
    supported = tr in web_storage._calc_regions()
    manifest = {
        "engagement": eid, "customer": customer, "project": project,
        "customer_slug": eid.split("/")[0], "project_slug": eid.split("/")[1],
        "region": tr, "target_region": tr,
        "dr_region": (body.get("dr_region") or "").strip().lower() or None,
        "currency": (body.get("currency") or "USD").upper(),
        "licensing_program": (body.get("licensing_program") or "MCA").upper(),
        "target_region_calculator_supported": supported,
        "notes": body.get("notes") or "",
        "visibility": _acl.normalize_visibility(body.get("visibility")), "status": "new",
        "created_by": web_access._principal_name(request),
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        cc.upload_blob(f"engagements/{eid}/_engagement.json",
                       json.dumps(manifest, indent=2).encode(), overwrite=True)
        for rel in ("inventory/.keep", "docs/.keep"):
            cc.upload_blob(f"engagements/{eid}/{rel}", b"", overwrite=True)
    except Exception as exc:  # noqa: BLE001
        web_runtime.log.exception("engagement create failed")
        return JSONResponse({"error": f"provisioning failed: {exc}"}, status_code=500)
    return JSONResponse(manifest, status_code=201)


@router.get("/api/engagements/{customer}/{project}/history")
def engagement_history(customer: str, project: str, request: Request):
    """Published-estimate version history (E11.8). Each re-publish snapshots the
    version it replaces into answers/engagements/<eid>/history/<ts>/."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    cc = web_storage._estimate_container()
    root = f"engagements/{eid}/history/"
    stamps: dict[str, dict] = {}
    try:
        for b in cc.list_blobs(name_starts_with=root):
            rest = b.name[len(root):]
            if "/" not in rest:
                continue
            stamp, fname = rest.split("/", 1)
            e = stamps.setdefault(stamp, {"stamp": stamp, "files": []})
            e["files"].append(fname)
            if fname == "latest.json":
                try:
                    meta = (json.loads(cc.download_blob(b.name).readall()).get("meta") or {})
                    e["published_at"] = meta.get("published_at")
                    e["package_id"] = meta.get("package_id")
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    versions = sorted(stamps.values(), key=lambda v: v["stamp"], reverse=True)
    return JSONResponse({"engagement": eid, "versions": versions, "count": len(versions)})


@router.get("/api/engagements/{customer}/{project}/audit")
def engagement_audit(customer: str, project: str, request: Request):
    """The engagement's audit trail (E11.10): creation + every run_engagement /
    publish_estimate / calc run, newest first."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    key = f"engagements/{eid}/_audit.jsonl"
    entries: list[dict] = []
    try:
        raw = web_storage._estimate_container().download_blob(key).readall()
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    entries.reverse()
    return JSONResponse({"engagement": eid, "entries": entries[:200], "count": len(entries)})
