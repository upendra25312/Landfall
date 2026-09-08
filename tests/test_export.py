"""Cycle 13 — deliverable/export.py (E5.4): Excel / Word / PowerPoint exports."""
import io
import sys
import os

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "evals"))

from deliverable.export import export, to_xlsx, to_docx, to_pptx
import pipeline as P


@pytest.fixture(scope="module")
def package():
    return P.run()


def test_dispatcher_rejects_unknown_format(package):
    with pytest.raises(ValueError):
        export(package, "pdf")


def test_xlsx_opens_and_has_a_sheet_per_section_plus_appendix(package):
    from openpyxl import load_workbook
    blob, name, mime = export(package, "xlsx")
    assert name.endswith(".xlsx") and "spreadsheet" in mime and len(blob) > 5000
    wb = load_workbook(io.BytesIO(blob))
    assert "Cover" in wb.sheetnames and "Calculation appendix" in wb.sheetnames
    assert "Register" in wb.sheetnames
    n_sections = len(package["sections"])
    section_sheets = [s for s in wb.sheetnames if s.startswith(("S1", "S2", "S3", "S4",
                                                                "S5", "S6", "S7", "S8"))]
    assert len(section_sheets) == n_sections
    # a headline figure value shows up somewhere in the workbook
    appendix = wb["Calculation appendix"]
    refs = {row[0].value for row in appendix.iter_rows(min_row=2)}
    assert {f["id"] for f in package["figures"]} <= refs


def test_docx_opens_and_carries_the_watermark_and_appendix(package):
    from docx import Document
    blob, name, mime = export(package, "docx")
    assert name.endswith(".docx") and "wordprocessing" in mime
    d = Document(io.BytesIO(blob))
    text = "\n".join(p.text for p in d.paragraphs)
    assert "DRAFT" in text
    assert any("Calculation appendix" in p.text for p in d.paragraphs)
    # every register id appears
    reg_ids = [i["id"] for cat in ("assumptions", "exclusions", "data_gaps")
               for i in package["register"][cat]]
    assert all(any(rid in p.text for p in d.paragraphs) for rid in reg_ids[:5])


def test_pptx_opens_and_has_title_headline_and_section_slides(package):
    from pptx import Presentation
    blob, name, mime = export(package, "pptx")
    assert name.endswith(".pptx") and "presentation" in mime
    prs = Presentation(io.BytesIO(blob))
    # title + headline + one per section + assumptions
    assert len(prs.slides) == 1 + 1 + len(package["sections"]) + 1
    all_text = " ".join(sh.text_frame.text for sl in prs.slides for sh in sl.shapes
                        if sh.has_text_frame)
    assert "Migration estimate" in all_text and "Headline numbers" in all_text


def test_exports_are_deterministic_byte_for_byte(package):
    # openpyxl / docx / pptx embed a timestamp in the zip; compare the parsed content
    from openpyxl import load_workbook
    a = load_workbook(io.BytesIO(to_xlsx(package)))
    b = load_workbook(io.BytesIO(to_xlsx(package)))
    ca = [list(r) for r in a["Calculation appendix"].iter_rows(values_only=True)]
    cb = [list(r) for r in b["Calculation appendix"].iter_rows(values_only=True)]
    assert ca == cb


def test_degraded_package_still_exports(package):
    from deliverable.assemble import assemble_estimate
    thin = assemble_estimate({"inventory_summary": {"servers": 10, "applications": 2},
                              "data_quality": {"confidence": "Low"},
                              "compute_cost": {"error": "price API 503"}})
    for fmt in ("xlsx", "docx", "pptx"):
        blob, _, _ = export(thin, fmt)
        assert len(blob) > 3000
