"""
Landfall chat UI - a thin FastAPI front end over the Foundry Migration Estimator agent.

One page, one endpoint. The agent is a Microsoft Foundry prompt agent addressed by
name and driven through the Responses API; each browser tab carries the last
response id so the conversation keeps its memory. Authentication in front of this
app is handled by the Container App's built-in Entra ID (Easy Auth) - configure it
after first deploy.
"""
import base64
import datetime as _dt
import os
import json
import pathlib
import logging

from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

import uploads as _up

logging.basicConfig(level=logging.INFO)

PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
AGENT_NAME = os.environ.get("AGENT_ID", "")  # Foundry agents are addressed by name
STORAGE_URL = os.environ.get("STORAGE_URL", "")  # assessment dashboard reads answers/estimate/*

_cred = DefaultAzureCredential()
_clients: dict = {}


def _openai_client():
    """Lazy — keep import (and container start) free of network / token calls."""
    if "openai" not in _clients:
        proj = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=_cred)
        _clients["openai"] = proj.get_openai_client()
    return _clients["openai"]


app = FastAPI(title="Landfall")

_HERE = pathlib.Path(__file__).parent
_ESTIMATE = {"prefix": "estimate", "container": "answers"}
_EXPORT_MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_blob_state: dict = {}


def _estimate_container():
    if "cc" not in _blob_state:
        from azure.storage.blob import BlobServiceClient

        if not STORAGE_URL:
            raise RuntimeError("STORAGE_URL not set")
        svc = BlobServiceClient(STORAGE_URL, credential=_cred)
        _blob_state["cc"] = svc.get_container_client(_ESTIMATE["container"])
    return _blob_state["cc"]


def _estimate_prefixes(engagement: str | None) -> list[str]:
    """Where a published estimate might live. Prefer the engagement path; fall back to
    the default engagement, then the pre-E11 flat `estimate/` path."""
    out = []
    eid = (engagement or "").strip().strip("/")
    if eid and eid != "_default_/_default_":
        out.append(f"engagements/{eid}/estimate")
    out.append("engagements/_default_/_default_/estimate")
    out.append("estimate")  # legacy (cycles 1-17)
    return out


def _read_estimate_blob(name: str, engagement: str | None = None) -> bytes | None:
    for prefix in _estimate_prefixes(engagement):
        try:
            return _estimate_container().download_blob(f"{prefix}/{name}").readall()
        except Exception:  # noqa: BLE001 - missing blob -> try the next location
            continue
    return None


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# --- per-engagement conversation (E11.26) ---------------------------------
# The Responses API stores the conversation server-side in the Foundry project;
# we persist only the pointer + a transcript in the engagement's own blob so the
# chat survives a browser close, is scoped to the customer/project, and travels
# with the engagement export. No new Azure resources.

def _chat_blob(eid: str) -> str:
    return f"engagements/{eid}/_chat.json"


def _load_chat(eid: str) -> dict:
    try:
        return json.loads(_estimate_container().download_blob(_chat_blob(eid)).readall())
    except Exception:  # noqa: BLE001
        return {"engagement": eid, "current_response_id": None, "started_at": _now(),
                "turns": [], "archived": []}


def _save_chat(eid: str, chat: dict) -> None:
    _estimate_container().upload_blob(
        _chat_blob(eid), json.dumps(chat, default=str).encode(), overwrite=True)


def _citations(resp) -> list:
    """Pull document/URL citation labels out of a Responses API result."""
    seen = []
    for item in getattr(resp, "output", None) or []:
        for content in getattr(item, "content", None) or []:
            for ann in getattr(content, "annotations", None) or []:
                label = (
                    getattr(ann, "filename", None)
                    or getattr(ann, "title", None)
                    or getattr(ann, "url", None)
                )
                if label and label not in seen:
                    seen.append(label)
    return sorted(seen)


@app.get("/healthz")
def health():
    return {"ok": True, "agent_configured": bool(AGENT_NAME),
            "storage_configured": bool(STORAGE_URL),
            "estimate_published": _read_estimate_blob("latest.json") is not None}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    question = (body.get("message") or "").strip()
    engagement = (body.get("engagement") or "").strip().strip("/")
    if not question:
        return JSONResponse({"error": "empty message"}, status_code=400)
    if not AGENT_NAME:
        return JSONResponse({"error": "AGENT_ID not set - run the postprovision hook"}, status_code=503)

    # The conversation pointer comes from the engagement's stored chat, not the
    # browser (E11.26). Falls back to a body thread_id only when unscoped.
    chat_doc = _load_chat(engagement) if engagement else {}
    prev_id = chat_doc.get("current_response_id") or (body.get("thread_id") if not engagement else None)

    scoped = question
    if engagement:
        # the user never types the engagement id — prepend a scoping instruction so the
        # agent passes it to every tool call (E11.7).
        scoped = (f"[Active engagement: {engagement}. Use exactly this value as the "
                  f"`engagement` argument for every tool call — do not ask the user "
                  f"for it.]\n\n{question}")

    try:
        kwargs = {
            "input": scoped,
            "extra_body": {
                "agent_reference": {"type": "agent_reference", "name": AGENT_NAME}
            },
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
        resp = _openai_client().responses.create(**kwargs)
        text = (resp.output_text or "").strip()
        if not text:
            return JSONResponse(
                {"error": f"agent returned no text (status {resp.status})", "thread_id": resp.id},
                status_code=502,
            )
        cites = _citations(resp)
        if engagement:
            ts = _now()
            chat_doc.setdefault("turns", []).append({"role": "user", "text": question, "ts": ts})
            chat_doc["turns"].append({"role": "assistant", "text": text, "ts": ts, "citations": cites})
            chat_doc["current_response_id"] = resp.id
            chat_doc["engagement"] = engagement
            chat_doc.setdefault("started_at", ts)
            try:
                _save_chat(engagement, chat_doc)
            except Exception:  # noqa: BLE001
                logging.exception("could not persist the conversation for %s", engagement)
        return {"answer": text, "citations": cites, "thread_id": resp.id}
    except Exception as exc:  # noqa: BLE001
        logging.exception("chat failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


def _calc_regions() -> list[str]:
    if "regions" not in _blob_state:
        try:
            _blob_state["regions"] = json.loads(
                (_HERE / "calc_regions.json").read_text(encoding="utf-8")).get("regions", [])
        except Exception:  # noqa: BLE001
            _blob_state["regions"] = ["swedencentral", "westeurope", "northeurope",
                                      "eastus", "eastus2", "westus2", "uksouth"]
    return _blob_state["regions"]


@app.get("/api/calc_regions")
def calc_regions():
    """Azure regions the Pricing Calculator can price — for the engagement region picker."""
    return JSONResponse({"regions": _calc_regions()})


def _raw_container():
    if "raw" not in _blob_state:
        from azure.storage.blob import BlobServiceClient
        if not STORAGE_URL:
            raise RuntimeError("STORAGE_URL not set")
        svc = BlobServiceClient(STORAGE_URL, credential=_cred)
        _blob_state["raw"] = svc.get_container_client("raw")
    return _blob_state["raw"]


# slug segments are [a-z0-9-]; the seed engagement `_default_` also uses underscores.
_SEG_RE = __import__("re").compile(r"^[a-z0-9_][a-z0-9_-]{0,49}$")


def _slug(v: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (v or "").strip().lower()).strip("-")
    return s[:40] or "x"


def _principal_name(request: Request) -> str:
    return (request.headers.get("x-ms-client-principal-name")
            or request.headers.get("x-ms-client-principal-id") or "anonymous")


@app.get("/api/engagements")
def engagements_list(request: Request):
    """List engagements from blob (`raw/engagements/<c>/<p>/_engagement.json`), filtered
    by the caller's visibility (E11.6). The chat page uses this for its engagement picker
    so the user never types the `<customer>/<project>` id."""
    me = _principal_name(request)
    out = []
    try:
        cc = _raw_container()
        for b in cc.list_blobs(name_starts_with="engagements/"):
            if not b.name.endswith("/_engagement.json"):
                continue
            try:
                m = json.loads(cc.download_blob(b.name).readall())
            except Exception:  # noqa: BLE001
                continue
            vis = m.get("visibility", "owner")
            if vis == "owner" and m.get("created_by") not in (me, "anonymous"):
                continue
            out.append({k: m.get(k) for k in
                        ("engagement", "customer", "project", "target_region", "dr_region",
                         "currency", "licensing_program", "status", "created_by", "created_at",
                         "target_region_calculator_supported")})
    except Exception as exc:  # noqa: BLE001
        logging.warning("engagements_list failed: %s", exc)
        return JSONResponse({"engagements": [], "error": str(exc)})
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return JSONResponse({"engagements": out})


@app.post("/api/engagements")
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
    c, p = _slug(customer), _slug(project)
    cc = _raw_container()
    eid = f"{c}/{p}"
    for n in range(2, 50):
        try:
            cc.download_blob(f"engagements/{eid}/_engagement.json")
            eid = f"{c}/{p}-{n}"
        except Exception:  # noqa: BLE001
            break
    tr = (body.get("target_region") or "swedencentral").strip().lower()
    supported = tr in _calc_regions()
    manifest = {
        "engagement": eid, "customer": customer, "project": project,
        "customer_slug": eid.split("/")[0], "project_slug": eid.split("/")[1],
        "region": tr, "target_region": tr,
        "dr_region": (body.get("dr_region") or "").strip().lower() or None,
        "currency": (body.get("currency") or "USD").upper(),
        "licensing_program": (body.get("licensing_program") or "MCA").upper(),
        "target_region_calculator_supported": supported,
        "notes": body.get("notes") or "", "visibility": "owner", "status": "new",
        "created_by": _principal_name(request),
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        cc.upload_blob(f"engagements/{eid}/_engagement.json",
                       json.dumps(manifest, indent=2).encode(), overwrite=True)
        for rel in ("inventory/.keep", "docs/.keep"):
            cc.upload_blob(f"engagements/{eid}/{rel}", b"", overwrite=True)
    except Exception as exc:  # noqa: BLE001
        logging.exception("engagement create failed")
        return JSONResponse({"error": f"provisioning failed: {exc}"}, status_code=500)
    return JSONResponse(manifest, status_code=201)


def _seg(v: str) -> str | None:
    v = (v or "").strip().lower()
    return v if _SEG_RE.match(v) else None


def _engagement(customer: str, project: str) -> tuple[str, str] | None:
    """Validate the path pair -> ('<c>/<p>', 'engagements/<c>/<p>'). None if malformed
    or the engagement doesn't exist (no `_engagement.json`)."""
    c, p = _seg(customer), _seg(project)
    if not c or not p:
        return None
    eid = f"{c}/{p}"
    try:
        _raw_container().download_blob(f"engagements/{eid}/_engagement.json").readall()
    except Exception:  # noqa: BLE001
        return None
    return eid, f"engagements/{eid}"


def _list_files(base: str) -> list[dict]:
    cc = _raw_container()
    out = []
    for sub in ("inventory", "docs"):
        for b in cc.list_blobs(name_starts_with=f"{base}/{sub}/", include=["metadata"]):
            fn = b.name.rsplit("/", 1)[-1]
            if not fn or fn == ".keep":
                continue
            md = getattr(b, "metadata", None) or {}
            out.append({
                "name": fn, "kind": sub, "size": b.size,
                "uploaded_at": (b.last_modified.isoformat() if b.last_modified else None),
                "uploaded_by": md.get("uploaded_by"),
                "profile": md.get("profile") or "",
                "rows": int(md.get("rows") or 0), "columns": int(md.get("columns") or 0),
            })
    out.sort(key=lambda x: x.get("uploaded_at") or "", reverse=True)
    return out


@app.get("/api/engagements/{customer}/{project}/files")
def engagement_files(customer: str, project: str):
    """Manifest of what's been uploaded for this engagement (E11.24)."""
    eng = _engagement(customer, project)
    if not eng:
        return JSONResponse({"error": "unknown or malformed engagement"}, status_code=404)
    eid, base = eng
    files = _list_files(base)
    total = sum(f["size"] for f in files)
    return JSONResponse({"engagement": eid, "files": files, "count": len(files),
                         "bytes": total, "over_soft_cap": total > _up.MAX_ENGAGEMENT})


@app.post("/api/engagements/{customer}/{project}/upload")
async def engagement_upload(customer: str, project: str, request: Request,
                            file: UploadFile, kind: str = Form("auto")):
    """Stream one file into `raw/engagements/<c>/<p>/inventory|docs/` (E11.6/E11.24).
    Server-side only — no SAS to the browser. Slug-validated: a file cannot be
    written outside its engagement's prefix."""
    eng = _engagement(customer, project)
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
            bc = _raw_container().get_blob_client(dest)
            checked = True
        bid = base64.b64encode(f"blk-{len(blocks):06d}".encode()).decode()
        bc.stage_block(bid, bytes(chunk))
        blocks.append(BlobBlock(block_id=bid))

    if total == 0:
        return JSONResponse({"error": f"{name} is empty"}, status_code=400)

    info = _up.peek(name, bytes(buf)) if total <= PEEK_CAP else {"profile": "", "rows": 0, "columns": 0}
    meta = {"uploaded_by": _principal_name(request),
            "profile": info.get("profile") or "", "rows": str(info.get("rows") or 0),
            "columns": str(info.get("columns") or 0), "kind": kind_folder}
    ctype = {"csv": "text/csv", "json": "application/json"}.get(
        name.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    try:
        bc.commit_block_list(blocks, metadata=meta, content_settings=ContentSettings(content_type=ctype))
    except Exception as exc:  # noqa: BLE001
        logging.exception("upload commit failed")
        return JSONResponse({"error": f"could not store {name}: {exc}"}, status_code=500)

    return JSONResponse({
        "name": name, "kind": kind_folder, "size": total, "engagement": eid,
        "profile": info.get("profile") or "", "rows": info.get("rows") or 0,
        "columns": info.get("columns") or 0,
        "path": f"raw/{base}/{kind_folder}/{name}",
    }, status_code=201)


@app.delete("/api/engagements/{customer}/{project}/files/{name}")
def engagement_file_delete(customer: str, project: str, name: str):
    eng = _engagement(customer, project)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    _eid, base = eng
    safe = _up.safe_name(name)
    cc = _raw_container()
    for sub in ("inventory", "docs"):
        try:
            cc.delete_blob(f"{base}/{sub}/{safe}")
            return JSONResponse({"deleted": safe, "kind": sub})
        except Exception:  # noqa: BLE001
            continue
    return JSONResponse({"error": f"{safe} not found"}, status_code=404)


@app.get("/api/engagements/{customer}/{project}/chat")
def engagement_chat_get(customer: str, project: str):
    """The saved conversation for this engagement (E11.26) — the page renders it on
    load / engagement switch so nothing is lost on a browser close."""
    eng = _engagement(customer, project)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    c = _load_chat(eid)
    return JSONResponse({"engagement": eid, "turns": c.get("turns", []),
                         "current_response_id": c.get("current_response_id"),
                         "archived": c.get("archived", [])})


@app.post("/api/engagements/{customer}/{project}/chat/new")
def engagement_chat_new(customer: str, project: str):
    """Start a fresh thread for this engagement — the previous one is archived, not
    destroyed (its Foundry response chain stays retrievable)."""
    eng = _engagement(customer, project)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    c = _load_chat(eid)
    if c.get("turns"):
        c.setdefault("archived", []).append({
            "started_at": c.get("started_at"), "ended_at": _now(),
            "last_response_id": c.get("current_response_id"), "turns": len(c["turns"])})
    c.update({"turns": [], "current_response_id": None, "started_at": _now(), "engagement": eid})
    try:
        _save_chat(eid, c)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"engagement": eid, "cleared": True, "archived": len(c["archived"])})


_EXPORT_MAX = 250 * 1024 * 1024


@app.get("/api/engagements/{customer}/{project}/export")
def engagement_export(customer: str, project: str):
    """One .zip with the engagement manifest + every uploaded file + every produced
    artifact + the conversation — so an engagement is portable across `azd down` /
    `azd up` or between deployments (E11.26)."""
    eng = _engagement(customer, project)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, rawbase = eng
    import io
    import zipfile

    raw, ans = _raw_container(), _estimate_container()
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
            {"engagement": eid, "exported_at": _now(), "format": "landfall-engagement/1"}))
    fn = eid.replace("/", "__") + ".landfall.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.post("/api/engagements/import")
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
    if len(parts) != 2 or not (_seg(parts[0]) and _seg(parts[1])):
        return JSONResponse({"error": f"bad engagement id in export: {eid!r}"}, status_code=400)

    raw, ans = _raw_container(), _estimate_container()
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


@app.get("/api/prompt_cards")
def prompt_cards():
    """Intro + capability list + the clickable prompt cards for the chat UI (E11.7).
    Config so pre-sales can edit `src/web/prompt_cards.json` without a code change."""
    try:
        return JSONResponse(json.loads((_HERE / "prompt_cards.json").read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        logging.warning("prompt_cards.json unreadable: %s", exc)
        return JSONResponse({"intro": {"title": "Landfall — Migration Estimator",
                                       "body": "Ask about the client inventory, sizing, waves or cost.",
                                       "capabilities": []}, "cards": []})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """The assessment dashboard — an Azure Migrate–style read of the published estimate."""
    return (_HERE / "dashboard.html").read_text(encoding="utf-8")


@app.get("/dashboard/data")
def dashboard_data(e: str | None = None):
    blob = _read_estimate_blob("latest.json", e)
    if blob is None:
        return JSONResponse({"error": "no estimate published"}, status_code=404)
    return JSONResponse(json.loads(blob))


@app.get("/dashboard/download/{fmt}")
def dashboard_download(fmt: str, e: str | None = None):
    fmt = fmt.lower().lstrip(".")
    if fmt not in _EXPORT_MIME:
        return JSONResponse({"error": "format must be xlsx | docx | pptx"}, status_code=400)
    blob = _read_estimate_blob(f"latest.{fmt}", e)
    if blob is None:
        return JSONResponse({"error": f"no {fmt} export published"}, status_code=404)
    name = (e or "landfall-estimate").replace("/", "-")
    return Response(blob, media_type=_EXPORT_MIME[fmt], headers={
        "Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


@app.get("/dashboard/landing-zone")
def landing_zone_data(e: str | None = None):
    """The Azure Pricing Calculator POE summary (landing_zone.json) for an engagement."""
    blob = _read_estimate_blob("landing_zone.json", e)
    if blob is None:
        return JSONResponse({"error": "no Pricing Calculator estimate built yet"}, status_code=404)
    return JSONResponse(json.loads(blob))


@app.get("/dashboard/download/landing-zone-xlsx")
def landing_zone_xlsx(e: str | None = None):
    """Stream the Azure Pricing Calculator's own Excel export — the POE artifact."""
    blob = _read_estimate_blob("landing_zone.xlsx", e)
    if blob is None:
        return JSONResponse({"error": "no Pricing Calculator estimate built yet"}, status_code=404)
    name = (e or "landfall").replace("/", "-") + "-landing-zone-POE"
    return Response(blob, media_type=_EXPORT_MIME["xlsx"], headers={
        "Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html><html><head><meta charset=utf-8>
<title>Landfall</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>
 :root{--bg:#0b151d;--panel:#111f2a;--line:#25343f;--ink:#e6edf1;--muted:#94a5b0;--accent:#0e7c8b}
 *{box-sizing:border-box}
 body{font:15px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
 header{display:flex;align-items:center;gap:12px;padding:12px 20px;border-bottom:1px solid var(--line);font-weight:600;position:sticky;top:0;background:var(--bg);z-index:5}
 header .sp{flex:1}
 header a,header button.link{color:#7fd3dd;font-size:13px;text-decoration:none;background:none;border:0;cursor:pointer;font-family:inherit}
 header button.link:hover,header a:hover{text-decoration:underline}
 #log{max-width:820px;margin:0 auto;padding:20px 20px 8px}
 .m{margin:12px 0;padding:12px 14px;border-radius:10px;white-space:pre-wrap;word-wrap:break-word}
 .u{background:#152430}
 .a{background:var(--panel);border:1px solid var(--line)}
 .c{font-size:12px;color:var(--muted);margin-top:6px}
 .empty{max-width:820px;margin:60px auto;text-align:center;color:var(--muted)}
 .working{display:flex;align-items:center;gap:10px;color:var(--muted)}
 .spin{width:15px;height:15px;border:2px solid var(--line);border-top-color:#7fd3dd;border-radius:50%;animation:sp .8s linear infinite;flex:none}
 @keyframes sp{to{transform:rotate(360deg)}}
 .dots::after{content:'';animation:dots 1.4s steps(4,end) infinite}
 @keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
 form{position:sticky;bottom:0;background:var(--bg);max-width:820px;margin:0 auto;display:flex;gap:8px;padding:14px 20px 18px;border-top:1px solid var(--line)}
 input{flex:1;padding:11px 12px;border-radius:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font:inherit}
 input:disabled{opacity:.55}
 button.send{padding:11px 20px;border-radius:8px;border:0;background:var(--accent);color:#fff;font-weight:600;cursor:pointer}
 button.send:disabled{opacity:.5;cursor:default}
 .intro{max-width:820px;margin:26px auto 6px;padding:0 20px}
 .intro h2{margin:0 0 8px;font-size:19px}
 .intro p{color:var(--muted);margin:0 0 14px}
 .intro p.sub{font-size:13px;margin:0 0 10px}
 .caps{list-style:none;margin:0 0 18px;padding:0;display:grid;gap:6px}
 .caps li{color:var(--ink);font-size:13.5px;padding-left:18px;position:relative}
 .caps li::before{content:'▹';position:absolute;left:0;color:#7fd3dd}
 .cardgrid{max-width:820px;margin:0 auto 4px;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
 .pc{display:flex;align-items:center;gap:9px;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--ink);font:inherit;font-size:13px;text-align:left;cursor:pointer}
 .pc:hover{border-color:#7fd3dd}
 .pc .ic{width:20px;height:20px;border-radius:6px;background:#152430;display:flex;align-items:center;justify-content:center;color:#7fd3dd;flex:none}
 .pc:disabled{opacity:.5;cursor:default}
 select,.mini input{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:7px 8px;font:inherit;font-size:13px}
 #engsel{max-width:280px}
 .mini{max-width:820px;margin:14px auto 0;padding:0 20px}
 .mini form{position:static;border:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:8px;background:none;max-width:none}
 .mini .full{grid-column:1/-1}
 .warn{color:#f0a35e;font-size:12px}
 #uploadpanel{max-width:820px;margin:14px auto 0;padding:0 20px}
 .utabs{display:flex;align-items:center;gap:12px;margin:0 0 8px;font-size:12px;color:var(--muted)}
 .utabs label{cursor:pointer}
 .uz{border:1.5px dashed var(--line);border-radius:12px;padding:16px;text-align:center;background:var(--panel);cursor:pointer;color:var(--muted);font-size:12.5px;line-height:1.7}
 .uz.drag{border-color:#7fd3dd;color:var(--ink);background:#152430}
 .uz b{color:#7fd3dd}
 #filerows{list-style:none;margin:8px 0 0;padding:0}
 .frow{display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;margin-top:8px;font-size:13px}
 .frow .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .frow .st{color:var(--muted);font-size:12px;white-space:nowrap}
 .frow.ok{border-color:#1f6f43}.frow.ok .st{color:#6fce9a}
 .frow.err{border-color:#7a3b2e}.frow.err .st{color:#f0a35e}
 .frow .pbar{width:74px;height:6px;border-radius:3px;background:#152430;overflow:hidden;flex:none}
 .frow .pbar i{display:block;height:100%;background:#7fd3dd;width:0;transition:width .2s}
 .frow .x{color:var(--muted);cursor:pointer;background:none;border:0;font:inherit;flex:none}
 .toast{position:fixed;left:50%;transform:translateX(-50%);bottom:84px;background:#152430;border:1px solid var(--line);border-radius:8px;padding:10px 16px;font-size:13px;z-index:20;opacity:0;pointer-events:none;transition:opacity .3s}
 .toast.show{opacity:1}
</style></head><body>
<header>
 <span>Landfall &mdash; Migration Estimator</span>
 <select id=engsel title="Active engagement — every question, upload and estimate is scoped to it"></select>
 <button class=link id=neweng title="Create a new customer / project engagement">+ New engagement</button>
 <button class=link id=expeng title="Download this engagement (files + estimates + chat) as a portable .zip" hidden>&darr; export</button>
 <button class=link id=impeng title="Restore an engagement from a .landfall.zip">&uarr; import</button>
 <input type=file id=impfile accept=".zip" hidden>
 <span class=sp></span>
 <button class=link id=newchat title="Archive this conversation and start a fresh one">+ New chat</button>
 <a href="/dashboard">Assessment dashboard &rarr;</a>
</header>
<div class=mini id=engform hidden>
 <form id=ef>
  <input name=customer placeholder="Customer name" required>
  <input name=project placeholder="Project name" required>
  <select name=target_region id=trsel title="Target Azure region for the landing zone"></select>
  <select name=dr_region id=drsel title="DR region (optional)"><option value="">No DR region</option></select>
  <select name=licensing_program><option value=MCA>Microsoft Customer Agreement (MCA)</option><option value=EA>Enterprise Agreement</option><option value=MOSP>Pay-as-you-go (MOSP)</option><option value=CSP>CSP</option></select>
  <select name=currency><option>USD</option><option>EUR</option><option>GBP</option><option>AUD</option><option>INR</option><option>SEK</option></select>
  <div class=full><button class=send type=submit>Create engagement</button>
   <button class=link type=button id=engcancel style="margin-left:10px">cancel</button></div>
 </form>
</div>
<div id=uploadpanel hidden>
 <div class=utabs>
  <span style="color:var(--ink)">Inventory &amp; documents for <b id=upeng></b></span>
  <span style="flex:1"></span>
  <label><input type=radio name=ukind value=auto checked> auto</label>
  <label><input type=radio name=ukind value=inventory> data</label>
  <label><input type=radio name=ukind value=docs> docs</label>
 </div>
 <label class=uz id=uz>
  <input type=file id=ufile multiple hidden>
  Drop files here or <b>browse</b><br>
  CSV · Excel · TSV · JSON &mdash; server / application inventory &nbsp;·&nbsp; PDF · Word · PNG &mdash; diagrams, DR, compliance<br>
  <span style="font-size:11px">up to 100&nbsp;MB each &mdash; lands in this engagement's private folder</span>
 </label>
 <ul id=filerows></ul>
</div>
<div id=toast class=toast></div>
<div id=log><div id=welcome></div></div>
<form id=f>
 <input id=q placeholder="Ask about the client inventory, sizing, waves, cost..." autocomplete=off>
 <button class=send id=send>Send</button>
</form>
<script>
let busy=false,CARDS=[],ENG=localStorage.getItem('landfall.eng')||'';
const log=document.getElementById('log'),q=document.getElementById('q'),send=document.getElementById('send');
const engsel=document.getElementById('engsel'),engform=document.getElementById('engform');

function add(t,cls,cites){
 const d=document.createElement('div');d.className='m '+cls;d.textContent=t;
 if(cites&&cites.length){const c=document.createElement('div');c.className='c';c.textContent='Sources: '+cites.join(', ');d.appendChild(c);}
 log.appendChild(d);d.scrollIntoView({block:'end'});return d;
}
function working(){
 const d=document.createElement('div');d.className='m a';
 d.innerHTML='<div class="working"><span class="spin"></span><span>The estimator is working<span class="dots"></span> <span class="el"></span></span></div>';
 log.appendChild(d);d.scrollIntoView({block:'end'});
 const t0=Date.now();const el=d.querySelector('.el');
 d._timer=setInterval(()=>{el.textContent='('+Math.round((Date.now()-t0)/1000)+'s)';},1000);
 return d;
}
function setBusy(b){busy=b;q.disabled=b;send.disabled=b;send.textContent=b?'Working…':'Send';
 document.querySelectorAll('.pc').forEach(x=>x.disabled=b);if(!b)q.focus();}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

function renderWelcome(){
 const w=document.getElementById('welcome');if(!w)return;
 const i=window._intro||{};
 const caps=(i.capabilities||[]).map(c=>'<li>'+esc(c)+'</li>').join('');
 const cards=CARDS.map((c,ix)=>'<button class=pc data-i="'+ix+'"><span class=ic>'+esc(c.icon||'▸')+'</span><span>'+esc(c.label)+'</span></button>').join('');
 const engnote = ENG
  ? '<p class=sub style="color:#7fd3dd">Active engagement: <b>'+esc(engLabel(ENG))+'</b> — every answer, upload and estimate is scoped to it. Add the client inventory in the panel above, then ask for the estimate.</p>'
  : '<p class="sub warn">No engagement selected. Pick one top-left, or click <b>+ New engagement</b> to start a customer / project — then upload their server &amp; application inventory.</p>';
 w.innerHTML='<div class=intro><h2>'+esc(i.title||'Landfall — Migration Estimator')+'</h2>'
  +engnote
  +'<p>'+esc(i.body||'').replace(/\\n/g,'<br>')+'</p>'
  +(caps?'<ul class=caps>'+caps+'</ul>':'')+'</div>'
  +(cards?'<div class=cardgrid>'+cards+'</div>':'');
 w.querySelectorAll('.pc').forEach(b=>b.onclick=()=>{if(busy)return;ask(CARDS[+b.dataset.i].prompt);});
}

async function loadCards(){
 try{const r=await fetch('/api/prompt_cards');const j=await r.json();
  window._intro=j.intro||{};CARDS=j.cards||[];}
 catch(e){window._intro={};CARDS=[];}
 renderWelcome();
}

async function loadEngagements(){
 let list=[];
 try{const r=await fetch('/api/engagements');list=(await r.json()).engagements||[];}catch(e){}
 engsel.innerHTML='';
 if(!list.length){
  const o=document.createElement('option');o.value='';o.textContent='— no engagements —';engsel.appendChild(o);
 }
 list.forEach(e=>{
  const o=document.createElement('option');o.value=e.engagement;
  o.textContent=(e.customer||e.engagement.split('/')[0])+' / '+(e.project||e.engagement.split('/')[1])
   +'  ·  '+(e.target_region||'?');
  engsel.appendChild(o);
 });
 if(ENG && list.some(e=>e.engagement===ENG)) engsel.value=ENG;
 else { ENG=engsel.value||''; localStorage.setItem('landfall.eng',ENG); }
 document.getElementById('expeng').hidden=!ENG;
 renderWelcome();showUpload();loadChat();
}
engsel.onchange=()=>{ENG=engsel.value;localStorage.setItem('landfall.eng',ENG);
 document.getElementById('expeng').hidden=!ENG;renderWelcome();showUpload();loadChat();};

// --- per-engagement conversation (E11.26) ------------------------------
async function loadChat(){
 if(!ENG){return;}
 let doc={turns:[]};
 const [c,p]=ENG.split('/');
 try{doc=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/chat')).json();}catch(e){}
 const turns=doc.turns||[];
 log.innerHTML='<div id=welcome></div>';
 if(!turns.length){renderWelcome();return;}
 document.getElementById('welcome').remove();
 turns.forEach(t=>add(t.text,t.role==='user'?'u':'a',t.citations));
}
document.getElementById('expeng').onclick=()=>{
 if(!ENG)return;const [c,p]=ENG.split('/');
 window.location='/api/engagements/'+enc(c)+'/'+enc(p)+'/export';
};
const impfile=document.getElementById('impfile');
document.getElementById('impeng').onclick=()=>impfile.click();
impfile.onchange=async()=>{
 const f=impfile.files[0];impfile.value='';if(!f)return;
 const fd=new FormData();fd.append('file',f);
 let r=await fetch('/api/engagements/import',{method:'POST',body:fd});
 let j=await r.json();
 if(r.status===409 && confirm(j.error+'\\n\\nReplace it?')){
  fd.append('overwrite','true');
  r=await fetch('/api/engagements/import',{method:'POST',body:fd});j=await r.json();
 }
 if(j.error){alert('Import failed: '+j.error);return;}
 toast('Imported '+j.engagement+' ('+j.imported+' files)');
 ENG=j.engagement;localStorage.setItem('landfall.eng',ENG);
 await loadEngagements();engsel.value=ENG;
};

// --- Upload panel (E11.6 / E11.24) ---------------------------------------
const upanel=document.getElementById('uploadpanel'),uz=document.getElementById('uz'),
      ufile=document.getElementById('ufile'),frows=document.getElementById('filerows'),
      toastEl=document.getElementById('toast');
const enc=encodeURIComponent;
function toast(m){toastEl.textContent=m;toastEl.classList.add('show');setTimeout(()=>toastEl.classList.remove('show'),3200);}
function ukind(){return (document.querySelector('input[name=ukind]:checked')||{}).value||'auto';}
function fmtSize(n){return n>=1048576?(n/1048576).toFixed(1)+' MB':n>=1024?Math.round(n/1024)+' KB':n+' B';}
function engLabel(eid){const o=[...engsel.options].find(o=>o.value===eid);return o?o.textContent.split('  ·  ')[0]:eid;}
function showUpload(){
 if(!ENG){upanel.hidden=true;return;}
 upanel.hidden=false;document.getElementById('upeng').textContent=engLabel(ENG);loadFiles();
}
async function loadFiles(){
 frows.innerHTML='';if(!ENG)return;
 const [c,p]=ENG.split('/');
 try{
  const j=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files')).json();
  (j.files||[]).forEach(f=>frows.appendChild(doneRow(f)));
  if(j.over_soft_cap)toast('This engagement is over the 2 GB soft cap.');
 }catch(e){}
}
function delFile(nm){
 return async()=>{if(!confirm('Remove '+nm+'?'))return;const [c,p]=ENG.split('/');
  await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files/'+enc(nm),{method:'DELETE'});loadFiles();};
}
function doneRow(f){
 const li=document.createElement('li');li.className='frow ok';
 const prof=f.profile?(' · '+esc(f.profile)):'',rows=f.rows?(' · '+f.rows+' rows'):'';
 li.innerHTML='<span class=nm>'+esc(f.name)+'</span><span class=st>✓ '+esc(f.kind)+prof+rows+' · '+fmtSize(f.size)+'</span><button class=x title=Remove>✕</button>';
 li.querySelector('.x').onclick=delFile(f.name);return li;
}
function uploadOne(file){
 const li=document.createElement('li');li.className='frow';
 li.innerHTML='<span class=nm>'+esc(file.name)+'</span><span class=pbar><i></i></span><span class=st>uploading…</span>';
 frows.prepend(li);
 const bar=li.querySelector('.pbar i'),st=li.querySelector('.st'),[c,p]=ENG.split('/');
 const fd=new FormData();fd.append('kind',ukind());fd.append('file',file);
 const xhr=new XMLHttpRequest();
 xhr.open('POST','/api/engagements/'+enc(c)+'/'+enc(p)+'/upload');
 xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.round(e.loaded/e.total*100);bar.style.width=pct+'%';st.textContent=pct<100?('uploading '+pct+'%'):'checking…';}};
 xhr.onload=()=>{let j={};try{j=JSON.parse(xhr.responseText);}catch(e){}
  if(xhr.status===201){li.replaceWith(doneRow(j));toast(j.name+' added to '+engLabel(ENG));}
  else{li.className='frow err';
   li.innerHTML='<span class=nm>'+esc(file.name)+'</span><span class=st>✗ '+esc(j.error||('error '+xhr.status))+'</span><button class=x>✕</button>';
   li.querySelector('.x').onclick=()=>li.remove();}};
 xhr.onerror=()=>{li.className='frow err';st.textContent='✗ network error';};
 xhr.send(fd);
}
uz.onclick=()=>ufile.click();
ufile.onchange=()=>{[...ufile.files].forEach(uploadOne);ufile.value='';};
uz.ondragover=e=>{e.preventDefault();uz.classList.add('drag');};
uz.ondragleave=()=>uz.classList.remove('drag');
uz.ondrop=e=>{e.preventDefault();uz.classList.remove('drag');[...e.dataTransfer.files].forEach(uploadOne);};

async function loadRegions(){
 try{const r=await fetch('/api/calc_regions');const regs=(await r.json()).regions||[];
  const tr=document.getElementById('trsel'),dr=document.getElementById('drsel');
  regs.forEach(x=>{tr.appendChild(new Option(x,x));dr.appendChild(new Option(x,x));});
  tr.value='swedencentral';
 }catch(e){}
}

document.getElementById('neweng').onclick=()=>{engform.hidden=!engform.hidden;};
document.getElementById('engcancel').onclick=()=>{engform.hidden=true;};
document.getElementById('ef').onsubmit=async ev=>{
 ev.preventDefault();
 const fd=Object.fromEntries(new FormData(ev.target).entries());
 const btn=ev.target.querySelector('button[type=submit]');btn.disabled=true;btn.textContent='Creating…';
 try{
  const r=await fetch('/api/engagements',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(fd)});
  const j=await r.json();
  if(j.error){alert('Could not create: '+j.error);}
  else{ENG=j.engagement;localStorage.setItem('landfall.eng',ENG);engform.hidden=true;ev.target.reset();
       await loadEngagements();engsel.value=ENG;showUpload();newChat();
       toast('Engagement created — now upload the client inventory below.');}
 }catch(e){alert('Error: '+e);}
 btn.disabled=false;btn.textContent='Create engagement';
};

async function newChat(){
 if(busy)return;
 if(ENG){const [c,p]=ENG.split('/');
  try{await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/chat/new',{method:'POST'});}catch(e){}}
 log.innerHTML='<div id=welcome></div>';renderWelcome();q.value='';q.focus();
}
document.getElementById('newchat').onclick=newChat;

async function ask(v){
 v=(v||'').trim();if(!v||busy)return;
 if(!ENG){
  add('Pick an engagement first (top-left) — or click "+ New engagement" to create one. '
     +'Every question is scoped to a customer / project so the estimate stays that client\\'s.','a');
  engform.hidden=false;return;
 }
 const w=document.getElementById('welcome');if(w)w.remove();
 q.value='';add(v,'u');
 setBusy(true);
 const ph=working();
 try{
  const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({message:v,engagement:ENG})});
  const j=await r.json();
  clearInterval(ph._timer);ph.remove();
  if(j.error){add('Error: '+j.error,'a');}
  else{add(j.answer,'a',j.citations);}
 }catch(err){clearInterval(ph._timer);ph.remove();add('Error: '+err,'a');}
 setBusy(false);
}
document.getElementById('f').onsubmit=e=>{e.preventDefault();ask(q.value);};
loadCards();loadEngagements();loadRegions();q.focus();
</script></body></html>"""
