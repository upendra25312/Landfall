"""Landfall transfers helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
import json
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
    import io
    import zipfile

    try:
        clen = int(request.headers.get("content-length") or 0)
    except ValueError:
        clen = 0
    if clen and clen > _EXPORT_MAX:
        return JSONResponse({"error": "import file too large"}, status_code=413)

    data = await file.read()
    if len(data) > _EXPORT_MAX:
        return JSONResponse({"error": "import file too large"}, status_code=413)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        meta = json.loads(z.read("export.json"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "not a Landfall engagement export (missing export.json)"},
                            status_code=400)

    eid = (meta.get("engagement") or "").strip().strip("/")
    parts = eid.split("/")
    if len(parts) != 2 or not (web_access._seg(parts[0]) and web_access._seg(parts[1])):
        return JSONResponse({"error": f"bad engagement id in export: {eid!r}"}, status_code=400)

    raw, ans = web_storage._raw_container(), web_storage._estimate_container()
    try:
        raw.download_blob(f"engagements/{eid}/_engagement.json").readall()
        exists = True
    except Exception:  # noqa: BLE001
        exists = False
    if exists and overwrite != "true":
        return JSONResponse({"error": f"engagement {eid} already exists — pass overwrite=true to replace",
                             "engagement": eid, "exists": True}, status_code=409)

    written = 0
    for name in z.namelist():
        if name == "export.json" or name.endswith("/"):
            continue
        if ".." in name.replace("\\", "/").split("/") or name.startswith("/"):
            continue
        body = z.read(name)
        if name.startswith("raw/"):
            raw.upload_blob(f"engagements/{eid}/{name[4:]}", body, overwrite=True)
            written += 1
        elif name.startswith("answers/"):
            ans.upload_blob(f"engagements/{eid}/{name[8:]}", body, overwrite=True)
            written += 1
    try:
        manifest = json.loads(raw.download_blob(f"engagements/{eid}/_engagement.json").readall())
    except Exception:  # noqa: BLE001
        manifest = {"engagement": eid}
    return JSONResponse({"engagement": eid, "imported": written, "manifest": manifest},
                        status_code=201)
