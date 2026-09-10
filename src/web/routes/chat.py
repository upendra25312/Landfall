"""Landfall chat helpers and HTTP routes.

Extracted in C52; HTTP contracts and behavior are preserved.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
import chat_state
import telemetry as _obs
import time as _time
import web_access
import web_runtime

router = APIRouter()


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


@router.post("/api/chat")
async def chat(req: Request):
    _t0 = _time.monotonic()
    body = await req.json()
    question = (body.get("message") or "").strip()
    engagement = (body.get("engagement") or "").strip().strip("/")

    def _ms() -> int:
        return round((_time.monotonic() - _t0) * 1000)

    if not question:
        return JSONResponse({"error": "empty message"}, status_code=400)
    if not web_runtime.AGENT_NAME:
        _obs.event("web_chat", status="agent_unconfigured", ms=_ms())
        return JSONResponse({"error": "AGENT_ID not set - run the postprovision hook"}, status_code=503)

    actor = web_access._principal(req)[0] or "anonymous"
    _eh = _obs.eng_hash(engagement)

    # E8.6 — a conversation can only be resumed through the engagement's server-side
    # pointer, and only after the caller's visibility has been checked. The engagement
    # id in the body is access-controlled here (404 if the caller can't see it); a
    # client-supplied thread_id is never honoured, so a leaked response id is inert.
    if engagement:
        _parts = engagement.split("/")
        _eng = web_access._engagement(_parts[0], _parts[-1], req) if len(_parts) == 2 else None
        if not _eng:
            _obs.event("web_chat", engagement=_eh, status="unknown_engagement", ms=_ms())
            return JSONResponse({"error": "unknown engagement"}, status_code=404)
        engagement = _eng[0]
    chat_doc = chat_state._load_chat(engagement) if engagement else {}
    prev_id = chat_doc.get("current_response_id") if engagement else None

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
                "agent_reference": {"type": "agent_reference", "name": web_runtime.AGENT_NAME}
            },
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
        resp = web_runtime._openai_client().responses.create(**kwargs)
        text = (resp.output_text or "").strip()
        if not text:
            _obs.event("web_chat", engagement=_eh, status="empty_agent_response",
                       agent_status=getattr(resp, "status", None), ms=_ms())
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
            ts = web_runtime._now()
            chat_doc.setdefault("turns", []).append(
                {"role": "user", "text": question, "ts": ts, "actor": actor})
            chat_doc["last_actor"] = actor
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
                chat_state._save_chat(engagement, chat_doc)
            except Exception:  # noqa: BLE001
                web_runtime.log.exception("could not persist the conversation for %s", engagement)
        _obs.event("web_chat", engagement=_eh, status="ok", scoped=bool(engagement),
                   cited=len(cites), tables=len(tables), chars=len(text), ms=_ms())
        return {"answer": text, "citations": cites, "thread_id": resp.id,
                "tables": tables, "sql": last_sql}
    except Exception as exc:  # noqa: BLE001
        web_runtime.log.exception("chat failed")
        _obs.event("web_chat", engagement=_eh, status="error",
                   error=type(exc).__name__, ms=_ms())
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/engagements/{customer}/{project}/chat")
def engagement_chat_get(customer: str, project: str, request: Request):
    """The saved conversation for this engagement (E11.26) — the page renders it on
    load / engagement switch so nothing is lost on a browser close."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    c = chat_state._load_chat(eid)
    return JSONResponse({"engagement": eid, "turns": c.get("turns", []),
                         "current_response_id": c.get("current_response_id"),
                         "archived": c.get("archived", [])})


@router.post("/api/engagements/{customer}/{project}/chat/new")
def engagement_chat_new(customer: str, project: str, request: Request):
    """Start a fresh thread for this engagement — the previous one is archived, not
    destroyed (its Foundry response chain stays retrievable)."""
    eng = web_access._engagement(customer, project, request)
    if not eng:
        return JSONResponse({"error": "unknown engagement"}, status_code=404)
    eid, _ = eng
    c = chat_state._load_chat(eid)
    if c.get("turns"):
        c.setdefault("archived", []).append({
            "started_at": c.get("started_at"), "ended_at": web_runtime._now(),
            "last_response_id": c.get("current_response_id"), "turns": len(c["turns"])})
    c.update({"turns": [], "current_response_id": None, "started_at": web_runtime._now(),
              "engagement": eid, "last_actor": web_access._principal(request)[0] or "anonymous"})
    try:
        chat_state._save_chat(eid, c)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"engagement": eid, "cleared": True, "archived": len(c["archived"])})


@router.post("/api/answer_to_xlsx")
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
        web_runtime.log.exception("answer_to_xlsx failed")
        return JSONResponse({"error": f"could not build the workbook: {exc}"}, status_code=500)
    stem = (engagement or "landfall").replace("/", "-")
    return Response(blob, media_type=web_runtime._EXPORT_MIME["xlsx"], headers={
        "Content-Disposition": f'attachment; filename="{stem}-answer.xlsx"'})
