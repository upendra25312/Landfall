"""
Client-ready exports of an assembled estimate package (PRD E5.4).

    from deliverable.export import export
    blob, filename, mime = export(package, "xlsx")   # or "docx" / "pptx"

xlsx — a workbook: cover, headline figures, a sheet per section, the calculation
       appendix, the register.
docx — a proposal-ready document: title page, headline table, every section,
       the calculation appendix, the register.
pptx — an executive readout: title, headline numbers, one slide per major
       section, assumptions.

Every figure keeps its `F*` reference so the calculation appendix still ties out.
All three carry the package's DRAFT watermark. Pure — the package is the input.
"""
from __future__ import annotations

import io

_ACCENT = "243A5E"        # deep Azure blue
_ACCENT2 = "0E7C8B"
_MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def export(package: dict, fmt: str) -> tuple[bytes, str, str]:
    fmt = (fmt or "").lower().lstrip(".")
    if fmt not in _MIME:
        raise ValueError(f"unknown format {fmt!r} (want xlsx | docx | pptx)")
    pid = (package.get("meta", {}) or {}).get("package_id", "landfall-estimate")
    blob = {"xlsx": to_xlsx, "docx": to_docx, "pptx": to_pptx}[fmt](package)
    return blob, f"{pid}.{fmt}", _MIME[fmt]


def _fmt(v):
    if isinstance(v, bool) or v is None:
        return "" if v is None else str(v)
    if isinstance(v, (int, float)):
        return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"
    return str(v)


def _headline(package: dict) -> list[dict]:
    keys = ("run_rate_monthly", "run_rate_annual", "one_time_cost", "effort_pd", "services_cost")
    return [f for f in package.get("figures", []) if f["key"] in keys]


def _sections(package: dict) -> list[dict]:
    return package.get("sections", [])


# --------------------------------------------------------------------- xlsx

def to_xlsx(package: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    meta = package.get("meta", {})
    wb = Workbook()
    head_fill = PatternFill("solid", fgColor=_ACCENT)
    head_font = Font(bold=True, color="FFFFFF")
    title_font = Font(bold=True, size=14, color=_ACCENT)

    def _sheet(name):
        ws = wb.create_sheet(name[:31])
        return ws

    def _table(ws, start_row, headers, rows):
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=c, value=h)
            cell.fill, cell.font = head_fill, head_font
        for r, row in enumerate(rows, start_row + 1):
            for c, v in enumerate(row, 1):
                ws.cell(row=r, column=c, value=v)
        for c, h in enumerate(headers, 1):
            width = max(len(str(h)), *(len(str(row[c - 1])) for row in rows)) if rows else len(str(h))
            ws.column_dimensions[get_column_letter(c)].width = min(60, width + 3)
        ws.freeze_panes = ws.cell(row=start_row + 1, column=1)

    # cover
    ws = wb.active
    ws.title = "Cover"
    ws["A1"] = f"Migration estimate — {meta.get('package_id', '')}"
    ws["A1"].font = title_font
    for i, (k, v) in enumerate([
        ("Status", meta.get("status")), ("Watermark", meta.get("watermark")),
        ("Region", meta.get("region")), ("Currency", meta.get("currency")),
        ("Prices as of", meta.get("price_date")), ("Overall confidence", meta.get("overall_confidence")),
        ("Generated", meta.get("generated_on")), ("Tools run", ", ".join(meta.get("tools_run") or [])),
        ("Tools failed", ", ".join(meta.get("tools_failed") or []) or "none"),
    ], start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=i, column=2, value=_fmt(v))
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 90

    # headline
    ws = _sheet("Headline")
    _table(ws, 1, ["Figure", "Value", "Unit", "Confidence", "Ref"],
           [[f["label"], f["value"], f["unit"], f["confidence"], f["id"]] for f in _headline(package)])

    # one sheet per section
    for s in _sections(package):
        ws = _sheet(f"{s['id']} {s['title']}")
        ws["A1"] = s["title"]
        ws["A1"].font = title_font
        row = 3
        figs = [f for f in package.get("figures", []) if f["id"] in s["figures"]]
        if figs:
            _table(ws, row, ["Figure", "Value", "Unit", "Ref"],
                   [[f["label"], f["value"], f["unit"], f["id"]] for f in figs])
            row += len(figs) + 3
        for line in _body_lines(s):
            ws.cell(row=row, column=1, value=line)
            row += 1

    # calculation appendix
    ws = _sheet("Calculation appendix")
    _table(ws, 1, ["Ref", "Figure", "Result", "Unit", "Formula", "Inputs", "Assumptions", "Confidence"],
           [[a["figure_id"], a["label"], a["result"], a["unit"], a["formula"],
             _kv(a.get("inputs")), ", ".join(a.get("assumptions_applied") or []) or "—", a["confidence"]]
            for a in package.get("calculation_appendix", [])])

    # register
    ws = _sheet("Register")
    reg = package.get("register", {})
    rows = []
    for cat in ("assumptions", "exclusions", "data_gaps"):
        for i in reg.get(cat, []):
            rows.append([i["id"], cat, i["text"], i.get("source") or ""])
    _table(ws, 1, ["ID", "Category", "Statement", "Source"], rows)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------- docx

def to_docx(package: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    meta = package.get("meta", {})
    doc = Document()
    accent = RGBColor(0x24, 0x3A, 0x5E)

    def _h(text, level=1):
        p = doc.add_heading(text, level=level)
        for r in p.runs:
            r.font.color.rgb = accent
        return p

    title = doc.add_paragraph()
    run = title.add_run(f"Migration estimate\n{meta.get('package_id', '')}")
    run.bold = True
    run.font.size = Pt(24)
    run.font.color.rgb = accent
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    wm = doc.add_paragraph()
    wr = wm.add_run(meta.get("watermark") or "DRAFT")
    wr.bold = True
    wr.font.color.rgb = RGBColor(0xB0, 0x30, 0x30)
    wm.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_tbl = doc.add_table(rows=0, cols=2)
    meta_tbl.style = "Light List Accent 1"
    for k, v in [("Region", meta.get("region")), ("Currency", meta.get("currency")),
                 ("Prices as of", meta.get("price_date")),
                 ("Overall confidence", meta.get("overall_confidence")),
                 ("Generated", meta.get("generated_on")),
                 ("Tools run", ", ".join(meta.get("tools_run") or []))]:
        cells = meta_tbl.add_row().cells
        cells[0].text, cells[1].text = str(k), _fmt(v)

    _h("Headline numbers", 1)
    t = doc.add_table(rows=1, cols=4)
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(("Figure", "Value", "Confidence", "Ref")):
        t.rows[0].cells[i].text = h
    for f in _headline(package):
        c = t.add_row().cells
        c[0].text, c[1].text = f["label"], f"{_fmt(f['value'])} {f['unit']}"
        c[2].text, c[3].text = f["confidence"], f["id"]

    for s in _sections(package):
        _h(f"{s['id']}. {s['title']}", 1)
        for line in _body_lines(s):
            doc.add_paragraph(line, style="List Bullet" if not line.startswith("|") else None)

    _h("Calculation appendix", 1)
    at = doc.add_table(rows=1, cols=5)
    at.style = "Light Grid Accent 1"
    for i, h in enumerate(("Ref", "Figure", "Result", "Formula", "Confidence")):
        at.rows[0].cells[i].text = h
    for a in package.get("calculation_appendix", []):
        c = at.add_row().cells
        c[0].text, c[1].text = a["figure_id"], a["label"]
        c[2].text = f"{_fmt(a['result'])} {a['unit']}"
        c[3].text, c[4].text = a["formula"], a["confidence"]

    reg = package.get("register", {})
    for cat, label in (("assumptions", "Assumptions"), ("exclusions", "Exclusions"),
                       ("data_gaps", "Data gaps")):
        _h(f"Register — {label}", 2)
        for i in reg.get(cat, []):
            doc.add_paragraph(f"{i['id']}  {i['text']}", style="List Bullet")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------- pptx

def to_pptx(package: dict) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    meta = package.get("meta", {})
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    accent = RGBColor(0x24, 0x3A, 0x5E)

    def _slide(title):
        s = prs.slides.add_slide(blank)
        box = s.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12), Inches(0.9))
        p = box.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = title
        r.font.size = Pt(30)
        r.font.bold = True
        r.font.color.rgb = accent
        return s

    def _bullets(slide, lines, top=1.5, size=16):
        box = slide.shapes.add_textbox(Inches(0.7), Inches(top), Inches(12), Inches(5.4))
        tf = box.text_frame
        tf.word_wrap = True
        for i, line in enumerate(lines):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.text = str(line)
            para.font.size = Pt(size)
            para.level = 1 if str(line).startswith("  ") else 0

    # title slide
    s = prs.slides.add_slide(blank)
    box = s.shapes.add_textbox(Inches(1), Inches(2.6), Inches(11.3), Inches(2.4))
    tf = box.text_frame
    tf.word_wrap = True
    r = tf.paragraphs[0].add_run()
    r.text = f"Migration estimate — {meta.get('package_id', '')}"
    r.font.size = Pt(40)
    r.font.bold = True
    r.font.color.rgb = accent
    p2 = tf.add_paragraph()
    p2.text = f"{meta.get('watermark', 'DRAFT')}"
    p2.font.size = Pt(18)
    p2.font.color.rgb = RGBColor(0xB0, 0x30, 0x30)
    p3 = tf.add_paragraph()
    p3.text = (f"Region {meta.get('region') or 'n/a'} · {meta.get('currency')} · "
               f"prices {meta.get('price_date') or 'n/a'} · confidence {meta.get('overall_confidence')}")
    p3.font.size = Pt(14)

    # headline
    s = _slide("Headline numbers")
    _bullets(s, [f"{f['label']}:  {_fmt(f['value'])} {f['unit']}   ({f['confidence']} · {f['id']})"
                 for f in _headline(package)], size=20)

    # a slide per section
    for sec in _sections(package):
        s = _slide(f"{sec['id']}. {sec['title']}")
        lines = [ln for ln in _body_lines(sec) if not ln.startswith("|")][:10]
        _bullets(s, lines or ["(tool not run)"])

    # assumptions
    reg = package.get("register", {})
    s = _slide("Assumptions & exclusions")
    _bullets(s, [f"{i['id']}  {i['text']}" for i in (reg.get("assumptions", []) + reg.get("exclusions", []))][:10],
             size=13)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------- shared

def _kv(d):
    return ", ".join(f"{k}={_fmt(v)}" for k, v in (d or {}).items() if v is not None) or "—"


def _body_lines(section: dict) -> list[str]:
    """Flatten a section body into human-readable lines (mirrors assemble's render)."""
    body = section.get("body") or {}
    key = section.get("key")
    if body.get("note"):
        return [body["note"]]
    if key == "current_state":
        return [f"{body.get('servers')} servers ({body.get('servers_powered_on') or '?'} on), "
                f"{body.get('applications')} applications",
                f"{body.get('total_vcpu')} vCPU · {body.get('total_ram_gb')} GB RAM · "
                f"{body.get('provisioned_disk_tb')} TB provisioned disk",
                f"{body.get('eol_servers')} servers past OS end-of-support · "
                f"{body.get('no_perf_data_servers') or 0} without performance history",
                f"Data-quality confidence: {body.get('data_quality_confidence') or 'n/a'}"]
    if key == "landing_zone":
        return [body.get("summary", ""),
                f"{len(body.get('spokes', []))} spokes · identity {body.get('identity')} · "
                f"connectivity {body.get('connectivity')}",
                f"DR: {body.get('dr')}"]
    if key == "disposition":
        bd = body.get("by_disposition") or {}
        return ["  ".join(f"{v} {k}" for k, v in bd.items()),
                f"Needs a business decision: {', '.join(body.get('needs_human_decision') or []) or 'none'}"]
    if key == "waves":
        return [f"Wave {w['wave']} [{w['kind']}] — {w['app_count']} apps / {w['server_count']} servers, "
                f"risk {w['risk_score']} ({w['risk_band']})" for w in body.get("waves", [])]
    if key == "run_rate_cost":
        out = [f"{_fmt(body.get('monthly'))} {body.get('currency')} / month "
               f"(~{_fmt(body.get('annual'))} / year), {body.get('reserved_term')} reserved, "
               f"region {body.get('region')}, prices {body.get('price_date') or 'n/a'}"]
        if body.get("one_time"):
            out.append(f"One-time migration cost: ~{_fmt(body['one_time'])} {body.get('currency')}")
        for d in body.get("top_cost_drivers", []):
            out.append(f"  {d['driver']} — {d['share_pct']}%")
        return out
    if key == "migration_effort":
        return [f"{body.get('estimate_at_completion_pd')} person-days "
                f"(range {body.get('range_pd', {}).get('low')}–{body.get('range_pd', {}).get('high')})",
                f"Services cost ~{_fmt(body.get('services_cost', {}).get('expected'))} "
                f"{body.get('services_cost', {}).get('currency')}",
                body.get("basis", "")]
    if key == "assumptions_register":
        return [f"{len(body.get('assumptions', []))} assumptions, "
                f"{len(body.get('exclusions', []))} exclusions, "
                f"{len(body.get('data_gaps', []))} data gaps"]
    if key == "next_steps":
        return list(body.get("actions", []))
    return [str(body)]
