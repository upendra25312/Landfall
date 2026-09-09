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

import access as _acl
import discovery as _disc
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
            data = _estimate_container().download_blob(f"{prefix}/{name}").readall()
        except Exception:  # noqa: BLE001 - missing blob -> try the next location
            continue
        if prefix == "estimate":  # pre-E11 flat path — one-release back-compat shim
            logging.warning("serving %s from the legacy flat estimate/ path — run "
                            "scripts/migrate_to_default_engagement.py --apply", name)
        return data
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
        try:
            from answer_xlsx import tables_from_response
            tables, last_sql = tables_from_response(resp)
        except Exception:  # noqa: BLE001
            tables, last_sql = [], None
        if engagement:
            ts = _now()
            chat_doc.setdefault("turns", []).append({"role": "user", "text": question, "ts": ts})
            a_turn = {"role": "assistant", "text": text, "ts": ts, "citations": cites}
            if tables:
                a_turn["tables"] = tables
            if last_sql:
                a_turn["sql"] = last_sql
            chat_doc["turns"].append(a_turn)
            chat_doc["current_response_id"] = resp.id
            chat_doc["engagement"] = engagement
            chat_doc.setdefault("started_at", ts)
            try:
                _save_chat(engagement, chat_doc)
            except Exception:  # noqa: BLE001
                logging.exception("could not persist the conversation for %s", engagement)
        return {"answer": text, "citations": cites, "thread_id": resp.id,
                "tables": tables, "sql": last_sql}
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
    return _acl.principal(request.headers)[0] or "anonymous"


def _principal(request: Request) -> tuple[str | None, list[str]]:
    return _acl.principal(request.headers)


@app.get("/api/engagements")
def engagements_list(request: Request):
    """List engagements from blob (`raw/engagements/<c>/<p>/_engagement.json`), filtered
    by the caller's visibility (E11.6). The chat page uses this for its engagement picker
    so the user never types the `<customer>/<project>` id."""
    me, groups = _principal(request)
    me = me or "anonymous"
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
            if not _acl.can_view(m, None if me == "anonymous" else me, groups):
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
        "notes": body.get("notes") or "",
        "visibility": _acl.normalize_visibility(body.get("visibility")), "status": "new",
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
        raw = _raw_container().download_blob(f"engagements/{eid}/_engagement.json").readall()
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
def engagement_files(customer: str, project: str, request: Request):
    """Manifest of what's been uploaded for this engagement (E11.24)."""
    eng = _engagement(customer, project, request)
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
    eng = _engagement(customer, project, request)
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
                                             _principal_name(request))
                _raw_container().upload_blob(f"{base}/_discovery.json",
                                             json.dumps(rec, indent=2).encode(), overwrite=True)
                resp["discovery"] = {"answered": len(parsed["answers"]),
                                     "matched": parsed["matched"],
                                     "gaps": rec["gaps"]["headline"]}
            elif parsed["format"] == "pdf":
                resp["discovery_note"] = ("PDF questionnaires aren't parsed — re-export "
                                          "the answers as .xlsx or .docx to feed the estimate")
        except Exception as exc:  # noqa: BLE001
            logging.warning("discovery import skipped for %s: %s", name, exc)

    return JSONResponse(resp, status_code=201)


@app.delete("/api/engagements/{customer}/{project}/files/{name}")
def engagement_file_delete(customer: str, project: str, name: str, request: Request):
    eng = _engagement(customer, project, request)
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


_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def _analysis_reports(eid: str) -> list[dict]:
    """Read the per-file data-quality reports the ingestion pipeline writes to
    answers/engagements/<eid>/_ingest/<stem>.dq.json (E11.6 / E11.24)."""
    prefix = f"engagements/{eid}/_ingest"
    cc = _estimate_container()
    out = []
    try:
        names = [b.name for b in cc.list_blobs(name_starts_with=f"{prefix}/")
                 if b.name.endswith(".dq.json")]
    except Exception:  # noqa: BLE001
        return out
    for n in names:
        try:
            doc = json.loads(cc.download_blob(n).readall())
        except Exception:  # noqa: BLE001
            continue
        s = doc.get("summary") or {}
        out.append({
            "file": s.get("file") or n.rsplit("/", 1)[-1].replace(".dq.json", ""),
            "table": s.get("table"),
            "profile": s.get("profile") or "",
            "status": s.get("status") or "ok",
            "rows_in": s.get("rows_in") or 0,
            "rows_loaded": s.get("rows_loaded") or 0,
            "rows_rejected": s.get("rows_rejected") or 0,
            "confidence": s.get("confidence_hint") or "",
            "findings": s.get("findings") or [],
        })
    out.sort(key=lambda r: r["file"])
    return out


def _analysis_summary(eid: str, base: str) -> dict:
    reports = _analysis_reports(eid)
    inv = [f["name"] for f in _list_files(base) if f["kind"] == "inventory"]
    have = {r["file"] for r in reports}
    tables, rows_loaded, findings = {}, 0, []
    worst = None
    for r in reports:
        if r["table"]:
            tables[r["table"]] = tables.get(r["table"], 0) + r["rows_loaded"]
        rows_loaded += r["rows_loaded"]
        for f in r["findings"]:
            if f not in findings:
                findings.append(f)
        c = _CONF_RANK.get((r["confidence"] or "").lower())
        if c is not None:
            worst = c if worst is None else min(worst, c)
    conf = {0: "Low", 1: "Medium", 2: "High"}.get(worst, "")
    return {
        "engagement": eid,
        "reports": reports,
        "summary": {
            "files_ingested": len(reports),
            "rows_loaded": rows_loaded,
            "tables": tables,
            "confidence": conf,
            "findings": findings,
            "pending": [f for f in inv if f not in have],
        },
    }


@app.get("/api/engagements/{customer}/{project}/analysis")
def engagement_analysis(customer: str, project: str, request: Request):
    """Current data-quality picture for the engagement — what ingestion has loaded so
    far and what it flagged. The page polls this after 'Start analysis'."""
    eng = _engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, base = eng
    return JSONResponse(_analysis_summary(eid, base))


@app.post("/api/engagements/{customer}/{project}/analyze")
async def engagement_analyze(customer: str, project: str, request: Request):
    """'Start analysis' — force a catch-up ingest of everything in the engagement's
    inventory/ folder (the per-file Event Grid trigger normally does this on upload;
    this covers a dropped event or a file added before the subscription existed), then
    return the data-quality summary. The ingest itself runs through the agent's
    `run_engagement` tool so the web tier needs no Function credentials."""
    eng = _engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, base = eng

    inv = [f for f in _list_files(base) if f["kind"] == "inventory"]
    if not inv:
        return JSONResponse({"error": "no inventory files uploaded yet"}, status_code=400)

    triggered = False
    if AGENT_NAME:
        try:
            _openai_client().with_options(timeout=180.0).responses.create(
                input=(f"[Active engagement: {eid}. Use exactly this value.]\n\n"
                       f"Call run_engagement for this engagement now. Reply with only the "
                       f"raw JSON it returns — no commentary, do not call any other tool."),
                extra_body={"agent_reference": {"type": "agent_reference", "name": AGENT_NAME}},
            )
            triggered = True
        except Exception:  # noqa: BLE001
            logging.exception("analyze: run_engagement via agent failed for %s", eid)

    result = _analysis_summary(eid, base)
    result["triggered"] = triggered
    return JSONResponse(result)


@app.get("/api/engagements/{customer}/{project}/history")
def engagement_history(customer: str, project: str, request: Request):
    """Published-estimate version history (E11.8). Each re-publish snapshots the
    version it replaces into answers/engagements/<eid>/history/<ts>/."""
    eng = _engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    cc = _estimate_container()
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


@app.get("/api/engagements/{customer}/{project}/chat")
def engagement_chat_get(customer: str, project: str, request: Request):
    """The saved conversation for this engagement (E11.26) — the page renders it on
    load / engagement switch so nothing is lost on a browser close."""
    eng = _engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    c = _load_chat(eid)
    return JSONResponse({"engagement": eid, "turns": c.get("turns", []),
                         "current_response_id": c.get("current_response_id"),
                         "archived": c.get("archived", [])})


@app.post("/api/engagements/{customer}/{project}/chat/new")
def engagement_chat_new(customer: str, project: str, request: Request):
    """Start a fresh thread for this engagement — the previous one is archived, not
    destroyed (its Foundry response chain stays retrievable)."""
    eng = _engagement(customer, project, request)
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
def engagement_export(customer: str, project: str, request: Request):
    """One .zip with the engagement manifest + every uploaded file + every produced
    artifact + the conversation — so an engagement is portable across `azd down` /
    `azd up` or between deployments (E11.26)."""
    eng = _engagement(customer, project, request)
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


@app.get("/questionnaire", response_class=HTMLResponse)
def questionnaire_page():
    """The discovery questionnaire (E11.25) — a pre-sales architect sends the client
    this URL, or exports the Word/Excel version to fill offline."""
    try:
        return (_HERE / "questionnaire.html").read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return HTMLResponse("<h1>Discovery questionnaire</h1><p>Template unavailable — "
                            "download it as <a href='/questionnaire.xlsx'>Excel</a> or "
                            "<a href='/questionnaire.docx'>Word</a>.</p>")


@app.get("/questionnaire.{fmt}")
def questionnaire_export(fmt: str, request: Request, e: str | None = None):
    """Blank questionnaire as .xlsx / .docx, or pre-filled with `?e=<engagement>`'s
    saved answers so a partly-done questionnaire can be topped up."""
    fmt = fmt.lower()
    if fmt not in ("xlsx", "docx"):
        return JSONResponse({"error": "format must be xlsx or docx"}, status_code=400)
    answers = None
    if e:
        if (g := _guard_eid(request, e)):
            return g
        try:
            rec = json.loads(_raw_container().download_blob(
                f"engagements/{e.strip().strip('/')}/_discovery.json").readall())
            answers = rec.get("answer_map") or {}
        except Exception:  # noqa: BLE001
            answers = None
    blob = _disc.render_xlsx(answers) if fmt == "xlsx" else _disc.render_docx(answers)
    return Response(blob, media_type=_EXPORT_MIME[fmt], headers={
        "Content-Disposition": f'attachment; filename="landfall-discovery-questionnaire.{fmt}"'})


@app.get("/api/engagements/{customer}/{project}/discovery")
def engagement_discovery(customer: str, project: str, request: Request):
    """The engagement's saved discovery answers + the 'ask the client' gap list (E11.25)."""
    eng = _engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    try:
        rec = json.loads(_raw_container().download_blob(
            f"engagements/{eid}/_discovery.json").readall())
    except Exception:  # noqa: BLE001
        return JSONResponse({"engagement": eid, "imported": False,
                             "gaps": _disc.gaps({}), "answers": {}})
    return JSONResponse({"engagement": eid, "imported": True,
                         "imported_from": rec.get("imported_from"),
                         "imported_at": rec.get("imported_at"),
                         "answers": rec.get("answers") or {},
                         "gaps": rec.get("gaps") or _disc.gaps(rec.get("answer_map") or {})})


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


@app.post("/api/answer_to_xlsx")
async def answer_to_xlsx(req: Request):
    """E11.14 — download a chat answer (+ any tabular tool output it carried) as an
    Excel workbook: an Answer sheet, a sheet per table, and a Provenance sheet."""
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001
        body = {}
    question = (body.get("question") or "").strip()
    answer = (body.get("answer") or "").strip()
    if not answer:
        return JSONResponse({"error": "nothing to export — 'answer' is required"}, status_code=400)
    engagement = (body.get("engagement") or "").strip().strip("/") or None
    tables = body.get("tables") if isinstance(body.get("tables"), list) else []
    try:
        from answer_xlsx import build_answer_workbook
        blob = build_answer_workbook(engagement, question, answer, tables, body.get("sql"))
    except Exception as exc:  # noqa: BLE001
        logging.exception("answer_to_xlsx failed")
        return JSONResponse({"error": f"could not build the workbook: {exc}"}, status_code=500)
    stem = (engagement or "landfall").replace("/", "-")
    return Response(blob, media_type=_EXPORT_MIME["xlsx"], headers={
        "Content-Disposition": f'attachment; filename="{stem}-answer.xlsx"'})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """The assessment dashboard — an Azure Migrate–style read of the published estimate."""
    return (_HERE / "dashboard.html").read_text(encoding="utf-8")


def _snapshot_blob(name: str, engagement: str | None, snapshot: str | None) -> bytes | None:
    """Read `name` from a history/<snapshot>/ folder, or the live latest.* if no
    snapshot is given (E11.8)."""
    if not snapshot:
        return _read_estimate_blob(name, engagement)
    eid = (engagement or "").strip().strip("/")
    stamp = "".join(ch for ch in snapshot if ch.isalnum() or ch == "Z")
    if not eid or not stamp:
        return None
    try:
        return _estimate_container().download_blob(
            f"engagements/{eid}/history/{stamp}/{name}").readall()
    except Exception:  # noqa: BLE001
        return None


def _guard_eid(request: Request, e: str | None):
    """403 (as JSONResponse) if the caller can't see engagement `e`; None if OK or
    `e` is unset/default. For the dashboard routes, which key off `?e=` not a path."""
    eid = (e or "").strip().strip("/")
    if not eid or eid == "_default_/_default_":
        return None
    try:
        m = json.loads(_raw_container().download_blob(
            f"engagements/{eid}/_engagement.json").readall())
    except Exception:  # noqa: BLE001
        return None  # unknown engagement -> let the downstream 404 handle it
    name, groups = _principal(request)
    if _acl.can_view(m, name, groups):
        return None
    return JSONResponse({"error": "not visible to you"}, status_code=403)


@app.get("/api/engagements/{customer}/{project}/audit")
def engagement_audit(customer: str, project: str, request: Request):
    """The engagement's audit trail (E11.10): creation + every run_engagement /
    publish_estimate / calc run, newest first."""
    eng = _engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    key = f"engagements/{eid}/_audit.jsonl"
    entries: list[dict] = []
    try:
        raw = _estimate_container().download_blob(key).readall()
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


@app.get("/dashboard/data")
def dashboard_data(request: Request, e: str | None = None, snapshot: str | None = None):
    if (g := _guard_eid(request, e)):
        return g
    blob = _snapshot_blob("latest.json", e, snapshot)
    if blob is None:
        return JSONResponse({"error": "no estimate published"}, status_code=404)
    return JSONResponse(json.loads(blob))


@app.get("/dashboard/download/{fmt}")
def dashboard_download(fmt: str, request: Request, e: str | None = None,
                       snapshot: str | None = None):
    if (g := _guard_eid(request, e)):
        return g
    fmt = fmt.lower().lstrip(".")
    if fmt not in _EXPORT_MIME:
        return JSONResponse({"error": "format must be xlsx | docx | pptx"}, status_code=400)
    blob = _snapshot_blob(f"latest.{fmt}", e, snapshot)
    if blob is None:
        return JSONResponse({"error": f"no {fmt} export published"}, status_code=404)
    name = (e or "landfall-estimate").replace("/", "-")
    return Response(blob, media_type=_EXPORT_MIME[fmt], headers={
        "Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


@app.get("/dashboard/landing-zone")
def landing_zone_data(request: Request, e: str | None = None):
    """The Azure Pricing Calculator POE summary (landing_zone.json) for an engagement."""
    if (g := _guard_eid(request, e)):
        return g
    blob = _read_estimate_blob("landing_zone.json", e)
    if blob is None:
        return JSONResponse({"error": "no Pricing Calculator estimate built yet"}, status_code=404)
    return JSONResponse(json.loads(blob))


@app.get("/dashboard/download/landing-zone-xlsx")
def landing_zone_xlsx(request: Request, e: str | None = None):
    """Stream the Azure Pricing Calculator's own Excel export — the POE artifact."""
    if (g := _guard_eid(request, e)):
        return g
    blob = _read_estimate_blob("landing_zone.xlsx", e)
    if blob is None:
        return JSONResponse({"error": "no Pricing Calculator estimate built yet"}, status_code=404)
    name = (e or "landfall").replace("/", "-") + "-landing-zone-POE"
    return Response(blob, media_type=_EXPORT_MIME["xlsx"], headers={
        "Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@app.get("/dashboard/landing-zone-diagram")
def landing_zone_diagram(request: Request, e: str | None = None,
                         fmt: str = "svg", download: int = 0):
    """The engagement's target landing-zone diagram (E11.22). `fmt=svg` (default) is
    the self-contained SVG the dashboard renders inline; `fmt=drawio` is the editable
    source; `?download=1` sends it as a file."""
    if (g := _guard_eid(request, e)):
        return g
    fmt = fmt.lower()
    if fmt == "drawio":
        blob = _read_estimate_blob("landing_zone.drawio", e)
        mime, ext = "application/xml", "drawio"
    elif fmt == "png":
        blob = _read_estimate_blob("landing_zone.png", e)
        mime, ext = "image/png", "png"
    else:
        blob = _read_estimate_blob("landing_zone.svg", e) or _read_estimate_blob("landing_zone.drawio", e)
        mime, ext = ("image/svg+xml", "svg") if (blob and blob.lstrip().startswith(b"<svg")) \
            else ("application/xml", "drawio")
    if blob is None:
        return JSONResponse({"error": "no landing-zone diagram built yet"}, status_code=404)
    if download:
        name = (e or "landfall").replace("/", "-") + "-landing-zone"
        return Response(blob, media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="{name}.{ext}"'})
    return Response(blob, media_type=mime)


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
 .frow .badge{font-size:11px;padding:2px 7px;border-radius:20px;white-space:nowrap;flex:none}
 .badge.ing{background:#12313f;color:#7fd3dd}.badge.rej{background:#3a2118;color:#f0a35e}.badge.wait{background:#1c2732;color:var(--muted)}
 #analysisbar{margin-top:12px;display:flex;align-items:center;gap:12px}
 #analysisbar .st{font-size:12px}
 #dqsummary{margin-top:12px;border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:12px 14px;font-size:13px}
 #dqsummary h4{margin:0 0 6px;font-size:13px}
 #dqsummary .conf{font-weight:600}
 #dqsummary .conf.High{color:#6fce9a}#dqsummary .conf.Medium{color:#e8c37a}#dqsummary .conf.Low{color:#f0a35e}
 #dqsummary ul{margin:8px 0 0;padding-left:18px;color:var(--muted)}
 #dqsummary ul li{margin:3px 0}
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
 <a href="/dashboard" id=dashlink>Assessment dashboard &rarr;</a>
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
 <div id=analysisbar hidden>
  <button class=send id=startanalysis type=button>Start analysis</button>
  <span class=st id=analysisnote></span>
 </div>
 <div id=dqsummary hidden></div>
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

function add(t,cls,cites,extra){
 const d=document.createElement('div');d.className='m '+cls;d.textContent=t;
 if(cites&&cites.length){const c=document.createElement('div');c.className='c';c.textContent='Sources: '+cites.join(', ');d.appendChild(c);}
 if(cls==='a'&&t&&(extra&&(extra.tables&&extra.tables.length))){
  const b=document.createElement('button');b.className='link';b.style.marginTop='6px';
  b.textContent='⭳ Download as Excel';
  b.onclick=()=>xlsxFromAnswer(extra.question||'',t,extra.tables||[],extra.sql||'');
  d.appendChild(b);
 }
 log.appendChild(d);d.scrollIntoView({block:'end'});return d;
}
async function xlsxFromAnswer(question,answer,tables,sql){
 try{
  const r=await fetch('/api/answer_to_xlsx',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({engagement:ENG,question:question,answer:answer,tables:tables,sql:sql})});
  if(!r.ok){toast('Excel export failed');return;}
  const blob=await r.blob(),u=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=u;a.download=(ENG||'landfall').replace('/','-')+'-answer.xlsx';a.click();
  setTimeout(()=>URL.revokeObjectURL(u),4000);
 }catch(e){toast('Excel export failed');}
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
 renderWelcome();showUpload();loadChat();syncDashLink();
}
function syncDashLink(){const a=document.getElementById('dashlink');
 if(a)a.href=ENG?('/dashboard?e='+encodeURIComponent(ENG)):'/dashboard';}
engsel.onchange=()=>{ENG=engsel.value;localStorage.setItem('landfall.eng',ENG);
 document.getElementById('expeng').hidden=!ENG;renderWelcome();showUpload();loadChat();syncDashLink();};

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
 turns.forEach((t,i)=>add(t.text,t.role==='user'?'u':'a',t.citations,
   t.role==='assistant'?{tables:t.tables,sql:t.sql,question:(turns[i-1]||{}).text||''}:null));
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
let ANALYSIS={};   // file name -> ingest report
const abar=document.getElementById('analysisbar'),anote=document.getElementById('analysisnote'),
      startBtn=document.getElementById('startanalysis'),dqEl=document.getElementById('dqsummary');
async function loadFiles(){
 frows.innerHTML='';dqEl.hidden=true;abar.hidden=true;if(!ENG)return;
 const [c,p]=ENG.split('/');
 let hasInv=false;
 try{
  const j=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files')).json();
  try{const a=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/analysis')).json();
      ANALYSIS={};(a.reports||[]).forEach(r=>ANALYSIS[r.file]=r);
      if((a.summary||{}).files_ingested)renderDQ(a.summary);}catch(e){}
  (j.files||[]).forEach(f=>{if(f.kind==='inventory')hasInv=true;frows.appendChild(doneRow(f));});
  if(j.over_soft_cap)toast('This engagement is over the 2 GB soft cap.');
 }catch(e){}
 abar.hidden=!hasInv;
}
function delFile(nm){
 return async()=>{if(!confirm('Remove '+nm+'?'))return;const [c,p]=ENG.split('/');
  await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files/'+enc(nm),{method:'DELETE'});loadFiles();};
}
function ingestBadge(f){
 if(f.kind!=='inventory')return '';
 const r=ANALYSIS[f.name];
 if(!r)return '<span class="badge wait">not analysed</span>';
 if(r.status&&r.status!=='ok'&&r.status!=='rejected')return '<span class="badge rej">'+esc(r.status)+'</span>';
 let b='<span class="badge ing">✓ '+(r.rows_loaded||0)+' rows'+(r.table?(' → '+esc(r.table)):'')+'</span>';
 if(r.rows_rejected)b+=' <span class="badge rej">'+r.rows_rejected+' rejected</span>';
 return b;
}
function doneRow(f){
 const li=document.createElement('li');li.className='frow ok';
 const prof=f.profile?(' · '+esc(f.profile)):'',rows=f.rows?(' · '+f.rows+' rows'):'';
 li.innerHTML='<span class=nm>'+esc(f.name)+'</span>'+ingestBadge(f)+
   '<span class=st>✓ '+esc(f.kind)+prof+rows+' · '+fmtSize(f.size)+'</span><button class=x title=Remove>✕</button>';
 li.querySelector('.x').onclick=delFile(f.name);return li;
}
function renderDQ(s){
 if(!s||!s.files_ingested){dqEl.hidden=true;return;}
 const tbl=Object.entries(s.tables||{}).map(([t,n])=>esc(t)+' ('+n+')').join(', ');
 let h='<h4>Data-quality summary</h4>';
 h+='<div>'+s.files_ingested+' file'+(s.files_ingested===1?'':'s')+' loaded · '+
    s.rows_loaded+' rows'+(tbl?(' · '+tbl):'')+
    (s.confidence?(' · confidence <span class="conf '+esc(s.confidence)+'">'+esc(s.confidence)+'</span>'):'')+'</div>';
 if((s.pending||[]).length)h+='<div class=warn>still ingesting: '+s.pending.map(esc).join(', ')+'</div>';
 if((s.findings||[]).length)h+='<ul>'+s.findings.map(f=>'<li>'+esc(f)+'</li>').join('')+'</ul>';
 dqEl.innerHTML=h;dqEl.hidden=false;
}
async function startAnalysis(){
 if(!ENG)return;const [c,p]=ENG.split('/');
 startBtn.disabled=true;anote.textContent='ingesting the uploaded files…';
 try{
  const j=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/analyze',{method:'POST'})).json();
  if(j.error){anote.textContent='✗ '+j.error;startBtn.disabled=false;return;}
  ANALYSIS={};(j.reports||[]).forEach(r=>ANALYSIS[r.file]=r);
  renderDQ(j.summary);await loadFiles();
  let tries=(j.summary&&j.summary.pending||[]).length?8:0;
  while(tries-- > 0){
   await new Promise(r=>setTimeout(r,2500));
   const a=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/analysis')).json();
   ANALYSIS={};(a.reports||[]).forEach(r=>ANALYSIS[r.file]=r);
   renderDQ(a.summary);await refreshRows();
   if(!((a.summary||{}).pending||[]).length)break;
  }
  anote.textContent='';
 }catch(e){anote.textContent='✗ '+e;}
 startBtn.disabled=false;
}
async function refreshRows(){
 if(!ENG)return;const [c,p]=ENG.split('/');
 try{const j=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files')).json();
  frows.innerHTML='';(j.files||[]).forEach(f=>frows.appendChild(doneRow(f)));}catch(e){}
}
startBtn.onclick=startAnalysis;
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
  else{add(j.answer,'a',j.citations,{tables:j.tables,sql:j.sql,question:v});}
 }catch(err){clearInterval(ph._timer);ph.remove();add('Error: '+err,'a');}
 setBusy(false);
}
document.getElementById('f').onsubmit=e=>{e.preventDefault();ask(q.value);};
loadCards();loadEngagements();loadRegions();q.focus();
</script></body></html>"""
