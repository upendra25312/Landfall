"""
Client-ready exports of an assembled estimate package (PRD E5.4).

    from deliverable.export import export
    blob, filename, mime = export(package, "xlsx")   # or "docx" / "pptx"

xlsx — a workbook: cover, headline figures, a sheet per section, the calculation
       appendix, the register.
docx — a proposal-ready document: title page, headline table, every section,
       the calculation appendix, the register.
pptx — a client-facing "Azure Migration Assessment" readout: a 12-slide narrative
       (cover · executive summary · approach · current state · landing zone · 6R
       disposition · wave plan · run-rate cost · effort · risk register · next
       steps · traceability) with native charts, tables and shapes. Narrative
       follows the Microsoft CAF + Migration Execution Guide lifecycle.

Every figure keeps its `F*` reference so the calculation appendix still ties out.
All three carry the package's DRAFT watermark (every slide, not just the cover).
Pure — the package is the only input; no external assets, no network.
"""
from __future__ import annotations

import io
import logging

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
    # the Model sheet is a live calculation — tell every consumer (Excel, LibreOffice,
    # the recalc CI gate) to recompute on open so cached values are never stale (E11.12)
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
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

    # live model — derived cells as formulas that reflow on an input change (E11.12)
    try:
        from .xlsx_model import write_model_sheet
        write_model_sheet(wb, package)
    except Exception:  # noqa: BLE001 - the model sheet is a bonus, never break the export
        logging.getLogger(__name__).warning("xlsx model sheet skipped", exc_info=True)

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
    from docx.shared import Inches, Pt, RGBColor

    meta = package.get("meta", {})
    doc = Document()
    # US-Letter in DXA (E5.4q / E11.12) — explicit so the doc renders the same for
    # every reviewer regardless of their Word default; 1" margins.
    for sec in doc.sections:
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
        sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)
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
#
# A client-facing "Azure Migration Assessment" readout. The narrative follows
# the Microsoft Cloud Adoption Framework + Migration Execution Guide lifecycle
# (Assess -> Plan & Design -> Mobilise -> Migrate -> Optimise). Native charts,
# tables and shapes only -- no external image assets. Every figure keeps its
# F-reference; the full calculation appendix travels in the .xlsx / .docx.

_PP = {
    "ink": "1B2A4A", "azure": "0078D4", "azure_d": "005A9E", "cyan": "2AA9E0",
    "slate": "5B6B7F", "mist": "F2F6FC", "line": "D7E1EC", "paper": "FFFFFF",
    "good": "0E7C3A", "warn": "B06E00", "risk": "C4314B", "band": "EAF3FB",
}
_SERIES = ["0078D4", "2AA9E0", "8661C5", "E8A33D", "5B6B7F", "0E7C3A"]
_FONT, _FONT_LIGHT = "Segoe UI", "Segoe UI Light"

_LIFECYCLE = [
    ("Assess", "Digital estate, readiness, right-sizing"),
    ("Plan & Design", "Landing zone, dispositions, wave plan"),
    ("Mobilise", "Foundation build, tooling, pilot wave"),
    ("Migrate", "Waves — pilot to regulated"),
    ("Optimise", "Cost, performance, decommission on-prem"),
]
_TOTAL_CONTENT = 11  # numbered content slides (the cover is not numbered)


def to_pptx(package: dict) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn

    def C(h):
        return RGBColor.from_string(h)

    meta = package.get("meta", {}) or {}
    figs = {f.get("key"): f for f in package.get("figures", [])}
    secs = {s.get("key"): (s.get("body") or {}) for s in package.get("sections", [])}
    reg = package.get("register", {}) or {}
    ccy = meta.get("currency", "USD")
    watermark = meta.get("watermark") or "DRAFT — architect review required"

    def fv(key, field="value", default=None):
        return (figs.get(key) or {}).get(field, default)

    def ref(key):
        return (figs.get(key) or {}).get("id", "")

    def money(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "—"
        if abs(v) >= 1_000_000:
            return f"{ccy} {v / 1_000_000:,.2f}M"
        return f"{ccy} {v:,.0f}"

    def num(v, suffix=""):
        try:
            return f"{float(v):,.0f}{suffix}"
        except (TypeError, ValueError):
            return "n/a"

    def pct(v):
        try:
            return f"{float(v):g}%"
        except (TypeError, ValueError):
            return "n/a"

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    BLANK = prs.slide_layouts[6]
    SW, SH, MX = 13.333, 7.5, 0.62
    slides_built = [0]

    try:
        for el in prs.slide_masters[0].element.iter(qn("a:latin")):
            el.set("typeface", _FONT)
    except Exception:                                        # noqa: BLE001
        pass

    # ---------------- primitives ----------------
    def new_slide():
        return prs.slides.add_slide(BLANK)

    def tbox(s, x, y, w, h):
        tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Pt(0)
        return tf

    def para(tf, text, size=12, color="1B2A4A", bold=False, first=False,
             align=PP_ALIGN.LEFT, font=None, space_after=4, level=0):
        p = tf.paragraphs[0] if (first and not tf.paragraphs[0].runs) else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.level = level
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = font or _FONT
        r.font.color.rgb = C(color)
        return p

    def rrect(s, x, y, w, h, fill=None, line_c=None, line_w=1.0, rounded=False):
        shp = s.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
            Inches(x), Inches(y), Inches(w), Inches(h))
        if rounded:
            try:
                shp.adjustments[0] = 0.055
            except Exception:                                # noqa: BLE001
                pass
        if fill is None:
            shp.fill.background()
        else:
            shp.fill.solid()
            shp.fill.fore_color.rgb = C(fill)
        if line_c is None:
            shp.line.fill.background()
        else:
            shp.line.color.rgb = C(line_c)
            shp.line.width = Pt(line_w)
        shp.shadow.inherit = False
        return shp

    def heading(s, text, kicker=None):
        ty = 0.5
        if kicker:
            para(tbox(s, MX, 0.4, SW - 2 * MX, 0.3), kicker.upper(), size=10.5,
                 color=_PP["azure"], bold=True, first=True)
            ty = 0.72
        para(tbox(s, MX, ty, SW - 2 * MX, 0.7), text, size=25, color=_PP["ink"],
             bold=True, first=True)
        rrect(s, MX, ty + 0.66, 1.05, 0.05, fill=_PP["azure"])

    def footer(s):
        para(tbox(s, MX, SH - 0.42, 7.0, 0.3), watermark, size=8, color=_PP["risk"],
             bold=True, first=True)
        para(tbox(s, SW - MX - 4.5, SH - 0.42, 4.5, 0.3),
             f"Confidential — for client discussion    ·    {slides_built[0] + 1} / {_TOTAL_CONTENT}",
             size=8, color=_PP["slate"], align=PP_ALIGN.RIGHT, first=True)

    def notes(s, text):
        try:
            s.notes_slide.notes_text_frame.text = text
        except Exception:                                    # noqa: BLE001
            pass

    def content_slide(title_txt, kicker=None, note=None):
        s = new_slide()
        heading(s, title_txt, kicker)
        footer(s)
        if note:
            notes(s, note)
        slides_built[0] += 1
        return s

    def takeaway(s, text):
        rrect(s, MX, SH - 1.28, SW - 2 * MX, 0.62, fill=_PP["band"])
        rrect(s, MX, SH - 1.28, 0.06, 0.62, fill=_PP["azure"])
        para(tbox(s, MX + 0.26, SH - 1.19, SW - 2 * MX - 0.5, 0.46), text,
             size=10.5, color=_PP["azure_d"], bold=True, first=True)

    def kpi(s, x, y, w, h, label, value, sub=None, tag=None, accent="0078D4"):
        rrect(s, x, y, w, h, fill=_PP["mist"], line_c=_PP["line"], rounded=True)
        rrect(s, x + 0.001, y + 0.16, 0.06, h - 0.32, fill=accent)
        tf = tbox(s, x + 0.28, y + 0.18, w - 0.44, h - 0.32)
        para(tf, label.upper(), size=8.5, color=_PP["slate"], bold=True, first=True, space_after=3)
        para(tf, value, size=21, color=_PP["ink"], bold=True, font=_FONT_LIGHT, space_after=2)
        if sub:
            para(tf, sub, size=9, color=_PP["slate"], space_after=1)
        if tag:
            para(tf, tag, size=7.5, color=_PP["azure_d"], space_after=0)

    def pill(s, x, y, w, h, text, fill, tc="FFFFFF"):
        p = rrect(s, x, y, w, h, fill=fill, rounded=True)
        try:
            p.adjustments[0] = 0.5
        except Exception:                                    # noqa: BLE001
            pass
        tf = p.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = Pt(3)
        tf.margin_top = tf.margin_bottom = Pt(0)
        para(tf, text, size=8.5, color=tc, bold=True, first=True, align=PP_ALIGN.CENTER, space_after=0)

    def doughnut(s, x, y, w, h, pairs):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        pairs = [(str(k), float(v)) for k, v in pairs if v]
        if not pairs:
            para(tbox(s, x, y + h / 2, w, 0.4), "chart data not available", size=9,
                 color=_PP["slate"], first=True, align=PP_ALIGN.CENTER)
            return
        cd = CategoryChartData()
        cd.categories = [k for k, _ in pairs]
        cd.add_series("v", [v for _, v in pairs])
        gf = s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(x), Inches(y),
                                Inches(w), Inches(h), cd)
        ch = gf.chart
        ch.has_title = False
        ch.has_legend = True
        ch.legend.position = XL_LEGEND_POSITION.RIGHT
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(9)
        plot = ch.plots[0]
        try:
            plot.donut_hole_size = 60
        except Exception:                                    # noqa: BLE001
            pass
        plot.has_data_labels = True
        plot.data_labels.number_format = "0%"
        plot.data_labels.number_format_is_linked = False
        plot.data_labels.font.size = Pt(8)
        plot.data_labels.font.bold = True
        plot.data_labels.font.color.rgb = C("FFFFFF")
        for i, pt in enumerate(plot.series[0].points):
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = C(_SERIES[i % len(_SERIES)])
            pt.format.line.color.rgb = C("FFFFFF")
            pt.format.line.width = Pt(1.5)

    def barh(s, x, y, w, h, cats, vals, fmt="#,##0"):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE
        pairs = [(str(c), float(v)) for c, v in zip(cats, vals) if v is not None]
        if not pairs:
            return
        cd = CategoryChartData()
        cd.categories = [c for c, _ in pairs]
        cd.add_series("v", [v for _, v in pairs])
        gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y),
                                Inches(w), Inches(h), cd)
        ch = gf.chart
        ch.has_title = False
        ch.has_legend = False
        ch.category_axis.tick_labels.font.size = Pt(9)
        ch.value_axis.visible = False
        for ax in (ch.value_axis, ch.category_axis):
            try:
                ax.has_major_gridlines = False
            except Exception:                                # noqa: BLE001
                pass
        plot = ch.plots[0]
        plot.gap_width = 55
        plot.has_data_labels = True
        plot.data_labels.number_format = fmt
        plot.data_labels.number_format_is_linked = False
        plot.data_labels.font.size = Pt(8.5)
        ser = plot.series[0]
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = C(_PP["azure"])

    def table(s, x, y, w, headers, rows, ratio, risk_col=None, row_h=0.33):
        head_h = 0.36
        gf = s.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y),
                                Inches(w), Inches(head_h + row_h * len(rows)))
        t = gf.table
        t.first_row = False
        t.horz_banding = False
        tot = float(sum(ratio))
        for i, rr in enumerate(ratio):
            t.columns[i].width = Inches(w * rr / tot)
        t.rows[0].height = Inches(head_h)
        for j, htext in enumerate(headers):
            c = t.cell(0, j)
            c.fill.solid()
            c.fill.fore_color.rgb = C(_PP["ink"])
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.margin_left = c.margin_right = Pt(6)
            c.margin_top = c.margin_bottom = Pt(2)
            para(c.text_frame, str(htext), size=8.5, color="FFFFFF", bold=True,
                 first=True, space_after=0)
        for ri, row in enumerate(rows, start=1):
            t.rows[ri].height = Inches(row_h)
            for j, val in enumerate(row):
                c = t.cell(ri, j)
                c.fill.solid()
                c.fill.fore_color.rgb = C(_PP["paper"] if ri % 2 else _PP["mist"])
                c.vertical_anchor = MSO_ANCHOR.MIDDLE
                c.margin_left = c.margin_right = Pt(6)
                c.margin_top = c.margin_bottom = Pt(1)
                if risk_col is not None and j == risk_col:
                    band = str(val).lower()
                    col = {"high": _PP["risk"], "medium": _PP["warn"],
                           "low": _PP["good"]}.get(band, _PP["ink"])
                    para(c.text_frame, str(val).title(), size=8.5, color=col,
                         bold=True, first=True, space_after=0)
                else:
                    para(c.text_frame, str(val), size=8.5, color=_PP["ink"],
                         first=True, space_after=0)
        return gf

    # ================= SLIDE 1 — cover =================
    s = new_slide()
    rrect(s, 0, 0, SW, 2.55, fill=_PP["ink"])
    rrect(s, 0, 2.55, SW, 0.08, fill=_PP["azure"])
    for i, dia in enumerate((1.9, 1.35, 0.85)):
        o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(11.0 + i * 0.35),
                               Inches(0.35 + i * 0.35), Inches(dia), Inches(dia))
        o.fill.solid()
        o.fill.fore_color.rgb = C(_PP["azure"] if i == 1 else _PP["azure_d"])
        o.line.fill.background()
        o.shadow.inherit = False
    para(tbox(s, MX, 0.62, 9.5, 0.35), "AZURE MIGRATION ASSESSMENT", size=12,
         color=_PP["cyan"], bold=True, first=True)
    para(tbox(s, MX, 1.02, 10.5, 1.2), "Landing-zone & migration estimate", size=33,
         color="FFFFFF", bold=True, first=True, font=_FONT_LIGHT)
    para(tbox(s, MX, 1.95, 10.5, 0.4),
         f"{meta.get('firm_name') or 'Prepared for client review'}   ·   "
         f"engagement {meta.get('package_id', 'landfall-estimate')}",
         size=11, color="D6E6F5", first=True)
    pill(s, MX, 2.95, 1.5, 0.36, "DRAFT", _PP["risk"])
    pill(s, MX + 1.66, 2.95, 2.7, 0.36,
         f"confidence: {meta.get('overall_confidence', 'n/a')}", _PP["slate"])
    para(tbox(s, MX, 3.6, 11.0, 0.9),
         f"Region {meta.get('region') or 'n/a'}  ·  {ccy}  ·  "
         f"list prices as of {meta.get('price_date') or 'n/a'}  ·  "
         f"generated {meta.get('generated_on') or 'n/a'}",
         size=11, color=_PP["slate"], first=True)
    para(tbox(s, MX, 4.15, 11.5, 1.4),
         "A data-derived draft for a named architect to review and own — not a bid. "
         "Every figure carries an F-reference to the calculation appendix in the "
         "accompanying Excel workbook. Structure follows the Microsoft Cloud Adoption "
         "Framework and Migration Execution Guide.",
         size=10.5, color=_PP["slate"], first=True)
    para(tbox(s, MX, SH - 0.55, 11.0, 0.3), watermark, size=8.5, color=_PP["risk"],
         bold=True, first=True)
    notes(s, "Cover. This is a DRAFT migration assessment generated from the client's "
             "own inventory. Set expectations: architect-owned, assumptions stated, "
             "confidence graded. Walk to the executive summary.")

    # ================= SLIDE 2 — executive summary =================
    cs = secs.get("current_state", {})
    rr = secs.get("run_rate_cost", {})
    ef = secs.get("migration_effort", {})
    dp = secs.get("disposition", {})
    n_dec = len(dp.get("needs_human_decision") or [])
    narrative = (
        f"The estate is {fv('servers_total', default='n/a')} servers and "
        f"{fv('apps_total', default='n/a')} applications across "
        f"{len(cs.get('by_env') or {})} environments. Running it on Azure is about "
        f"{money(fv('run_rate_annual'))} per year, plus roughly "
        f"{money(fv('one_time_cost'))} one-time to migrate. Delivery is estimated at "
        f"{num(fv('effort_pd'))} person-days "
        f"(≈{money(fv('services_cost'))} services) across "
        f"{fv('wave_count', default='n/a')} waves into a "
        f"{fv('lz_spokes', default='n/a')}-spoke landing zone. "
        f"{fv('eol_servers', default=0)} servers are past OS end-of-support and "
        f"{n_dec} application(s) need a disposition decision before the plan is firm."
    )
    s = content_slide("Executive summary", kicker="The estimate at a glance",
                      note="Read the narrative. The three tiles are the numbers a "
                           "sponsor remembers: annual run-rate, one-time cost, effort. "
                           "Everything after this slide is the working behind them.")
    para(tbox(s, MX, 1.65, 7.7, 3.6), narrative, size=13, color=_PP["ink"], first=True)
    kx, kw, kh = 8.7, 4.0, 1.45
    kpi(s, kx, 1.55, kw, kh, "Azure run-rate / year", money(fv("run_rate_annual")),
        sub=f"≈ {money(fv('run_rate_monthly'))} / month",
        tag=f"{ref('run_rate_annual')} · {fv('run_rate_annual', 'confidence', 'n/a')} confidence")
    kpi(s, kx, 3.13, kw, kh, "One-time migration cost", money(fv("one_time_cost")),
        sub="dual-run + tooling + replication",
        tag=f"{ref('one_time_cost')} · {fv('one_time_cost', 'confidence', 'n/a')} confidence",
        accent=_PP["cyan"])
    kpi(s, kx, 4.71, kw, kh, "Migration effort", f"{num(fv('effort_pd'))} PD",
        sub=f"≈ {money(fv('services_cost'))} services cost",
        tag=f"{ref('effort_pd')} · {fv('effort_pd', 'confidence', 'n/a')} confidence",
        accent=_PP["slate"])
    takeaway(s, "Defensible enough to shape a Statement of Work; the architect closes "
                "the open decisions and data gaps before it is quoted.")

    # ================= SLIDE 3 — approach / lifecycle =================
    s = content_slide("Our approach", kicker="Method",
                      note="We follow the Microsoft migration lifecycle. This deck is the "
                           "output of Assess and Plan & Design. Mobilise / Migrate / "
                           "Optimise are the delivery phases the wave plan sequences.")
    para(tbox(s, MX, 1.6, SW - 2 * MX, 0.5),
         "Aligned to the Microsoft Cloud Adoption Framework and the Migration Execution "
         "Guide. This assessment covers Assess and Plan & Design; the wave plan sequences "
         "the rest.", size=11, color=_PP["slate"], first=True)
    n = len(_LIFECYCLE)
    cw = (SW - 2 * MX - (n - 1) * 0.12) / n
    for i, (name, desc) in enumerate(_LIFECYCLE):
        x = MX + i * (cw + 0.12)
        ch = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(x), Inches(2.5),
                                Inches(cw + 0.12), Inches(1.15))
        ch.fill.solid()
        ch.fill.fore_color.rgb = C(_PP["azure"] if i < 2 else _PP["slate"])
        ch.line.fill.background()
        ch.shadow.inherit = False
        tf = ch.text_frame
        tf.word_wrap = True
        para(tf, name, size=11, color="FFFFFF", bold=True, first=True,
             align=PP_ALIGN.CENTER, space_after=0)
        para(tbox(s, x, 3.8, cw + 0.12, 1.4), desc, size=9, color=_PP["slate"],
             first=True, align=PP_ALIGN.CENTER)
    para(tbox(s, MX, 2.15, 4.0, 0.3), "▸ THIS ASSESSMENT", size=8.5,
         color=_PP["azure"], bold=True, first=True)
    takeaway(s, "The numbers in this deck come from deterministic tools over the client "
                "inventory — not estimates typed by hand.")

    # ================= SLIDE 4 — current state =================
    by_env = cs.get("by_env") or {}
    s = content_slide("Current state — digital estate", kicker="Assess",
                      note="The estate we are sizing. Call out the readiness gaps: EOL "
                           "servers drive replatform/retire pressure; missing perf data "
                           "means right-sizing for those servers is Low confidence.")
    tw = (SW - 2 * MX - 3 * 0.2) / 4
    kpi(s, MX + 0 * (tw + 0.2), 1.6, tw, 1.3, "Servers", str(fv("servers_total", default="n/a")),
        tag=ref("servers_total"))
    kpi(s, MX + 1 * (tw + 0.2), 1.6, tw, 1.3, "Applications", str(fv("apps_total", default="n/a")),
        tag=ref("apps_total"), accent=_PP["cyan"])
    kpi(s, MX + 2 * (tw + 0.2), 1.6, tw, 1.3, "Current vCPU", f"{fv('vcpu_total', default='n/a'):,}"
        if isinstance(fv("vcpu_total"), (int, float)) else "n/a", tag=ref("vcpu_total"), accent=_PP["slate"])
    kpi(s, MX + 3 * (tw + 0.2), 1.6, tw, 1.3, "RAM · disk",
        f"{_fmt(cs.get('total_ram_gb'))} GB",
        sub=f"{_fmt(cs.get('provisioned_disk_tb'))} TB provisioned", accent=_PP["slate"])
    para(tbox(s, MX, 3.2, 5.0, 0.3), "SERVERS BY ENVIRONMENT", size=9, color=_PP["slate"],
         bold=True, first=True)
    order = sorted(by_env.items(), key=lambda kv: -kv[1])
    barh(s, MX - 0.1, 3.5, 5.6, 2.0, [k for k, _ in order], [v for _, v in order])
    rrect(s, 6.7, 3.4, SW - MX - 6.7, 2.1, fill=_PP["mist"], line_c=_PP["line"], rounded=True)
    rf = tbox(s, 6.95, 3.6, SW - MX - 7.2, 1.8)
    para(rf, "READINESS SIGNALS", size=9, color=_PP["slate"], bold=True, first=True, space_after=6)
    para(rf, f"•  {fv('eol_servers', default=0)} servers past OS end-of-support  "
             f"({ref('eol_servers')})", size=10.5, color=_PP["ink"], space_after=5)
    para(rf, f"•  {cs.get('no_perf_data_servers') or 0} servers with no performance "
             f"history — right-sizing for those is Low confidence", size=10.5,
         color=_PP["ink"], space_after=5)
    para(rf, f"•  data-quality confidence: {cs.get('data_quality_confidence') or 'n/a'}",
         size=10.5, color=_PP["ink"], space_after=0)
    takeaway(s, "Right-sizing and cost carry the estate's data-quality confidence; the "
                "gaps above are the first thing to close with the client.")

    # ================= SLIDE 5 — landing zone =================
    lz = secs.get("landing_zone", {})
    spokes = lz.get("spokes") or []
    by_zone = {}
    for sp in spokes:
        by_zone[sp.get("zone", "?")] = by_zone.get(sp.get("zone", "?"), 0) + 1
    s = content_slide("Target — Azure landing zone", kicker="Plan & Design",
                      note="CAF-aligned landing zone derived from the app portfolio and "
                           "compliance scope. The regulated spoke pair is data-driven: "
                           "apps carrying HIPAA / PCI-DSS scope land there, isolated.")
    zones = sorted(by_zone.items(), key=lambda kv: -kv[1])[:5]
    hub_cy = 1.75 + max(1, len(zones)) * 1.0 / 2
    hub = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(MX + 0.35), Inches(hub_cy - 0.8),
                             Inches(1.6), Inches(1.6))
    hub.fill.solid(); hub.fill.fore_color.rgb = C(_PP["ink"]); hub.line.fill.background()
    hub.shadow.inherit = False
    htf = hub.text_frame
    para(htf, "Platform", size=10, color="FFFFFF", bold=True, first=True,
         align=PP_ALIGN.CENTER, space_after=0)
    para(htf, "hub", size=10, color="FFFFFF", bold=True, align=PP_ALIGN.CENTER, space_after=0)
    zy = 1.75
    for zn, cnt in zones:
        o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(3.05), Inches(zy), Inches(1.5), Inches(0.86))
        o.fill.solid(); o.fill.fore_color.rgb = C(_PP["azure"]); o.line.fill.background()
        o.shadow.inherit = False
        otf = o.text_frame
        para(otf, str(zn).title(), size=9, color="FFFFFF", bold=True, first=True,
             align=PP_ALIGN.CENTER, space_after=0)
        para(otf, f"{cnt} spoke(s)", size=7.5, color="FFFFFF", align=PP_ALIGN.CENTER, space_after=0)
        cn = s.shapes.add_connector(1, Inches(MX + 1.95), Inches(hub_cy),
                                    Inches(3.05), Inches(zy + 0.43))
        cn.line.color.rgb = C(_PP["line"]); cn.line.width = Pt(1.25)
        cn.shadow.inherit = False
        zy += 1.0
    zone_rows = [[str(zn).title(), str(c),
                  {"regulated": "Regulated scope — isolated spoke + Confidential MG",
                   "online": "Internet-facing workloads",
                   "corp": "Internal line-of-business",
                   "sandbox": "Non-production experimentation"}.get(zn, "—")]
                 for zn, c in zones]
    table(s, 5.1, 1.75, SW - MX - 5.1, ["Zone", "Spokes", "Purpose"], zone_rows, [1.1, 0.8, 3.2])
    band_y = 1.75 + 0.36 + 0.33 * len(zone_rows) + 0.3
    rrect(s, 5.1, band_y, SW - MX - 5.1, 1.5, fill=_PP["mist"], line_c=_PP["line"], rounded=True)
    bf = tbox(s, 5.35, band_y + 0.16, SW - MX - 5.6, 1.2)
    para(bf, f"Identity   ·   {lz.get('identity') or 'n/a'}", size=10, color=_PP["ink"],
         first=True, space_after=4)
    para(bf, f"Connectivity   ·   {lz.get('connectivity') or 'n/a'}", size=10,
         color=_PP["ink"], space_after=4)
    para(bf, f"DR   ·   {lz.get('region') or 'n/a'} → {lz.get('dr_region') or 'n/a'} "
             f"(ASR for tier 1–2)", size=10, color=_PP["ink"], space_after=4)
    _conf = lz.get("design_conformance") or {}
    if _conf.get("headline"):
        para(bf, f"Design checklist   ·   {_conf['headline']}"
                 + ("  (+ AI-LZ overlay)" if _conf.get("ai_lz_applicable") else ""),
             size=10, color=_PP["ink"], space_after=0)
    takeaway(s, f"{fv('lz_spokes', default='n/a')} spokes, "
                f"{', '.join(lz.get('regulated_scopes') or []) or 'no'} regulated scope(s) "
                f"— topology derived from the portfolio, not a template"
                + (f"; {_conf['headline']} vs the Azure (AI) Landing Zone design checklist"
                   if _conf.get("headline") else "")
                + f". ({ref('lz_spokes')})")

    # ================= SLIDE 6 — disposition (6R) =================
    by_disp = dp.get("by_disposition") or {}
    need = dp.get("needs_human_decision") or []
    s = content_slide("Application disposition (6R)", kicker="Workload mapping",
                      note="Rule-derived from OS end-of-life, tech stack, criticality, "
                           "internet exposure and DB engine. Repurchase / Refactor / "
                           "Retire always need business sign-off — that is the callout.")
    doughnut(s, MX, 1.7, 6.2, 3.6, list(by_disp.items()))
    rrect(s, 7.6, 1.7, SW - MX - 7.6, 1.75, fill=_PP["mist"], line_c=_PP["line"], rounded=True)
    lf = tbox(s, 7.85, 1.88, SW - MX - 7.9, 1.5)
    para(lf, "DISPOSITION MIX", size=9, color=_PP["slate"], bold=True, first=True, space_after=5)
    for k, v in by_disp.items():
        para(lf, f"{v}  ×  {k}", size=11, color=_PP["ink"], space_after=3)
    rrect(s, 7.6, 3.65, SW - MX - 7.6, 1.65, fill="FBEEF0", line_c=_PP["risk"], rounded=True)
    wf = tbox(s, 7.85, 3.83, SW - MX - 7.9, 1.4)
    para(wf, "NEEDS A BUSINESS DECISION", size=9, color=_PP["risk"], bold=True, first=True,
         space_after=4)
    para(wf, ", ".join(need) if need else "none — all dispositions are rule-clear",
         size=10, color=_PP["ink"], space_after=0)
    takeaway(s, f"{sum(by_disp.values())} applications scored; {len(need)} held for "
                "owner sign-off. Rehost dominates — a lift-and-shift-first plan.")

    # ================= SLIDE 7 — wave plan =================
    waves = (secs.get("waves", {}) or {}).get("waves") or []
    s = content_slide("Migration wave plan", kicker="Wave planning",
                      note="Dependency graph -> affinity move-groups -> risk-ordered "
                           "waves. Platform foundation first, a low-risk pilot next, "
                           "regulated workloads last. Risk colour = the tool's score band.")
    wrows = [[f"Wave {w.get('wave')}", str(w.get('kind', '')).title(),
              str(w.get('app_count', '')), str(w.get('server_count', '')),
              str(w.get('risk_band', ''))] for w in waves[:9]]
    table(s, MX, 1.7, SW - 2 * MX, ["Wave", "Type", "Apps", "Servers", "Risk"],
          wrows, [0.9, 1.4, 0.7, 0.9, 1.0], risk_col=4, row_h=0.36)
    para(tbox(s, MX, 1.72 + 0.36 + 0.36 * len(wrows) + 0.2, SW - 2 * MX, 0.6),
         "Sequenced platform → pilot → standard → regulated. Regulated "
         "workloads (HIPAA, PCI-DSS) migrate last, after the controls are proven on "
         "earlier waves.", size=10, color=_PP["slate"], first=True)
    takeaway(s, f"{fv('wave_count', default=len(waves))} waves. "
                f"({ref('wave_count')})  Cross-wave blocking dependencies are listed in "
                "the workbook's wave sheet.")

    # ================= SLIDE 8 — run-rate cost =================
    drivers = rr.get("top_cost_drivers") or []
    shown = sum(d.get("share_pct", 0) for d in drivers)
    dough = [(d.get("driver", "?").split(" — ")[0], d.get("share_pct", 0)) for d in drivers]
    if 0 < shown < 99:
        dough.append(("Other", round(100 - shown, 1)))
    s = content_slide("Azure run-rate cost", kicker="Assess",
                      note="What the estate costs to run on Azure once migrated. "
                           "1-year reserved + Azure Hybrid Benefit assumed. The range is "
                           "wide because right-sizing confidence is Low on part of the fleet.")
    doughnut(s, MX, 1.7, 6.4, 3.7, dough)
    kpi(s, 8.0, 1.6, SW - MX - 8.0, 1.4, "Run-rate / month", money(fv("run_rate_monthly")),
        sub=f"≈ {money(fv('run_rate_annual'))} / year", tag=ref("run_rate_monthly"))
    rng = rr.get("range") or {}
    kpi(s, 8.0, 3.15, SW - MX - 8.0, 1.4, "Modelled range / month",
        f"{money(rng.get('low_monthly'))} – {money(rng.get('high_monthly'))}",
        sub="low – high on right-sizing + reservation", accent=_PP["slate"])
    para(tbox(s, 8.0, 4.75, SW - MX - 8.0, 0.9),
         f"{rr.get('reserved_term') or '1yr'} reserved · Azure Hybrid Benefit · "
         f"{rr.get('region') or meta.get('region')} · prices {rr.get('price_date') or 'n/a'}. "
         f"One-time migration ≈ {money(fv('one_time_cost'))} ({ref('one_time_cost')}).",
         size=9, color=_PP["slate"], first=True)
    takeaway(s, "Compute and managed disk are ~72% of run-rate — the two levers are "
                "right-sizing discipline and reservation coverage.")

    # ================= SLIDE 9 — effort & investment =================
    ws = ef.get("workstreams") or []
    ws_sorted = sorted(ws, key=lambda x: -(x.get("pd") or 0))[:7]
    s = content_slide("Migration effort & investment", kicker="Project plan",
                      note="Parametric model: servers + apps + disposition mix + spokes + "
                           "waves -> person-days. Contingency is tied to data-quality "
                           "confidence, not a flat number. Apply the firm's day rate.")
    para(tbox(s, MX, 1.55, 6.0, 0.3), "EFFORT BY WORKSTREAM (PERSON-DAYS)", size=9,
         color=_PP["slate"], bold=True, first=True)
    barh(s, MX - 0.1, 1.85, 6.6, 3.5,
         [w.get("workstream", "?") for w in ws_sorted],
         [w.get("pd", 0) for w in ws_sorted], fmt="#,##0")
    kpi(s, 7.9, 1.7, SW - MX - 7.9, 1.4, "Effort at completion",
        f"{num(fv('effort_pd'))} PD",
        sub=f"range {num((ef.get('range_pd') or {}).get('low'))}–"
            f"{num((ef.get('range_pd') or {}).get('high'))} PD", tag=ref("effort_pd"))
    kpi(s, 7.9, 3.25, SW - MX - 7.9, 1.4, "Services cost (expected)",
        money((ef.get("services_cost") or {}).get("expected")),
        sub="at the blended day rate", tag=ref("services_cost"), accent=_PP["cyan"])
    para(tbox(s, 7.9, 4.85, SW - MX - 7.9, 0.9),
         f"Contingency {pct(ef.get('contingency_pct'))} (data-quality "
         f"{cs.get('data_quality_confidence') or 'n/a'}) · PM + governance overlaid "
         f"on delivery · point estimate ±15%.", size=9, color=_PP["slate"], first=True)
    takeaway(s, "Effort and services cost move with the data-quality confidence and the "
                "open disposition decisions — both close in the next step.")

    # ================= SLIDE 10 — assumptions / exclusions / gaps =================
    s = content_slide("Assumptions, exclusions & data gaps", kicker="Risk register",
                      note="Every material assumption is machine-tracked with a stable id "
                           "and mapped to the source tool. Full register (A / X / G ids) "
                           "is in the workbook and the Word document.")
    cols = [("ASSUMPTIONS", reg.get("assumptions") or [], _PP["azure"]),
            ("EXCLUSIONS", reg.get("exclusions") or [], _PP["slate"]),
            ("DATA GAPS", reg.get("data_gaps") or [], _PP["warn"])]
    colw = (SW - 2 * MX - 2 * 0.3) / 3
    for i, (name, items, cc) in enumerate(cols):
        x = MX + i * (colw + 0.3)
        rrect(s, x, 1.65, colw, 0.5, fill=cc, rounded=True)
        para(tbox(s, x + 0.2, 1.75, colw - 0.4, 0.35),
             f"{name}   ({len(items)})", size=10, color="FFFFFF", bold=True, first=True)
        cf = tbox(s, x + 0.05, 2.35, colw - 0.1, 3.0)
        for it in items[:5]:
            txt = it.get("text", "")
            txt = txt if len(txt) <= 120 else txt[:117] + "…"
            para(cf, f"{it.get('id', '')}  {txt}", size=8.5, color=_PP["ink"], space_after=6)
        if len(items) > 5:
            para(cf, f"… and {len(items) - 5} more — see the workbook", size=8.5,
                 color=_PP["slate"], space_after=0)
    takeaway(s, "The register is generated across the whole run — it maps directly "
                "onto the SoW working-assumptions and risk sections.")

    # ================= SLIDE 11 — next steps =================
    actions = (secs.get("next_steps", {}) or {}).get("actions") or []
    s = content_slide("Recommended next steps", kicker="Mobilise",
                      note="The path from this draft to a quotable SoW. Item 1 is "
                           "non-negotiable: a named architect owns every number before "
                           "anything leaves the room.")
    yy = 1.75
    for i, act in enumerate(actions[:6], start=1):
        num = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(MX), Inches(yy), Inches(0.42), Inches(0.42))
        num.fill.solid(); num.fill.fore_color.rgb = C(_PP["azure"]); num.line.fill.background()
        num.shadow.inherit = False
        para(num.text_frame, str(i), size=12, color="FFFFFF", bold=True, first=True,
             align=PP_ALIGN.CENTER, space_after=0)
        para(tbox(s, MX + 0.66, yy + 0.02, SW - 2 * MX - 0.66, 0.7), act, size=11.5,
             color=_PP["ink"], first=True)
        yy += 0.78
    takeaway(s, "Weeks 1–2: close data gaps and disposition decisions, then the "
                "estimate is ready to price.")

    # ================= SLIDE 12 — traceability =================
    s = content_slide("Traceability & disclaimer", kicker="How to read this",
                      note="Close on the contract with the reader: it's a draft, every "
                           "number is traceable, the architect owns it. Hand over the "
                           "workbook for the full appendix.")
    para(tbox(s, MX, 1.75, SW - 2 * MX, 1.2),
         f"Every figure in this deck carries an F-reference (F1–F{len(package.get('figures', []))}). "
         "The full calculation appendix — source tool, query / filter, input row "
         "count, formula, assumptions applied and confidence for each figure — is in "
         "the accompanying Excel workbook and Word document.", size=12, color=_PP["ink"],
         first=True)
    rrect(s, MX, 3.3, SW - 2 * MX, 1.9, fill="FBEEF0", line_c=_PP["risk"], rounded=True)
    df = tbox(s, MX + 0.3, 3.55, SW - 2 * MX - 0.6, 1.5)
    para(df, watermark.upper(), size=11, color=_PP["risk"], bold=True, first=True, space_after=6)
    para(df, "This is a draft estimate produced from client-supplied inventory, which is "
             "typically incomplete. It is not a bid, a fixed price, or a commitment. A "
             "named migration architect must review, adjust and own every figure before "
             "it is used in a proposal or Statement of Work.", size=10, color=_PP["ink"],
         space_after=0)
    para(tbox(s, MX, 5.5, SW - 2 * MX, 0.4),
         f"Generated {meta.get('generated_on') or 'n/a'} · engagement "
         f"{meta.get('package_id', 'landfall-estimate')} · "
         f"config {('firm' if meta.get('firm_name') else 'defaults')}.",
         size=9, color=_PP["slate"], first=True)

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
        out = [body.get("summary", ""),
               f"{len(body.get('spokes', []))} spokes · identity {body.get('identity')} · "
               f"connectivity {body.get('connectivity')}",
               f"DR: {body.get('dr')}"]
        conf = body.get("design_conformance")
        if conf:
            out.append(f"Design conformance: {conf.get('headline')} "
                       f"(ALZ/AI-LZ design checklist"
                       + ("; AI-LZ overlay applies" if conf.get("ai_lz_applicable") else "")
                       + ")")
            for g in conf.get("gaps", [])[:12]:
                out.append(f"  [{g['status']}] {g['id']} {g['item']} — {g['recommendation']}")
        return out
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
        out = [f"{len(body.get('assumptions', []))} assumptions, "
               f"{len(body.get('exclusions', []))} exclusions, "
               f"{len(body.get('data_gaps', []))} data gaps"]
        disc = body.get("discovery")
        if disc:
            out.append(f"Discovery questionnaire: {disc.get('headline')}")
        return out
    if key == "next_steps":
        return list(body.get("actions", []))
    return [str(body)]
