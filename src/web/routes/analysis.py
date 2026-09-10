"""Landfall analysis helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import json
import web_access
import web_runtime
import web_storage

router = APIRouter()


_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def _analysis_reports(eid: str) -> list[dict]:
    """Read the per-file data-quality reports the ingestion pipeline writes to
    answers/engagements/<eid>/_ingest/<stem>.dq.json (E11.6 / E11.24)."""
    prefix = f"engagements/{eid}/_ingest"
    cc = web_storage._estimate_container()
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
    inv = [f["name"] for f in web_storage._list_files(base) if f["kind"] == "inventory"]
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


@router.get("/api/engagements/{customer}/{project}/analysis")
def engagement_analysis(customer: str, project: str, request: Request):
    """Current data-quality picture for the engagement — what ingestion has loaded so
    far and what it flagged. The page polls this after 'Start analysis'."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, base = eng
    return JSONResponse(_analysis_summary(eid, base))


@router.post("/api/engagements/{customer}/{project}/analyze")
async def engagement_analyze(customer: str, project: str, request: Request):
    """'Start analysis' — force a catch-up ingest of everything in the engagement's
    inventory/ folder (the per-file Event Grid trigger normally does this on upload;
    this covers a dropped event or a file added before the subscription existed), then
    return the data-quality summary. The ingest itself runs through the agent's
    `run_engagement` tool so the web tier needs no Function credentials."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, base = eng

    inv = [f for f in web_storage._list_files(base) if f["kind"] == "inventory"]
    if not inv:
        return JSONResponse({"error": "no inventory files uploaded yet"}, status_code=400)

    triggered = False
    if web_runtime.AGENT_NAME:
        try:
            web_runtime._openai_client().with_options(timeout=180.0).responses.create(
                input=(f"[Active engagement: {eid}. Use exactly this value.]\n\n"
                       f"Call run_engagement for this engagement now. Reply with only the "
                       f"raw JSON it returns — no commentary, do not call any other tool."),
                extra_body={"agent_reference": {"type": "agent_reference", "name": web_runtime.AGENT_NAME}},
            )
            triggered = True
        except Exception:  # noqa: BLE001
            web_runtime.log.exception("analyze: run_engagement via agent failed for %s", eid)

    result = _analysis_summary(eid, base)
    result["triggered"] = triggered
    return JSONResponse(result)


@router.get("/api/engagements/{customer}/{project}/pipeline")
def engagement_pipeline(customer: str, project: str, request: Request):
    """E13.2 / E12.8 — the four-step engagement pipeline state for the status strip:
    Inventory -> Analysis -> Estimate -> Calculator POE. Aggregated from the same
    blob + report reads the individual routes use; each step also carries what it
    is waiting on so the UI can nudge without blocking."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, base = eng

    files = web_storage._list_files(base)
    inv_n = sum(1 for f in files if f["kind"] == "inventory")
    has_inv = inv_n > 0

    an = _analysis_summary(eid, base)["summary"]
    analysed = (an.get("files_ingested") or 0) > 0 and (an.get("rows_loaded") or 0) > 0

    estimate = web_storage._read_estimate_blob("latest.json", eid) is not None

    lz = web_storage._read_estimate_blob("landing_zone.json", eid)
    poe_status = None
    if lz:
        try:
            poe_status = (json.loads(lz).get("status") or "ready")
        except Exception:  # noqa: BLE001
            poe_status = "ready"
    poe = poe_status == "ready"

    steps = [
        {"key": "uploads", "label": "Inventory", "done": has_inv,
         "detail": (f"{inv_n} file{'s' if inv_n != 1 else ''}" if has_inv else "none yet")},
        {"key": "analysis", "label": "Analysis", "done": analysed,
         "detail": (f"{an['rows_loaded']} rows · {an.get('confidence') or '—'} confidence"
                    if analysed else ("pending" if has_inv else "—")),
         "waiting_on": None if has_inv else "uploads"},
        {"key": "estimate", "label": "Estimate", "done": estimate,
         "detail": "published" if estimate else "not yet",
         "waiting_on": None if analysed else "analysis"},
        {"key": "poe", "label": "Calculator POE", "done": poe,
         "detail": (poe_status or "not yet") if lz else "not yet",
         "waiting_on": None if estimate else "estimate"},
    ]
    return JSONResponse({
        "engagement": eid,
        "steps": steps,
        "next": next((s["key"] for s in steps if not s["done"]), None),
        "analysed": analysed,
    })
