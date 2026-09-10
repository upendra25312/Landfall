"""Landfall uploads helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse
import base64
import discovery as _disc
import json
import uploads as _up
import web_access
import web_runtime
import web_storage
import asyncio
import os

router = APIRouter()


@router.post('/api/engagements/{customer}/{project}/upload-ticket')
async def upload_ticket(customer: str, project: str, request: Request):
    if os.environ.get('DIRECT_UPLOADS_ENABLED') != '1':
        return JSONResponse({'error': 'Direct uploads are not configured'}, status_code=503)
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({'error': 'unknown engagement'}, status_code=404)
    from direct_uploads import create_ticket
    try:
        return await asyncio.to_thread(create_ticket, eng[0], web_access._principal_name(request), await request.json())
    except (ValueError, TypeError):
        return JSONResponse({'error': 'Invalid upload ticket request'}, status_code=400)


@router.post('/api/engagements/{customer}/{project}/upload-complete')
async def upload_complete(customer: str, project: str, request: Request):
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({'error': 'unknown engagement'}, status_code=404)
    from direct_uploads import complete_ticket
    try:
        result = await asyncio.to_thread(complete_ticket, eng[0], web_access._principal_name(request),
                                         (await request.json()).get('ticket'))
        return JSONResponse(result, status_code=201)
    except (ValueError, TypeError):
        return JSONResponse({'error': 'Upload validation failed or ticket expired'}, status_code=400)
    except Exception:
        web_runtime.log.exception('Direct upload finalization failed')
        return JSONResponse({'error': 'Could not complete the upload; retry from the upload panel'}, status_code=502)


@router.get("/api/engagements/{customer}/{project}/files")
def engagement_files(customer: str, project: str, request: Request):
    """Manifest of what's been uploaded for this engagement (E11.24)."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown or malformed engagement"}, status_code=404)
    eid, base = eng
    files = web_storage._list_files(base)
    total = sum(f["size"] for f in files)
    return JSONResponse({"engagement": eid, "files": files, "count": len(files),
                         "bytes": total, "over_soft_cap": total > _up.MAX_ENGAGEMENT})


@router.post("/api/engagements/{customer}/{project}/upload")
async def engagement_upload(customer: str, project: str, request: Request,
                            file: UploadFile, kind: str = Form("auto")):
    """Stream one file into `raw/engagements/<c>/<p>/inventory|docs/` (E11.6/E11.24).
    Server-side only — no SAS to the browser. Slug-validated: a file cannot be
    written outside its engagement's prefix."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown or malformed engagement — create it first"},
                            status_code=404)
    eid, base = eng
    try:
        clen = int(request.headers.get("content-length") or 0)
    except ValueError:
        clen = 0
    if clen and clen > _up.MAX_REQUEST:
        return JSONResponse({"error": f"upload too large (limit {_up.MAX_REQUEST // 1024 // 1024} MB)"},
                            status_code=413)

    name = _up.safe_name(file.filename)
    from azure.storage.blob import BlobBlock, ContentSettings
    PEEK_CAP = 12 * 1024 * 1024
    CHUNK = 4 * 1024 * 1024
    buf = bytearray()
    total = 0
    checked = False
    kind_folder = None
    blocks: list = []
    bc = None

    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > _up.MAX_FILE:
            return JSONResponse(
                {"error": f"{name} is over the {_up.MAX_FILE // 1024 // 1024} MB per-file limit"},
                status_code=413)
        if len(buf) < PEEK_CAP:
            buf.extend(chunk[: PEEK_CAP - len(buf)])
        if not checked:
            ok, detected, reason = _up.classify(name, bytes(buf[:8192]))
            if not ok:
                return JSONResponse({"error": f"{name}: {reason}", "name": name}, status_code=415)
            kind_folder = detected if kind in ("auto", "", None) else (
                "docs" if kind == "docs" else "inventory")
            dest = f"{base}/{kind_folder}/{name}"
            bc = web_storage._raw_container().get_blob_client(dest)
            checked = True
        bid = base64.b64encode(f"blk-{len(blocks):06d}".encode()).decode()
        bc.stage_block(bid, bytes(chunk))
        blocks.append(BlobBlock(block_id=bid))

    if total == 0:
        return JSONResponse({"error": f"{name} is empty"}, status_code=400)

    info = _up.peek(name, bytes(buf)) if total <= PEEK_CAP else {"profile": "", "rows": 0, "columns": 0}
    meta = {"uploaded_by": web_access._principal_name(request),
            "profile": info.get("profile") or "", "rows": str(info.get("rows") or 0),
            "columns": str(info.get("columns") or 0), "kind": kind_folder}
    ctype = {"csv": "text/csv", "json": "application/json"}.get(
        name.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    try:
        bc.commit_block_list(blocks, metadata=meta, content_settings=ContentSettings(content_type=ctype))
    except Exception as exc:  # noqa: BLE001
        web_runtime.log.exception("upload commit failed")
        return JSONResponse({"error": f"could not store {name}: {exc}"}, status_code=500)

    resp = {
        "name": name, "kind": kind_folder, "size": total, "engagement": eid,
        "profile": info.get("profile") or "", "rows": info.get("rows") or 0,
        "columns": info.get("columns") or 0,
        "path": f"raw/{base}/{kind_folder}/{name}",
    }

    # E11.25 — a completed discovery questionnaire dropped into docs/ is recognised
    # by its question codes and its answers are written to _discovery.json.
    if kind_folder == "docs" and name.lower().endswith((".xlsx", ".docx", ".pdf")) \
            and total <= PEEK_CAP:
        try:
            parsed = _disc.parse_upload(bytes(buf), name)
            if parsed["is_template"]:
                rec = _disc.discovery_record(parsed["answers"], parsed["matched"], name,
                                             web_access._principal_name(request))
                web_storage._raw_container().upload_blob(f"{base}/_discovery.json",
                                             json.dumps(rec, indent=2).encode(), overwrite=True)
                resp["discovery"] = {"answered": len(parsed["answers"]),
                                     "matched": parsed["matched"],
                                     "gaps": rec["gaps"]["headline"]}
            elif parsed["format"] == "pdf":
                resp["discovery_note"] = ("PDF questionnaires aren't parsed — re-export "
                                          "the answers as .xlsx or .docx to feed the estimate")
        except Exception as exc:  # noqa: BLE001
            web_runtime.log.warning("discovery import skipped for %s: %s", name, exc)

    return JSONResponse(resp, status_code=201)


@router.delete("/api/engagements/{customer}/{project}/files/{name}")
def engagement_file_delete(customer: str, project: str, name: str, request: Request):
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    _eid, base = eng
    safe = _up.safe_name(name)
    cc = web_storage._raw_container()
    for sub in ("inventory", "docs"):
        try:
            cc.delete_blob(f"{base}/{sub}/{safe}")
            return JSONResponse({"deleted": safe, "kind": sub})
        except Exception:  # noqa: BLE001
            continue
    return JSONResponse({"error": f"{safe} not found"}, status_code=404)
