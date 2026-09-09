"""
Discovery questionnaire — serve, export, re-import (PRD E11.25).

`discovery_catalog.json` (generated from docs/discovery-questionnaire.html by
scripts/gen_discovery_catalog.py) is the question set. This module:

  * renders a blank / pre-filled questionnaire to .xlsx and .docx
  * parses a returned .xlsx / .docx back into {question_id: answer}
  * lists the unanswered MUST / SHOULD questions (the "ask the client" gaps)

The structured answers land at raw/engagements/<c>/<p>/_discovery.json and feed
`assemble_estimate` (cited assumptions) + `design_landing_zone` (compliance / DR).
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import pathlib
import re

_HERE = pathlib.Path(__file__).parent
_CATALOG_PATH = _HERE / "discovery_catalog.json"
_QID = re.compile(r"^([A-Z]{1,3}[0-9]{1,3})\b")
_MIN_MATCH = 3          # a doc must hit at least this many question ids to count as the template


def load_catalog() -> list[dict]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def _by_section(cat: list[dict]) -> list[tuple[str, list[dict]]]:
    out: list[tuple[str, list[dict]]] = []
    for q in cat:
        if not out or out[-1][0] != q["section"]:
            out.append((q["section"], []))
        out[-1][1].append(q)
    return out


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------- export

def render_xlsx(answers: dict | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    answers = answers or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "Discovery"
    ws.append(["Landfall — Azure migration discovery questionnaire"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Fill the Answer column and send this file back. Do not change the ID column."])
    ws.append([])
    ws.append(["ID", "Section", "Priority", "Question", "Answer"])
    for c in ws[4]:
        c.font = Font(bold=True)
    for q in load_catalog():
        ws.append([q["id"], q["section"], q["priority"], q["text"],
                   str(answers.get(q["id"], ""))])
    widths = [8, 26, 9, 82, 46]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    for row in ws.iter_rows(min_row=5):
        row[3].alignment = Alignment(wrap_text=True, vertical="top")
        row[4].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A5"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_docx(answers: dict | None = None) -> bytes:
    from docx import Document
    from docx.shared import Inches, Pt

    answers = answers or {}
    doc = Document()
    for sec in doc.sections:
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
        sec.left_margin = sec.right_margin = Inches(1)
    doc.add_heading("Landfall — Azure migration discovery questionnaire", level=0)
    doc.add_paragraph("Answer under each question and send this file back. Keep the "
                      "question codes (e.g. B1, SC1) — the importer matches on them.")
    for section, qs in _by_section(load_catalog()):
        doc.add_heading(section, level=1)
        for q in qs:
            p = doc.add_paragraph()
            p.add_run(f"{q['id']}  ").bold = True
            p.add_run(f"[{q['priority']}]  ").italic = True
            p.add_run(q["text"])
            a = doc.add_paragraph(str(answers.get(q["id"], "")) or "…")
            a.paragraph_format.left_indent = Inches(0.3)
            a.paragraph_format.space_after = Pt(8)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------- import

def _clean(v) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    return "" if s in ("…", "-", "n/a", "N/A", "TBD", "tbd") else s


def parse_upload(data: bytes, filename: str) -> dict:
    """Return {answers, matched, unmatched, format}. `answers` maps a known question
    id to its (non-empty) answer. `matched` < _MIN_MATCH means this file is not the
    questionnaire template."""
    name = (filename or "").lower()
    ids = {q["id"] for q in load_catalog()}
    answers: dict[str, str] = {}
    fmt = "unknown"

    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            fmt = "xlsx"
            answers = _parse_xlsx(data, ids)
        elif name.endswith(".docx"):
            fmt = "docx"
            answers = _parse_docx(data, ids)
        elif name.endswith(".pdf"):
            fmt = "pdf"                          # not parsed — see note in the route
    except Exception:                            # noqa: BLE001
        answers = {}

    matched = sorted(answers)
    unmatched = sorted(ids - set(matched))
    return {"answers": answers, "matched": matched, "unmatched": unmatched,
            "format": fmt, "is_template": len(matched) >= _MIN_MATCH}


def _parse_xlsx(data: bytes, ids: set[str]) -> dict[str, str]:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out: dict[str, str] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            if not row:
                continue
            cells = [c for c in row if c is not None]
            if not cells:
                continue
            head = str(cells[0]).strip()
            if head in ids:
                ans = _clean(row[-1]) if len(row) > 1 else ""
                # last cell must not be the question text itself
                if ans and ans != _clean(cells[1] if len(cells) > 1 else ""):
                    out[head] = ans
                elif ans and len(cells) >= 2 and ans != head:
                    out[head] = ans
    return out


def _parse_docx(data: bytes, ids: set[str]) -> dict[str, str]:
    from docx import Document
    doc = Document(io.BytesIO(data))

    # tables first (an exported .xlsx re-saved as .docx, or a table layout)
    out: dict[str, str] = {}
    for t in doc.tables:
        for r in t.rows:
            cells = [c.text.strip() for c in r.cells]
            if cells and cells[0] in ids and len(cells) > 1:
                ans = _clean(cells[-1])
                if ans and ans != _clean(cells[1]):
                    out[cells[0]] = ans

    # paragraph layout: a "B1  [MUST]  question…" line, then the answer paragraph(s),
    # until the next question line or a section heading.
    rows = [(p.text.strip(), (p.style.name or "") if p.style else "") for p in doc.paragraphs]

    def _is_q(t: str) -> str | None:
        m = _QID.match(t)
        return m.group(1) if m and m.group(1) in ids else None

    for i, (text, _style) in enumerate(rows):
        qid = _is_q(text)
        if not qid or qid in out:
            continue
        parts = []
        for nxt, nstyle in rows[i + 1:]:
            if _is_q(nxt) or nstyle.startswith("Heading") or nstyle.startswith("Title"):
                break
            if nxt and nxt != "…":
                parts.append(nxt)
        ans = _clean(" ".join(parts))
        if ans:
            out[qid] = ans
    return out


# --------------------------------------------------------------------- gaps

def gaps(answers: dict | None) -> dict:
    """The unanswered MUST / SHOULD questions, grouped by section — the dashboard's
    'ask the client' list and the agent's 'What's missing?' answer."""
    answered = {k for k, v in (answers or {}).items() if str(v).strip()}
    cat = load_catalog()
    missing = [q for q in cat if q["priority"] in ("MUST", "SHOULD") and q["id"] not in answered]
    by_section: dict[str, list[dict]] = {}
    for q in missing:
        by_section.setdefault(q["section"], []).append(
            {"id": q["id"], "priority": q["priority"], "question": q["text"]})
    must_total = sum(1 for q in cat if q["priority"] == "MUST")
    must_missing = sum(1 for q in missing if q["priority"] == "MUST")
    return {
        "answered": len(answered),
        "total": len(cat),
        "must_answered": must_total - must_missing,
        "must_total": must_total,
        "missing": [{"section": s, "questions": qs} for s, qs in by_section.items()],
        "headline": f"{len(answered)}/{len(cat)} answered · "
                    f"{must_missing} required question{'s' if must_missing != 1 else ''} still open",
    }


def discovery_record(answers: dict, matched: list[str], filename: str, actor: str) -> dict:
    """The _discovery.json payload."""
    cat = {q["id"]: q for q in load_catalog()}
    return {
        "answers": {qid: {"answer": ans, "question": cat.get(qid, {}).get("text"),
                          "section": cat.get(qid, {}).get("section"),
                          "feeds": cat.get(qid, {}).get("feeds")}
                    for qid, ans in answers.items()},
        "answer_map": answers,
        "matched": matched,
        "imported_from": filename,
        "imported_by": actor,
        "imported_at": _now(),
        "gaps": gaps(answers),
    }
