"""Landfall questionnaire helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
import discovery as _disc
import json
import web_access
import web_runtime
import web_storage

router = APIRouter()


@router.get("/questionnaire", response_class=HTMLResponse)
def questionnaire_page():
    """The discovery questionnaire (E11.25) — a pre-sales architect sends the client
    this URL, or exports the Word/Excel version to fill offline."""
    try:
        return (web_runtime._HERE / "questionnaire.html").read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return HTMLResponse("<h1>Discovery questionnaire</h1><p>Template unavailable — "
                            "download it as <a href='/questionnaire.xlsx'>Excel</a> or "
                            "<a href='/questionnaire.docx'>Word</a>.</p>")


@router.get("/questionnaire.{fmt}")
def questionnaire_export(fmt: str, request: Request, e: str | None = None):
    """Blank questionnaire as .xlsx / .docx, or pre-filled with `?e=<engagement>`'s
    saved answers so a partly-done questionnaire can be topped up."""
    fmt = fmt.lower()
    if fmt not in ("xlsx", "docx"):
        return JSONResponse({"error": "format must be xlsx or docx"}, status_code=400)
    answers = None
    if e:
        if (g := web_access._guard_eid(request, e)):
            return g
        try:
            rec = json.loads(web_storage._raw_container().download_blob(
                f"engagements/{e.strip().strip('/')}/_discovery.json").readall())
            answers = rec.get("answer_map") or {}
        except Exception:  # noqa: BLE001
            answers = None
    blob = _disc.render_xlsx(answers) if fmt == "xlsx" else _disc.render_docx(answers)
    return Response(blob, media_type=web_runtime._EXPORT_MIME[fmt], headers={
        "Content-Disposition": f'attachment; filename="landfall-discovery-questionnaire.{fmt}"'})


@router.get("/api/engagements/{customer}/{project}/discovery")
def engagement_discovery(customer: str, project: str, request: Request):
    """The engagement's saved discovery answers + the 'ask the client' gap list (E11.25)."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    try:
        rec = json.loads(web_storage._raw_container().download_blob(
            f"engagements/{eid}/_discovery.json").readall())
    except Exception:  # noqa: BLE001
        return JSONResponse({"engagement": eid, "imported": False,
                             "gaps": _disc.gaps({}), "answers": {}})
    return JSONResponse({"engagement": eid, "imported": True,
                         "imported_from": rec.get("imported_from"),
                         "imported_at": rec.get("imported_at"),
                         "answers": rec.get("answers") or {},
                         "gaps": rec.get("gaps") or _disc.gaps(rec.get("answer_map") or {})})
