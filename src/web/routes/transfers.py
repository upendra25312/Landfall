"""Landfall transfers helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
import json
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from engagement_archive import InvalidArchive, unpack
import web_access
import web_runtime
import web_storage

router = APIRouter()


_EXPORT_MAX = 250 * 1024 * 1024


@router.get("/api/engagements/{customer}/{project}/export")
def engagement_export(customer: str, project: str, request: Request):
    """One .zip with the engagement manifest + every uploaded file + every produced
    artifact + the conversation — so an engagement is portable across `azd down` /
    `azd up` or between deployments (E11.26)."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, rawbase = eng
    import io
    import zipfile

    raw, ans = web_storage._raw_container(), web_storage._estimate_container()
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for cont, base, top in ((raw, f"{rawbase}/", "raw"),
                                (ans, f"engagements/{eid}/", "answers")):
            for b in cont.list_blobs(name_starts_with=base):
                rel = b.name[len(base):]
                if not rel or rel.endswith("/.keep") or b.size == 0:
                    continue  # skip empties + HNS directory markers
                data = cont.download_blob(b.name).readall()
                total += len(data)
                if total > _EXPORT_MAX:
                    return JSONResponse(
                        {"error": f"engagement is over the {_EXPORT_MAX // 1024 // 1024} MB "
                                  "export limit — remove old history/uploads first"}, status_code=413)
                z.writestr(f"{top}/{rel}", data)
        z.writestr("export.json", json.dumps(
            {"engagement": eid, "exported_at": web_runtime._now(), "format": "landfall-engagement/1"}))
    fn = eid.replace("/", "__") + ".landfall.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.post("/api/engagements/import")
async def engagement_import(request: Request, file: UploadFile, overwrite: str = Form("false")):
    """Restore an engagement from an export .zip into this deployment (E11.26)."""
    # C53: validate the archive and authorize its owner before any writes.
    actor = web_access._principal(request)[0]
    if not actor or actor in ("anonymous", "unknown"):
        return JSONResponse({"error": "sign in to import an engagement"}, status_code=401)
    try:
        clen = int(request.headers.get("content-length") or 0)
    except ValueError:
        clen = 0
    if clen and clen > _EXPORT_MAX:
        return JSONResponse({"error": "import file too large"}, status_code=413)

    data = await file.read(_EXPORT_MAX + 1)
    if len(data) > _EXPORT_MAX:
        return JSONResponse({"error": "import file too large"}, status_code=413)
    try:
        eid, manifest, members = unpack(data, _EXPORT_MAX)
    except InvalidArchive as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    raw, ans = web_storage._raw_container(), web_storage._estimate_container()
    try:
        existing = json.loads(raw.download_blob(f"engagements/{eid}/_engagement.json").readall())
        if not isinstance(existing, dict) or existing.get("created_by") != actor:
            return JSONResponse({"error": "only the engagement owner can replace it"}, status_code=403)
    except (ResourceNotFoundError, KeyError):
        existing = None
    except Exception:
        return JSONResponse({"error": "cannot verify existing engagement"}, status_code=503)
    if existing is not None and overwrite != "true":
        return JSONResponse({"error": f"engagement {eid} already exists — pass overwrite=true to replace",
                             "engagement": eid, "exists": True}, status_code=409)

    manifest["created_by"] = actor
    manifest["visibility"] = existing.get("visibility", "owner") if existing is not None else "owner"
    if existing is not None and "created_at" in existing:
        manifest["created_at"] = existing["created_at"]
    written = 0
    try:
        if existing is None:
            # Claim the name atomically before touching any uploaded artifacts.
            # A competing creator must stop this import before its first file write.
            raw.upload_blob(f"engagements/{eid}/_engagement.json", json.dumps(manifest).encode(),
                            overwrite=False)
            written += 1
        for name, body in members.items():
            if name in ("export.json", "raw/_engagement.json") or name.startswith("sql/"):
                continue
            top, rel = name.split("/", 1)
            (raw if top == "raw" else ans).upload_blob(f"engagements/{eid}/{rel}", body, overwrite=True)
            written += 1
        if existing is not None:
            raw.upload_blob(f"engagements/{eid}/_engagement.json", json.dumps(manifest).encode(), overwrite=True)
            written += 1
    except ResourceExistsError:
        return JSONResponse({"error": "engagement was created concurrently; retry after reviewing it",
                             "imported": written}, status_code=409)
    except Exception:
        return JSONResponse({"error": "import incomplete; storage write failed", "imported": written}, status_code=503)
    return JSONResponse({"engagement": eid, "imported": written, "manifest": manifest,
                         "not_imported": [name for name in members if name.startswith("sql/")]},
                        status_code=201)
