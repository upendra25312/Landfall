"""C22 / E11.12 (E5.4q) — the estimate workbook is a *live model*: derived cells
are formulas that reflow, and they recalc without error.

The model formulas use only `+ - * / ( )` over cell refs and integer constants, so
the recalc is checked in-process with a tiny safe evaluator — no dependency. The
LibreOffice pass (RECALC=1 + `soffice`, set by the CI job) is an extra belt: it
opens the workbook, forces a recalculation, and asserts no formula errored.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "src", "api"))
sys.path.insert(0, os.path.join(ROOT, "evals"))

import pipeline as P  # noqa: E402
from deliverable.export import to_xlsx  # noqa: E402
from deliverable.xlsx_model import model_formulas  # noqa: E402

_ERR = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")
_FORMULA_OK = re.compile(r"^=[A-Z0-9.+\-*/() ]+$")
_REF = re.compile(r"[A-Z]{1,3}\d+")
_ARITH_OK = re.compile(r"^[\d.+\-*/() ]+$")


@pytest.fixture(scope="module")
def wb_bytes():
    return to_xlsx(P.run())


def _model_sheet(wb_bytes, data_only=False):
    from openpyxl import load_workbook
    return load_workbook(io.BytesIO(wb_bytes), data_only=data_only)["Model"]


def _sheet_cells(ws) -> dict:
    """coord -> raw value (a number, a '=formula' string, or other)."""
    return {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}


def _evaluate(formula, cells: dict, _seen=None) -> float:
    """Recalculate a formula (or return a literal), resolving cell refs recursively —
    a mini spreadsheet engine over the whitelisted arithmetic our model emits."""
    if isinstance(formula, (int, float)):
        return float(formula)
    if not (isinstance(formula, str) and formula.startswith("=")):
        return 0.0
    _seen = _seen or set()

    def _ref(m):
        coord = m.group(0)
        if coord in _seen:
            raise AssertionError(f"circular reference at {coord}")
        return repr(_evaluate(cells.get(coord, 0), cells, _seen | {coord}))

    expr = _REF.sub(_ref, formula[1:])
    assert _ARITH_OK.match(expr), f"non-arithmetic expression after ref substitution: {expr}"
    return eval(expr, {"__builtins__": {}}, {})  # noqa: S307 - whitelisted arithmetic only


def test_headline_chain_is_formulas_not_literals(wb_bytes):
    ws = _model_sheet(wb_bytes)
    rows = {r[0].value: r[2].value for r in ws.iter_rows(min_row=5) if r[0].value}
    assert isinstance(rows.get("F8"), str) and rows["F8"].startswith("=")   # run-rate roll-up
    assert isinstance(rows.get("F9"), str) and rows["F9"].startswith("=")   # annualisation
    assert _REF.search(rows["F8"]) and _REF.search(rows["F9"])              # over cell refs


def test_every_formula_is_excel_2007_safe(wb_bytes):
    ws = _model_sheet(wb_bytes)
    formulas = [c.value for row in ws.iter_rows() for c in row
                if isinstance(c.value, str) and c.value.startswith("=")]
    assert formulas
    for f in formulas:
        assert _FORMULA_OK.match(f), f"unsafe / non-Excel-2007 formula: {f}"


def test_modelled_figures_reproduce_their_stated_result():
    for m in model_formulas(P.run()):
        assert abs(m["expected"] - m["result"]) <= max(0.02, 0.01 * abs(m["result"])), m


def test_the_workbook_recalculates_to_the_estimator_totals(wb_bytes):
    ws = _model_sheet(wb_bytes)
    cells = _sheet_cells(ws)
    want = {m["figure_id"]: m["result"] for m in model_formulas(P.run())}
    rows = {r[0].value: r[2] for r in ws.iter_rows(min_row=5) if r[0].value}
    checked = 0
    for fid, res in want.items():
        cell = rows[fid]
        if isinstance(cell.value, str) and cell.value.startswith("="):
            got = _evaluate(cell.value, cells)
            assert abs(got - res) <= max(0.5, 0.01 * abs(res)), (fid, got, res)
            checked += 1
    assert checked >= 2 and {"F8", "F9"} <= set(want)


def test_changing_an_input_reflows_the_totals(wb_bytes):
    ws = _model_sheet(wb_bytes)
    cells = _sheet_cells(ws)
    rows = {r[0].value: r[2].value for r in ws.iter_rows(min_row=5) if r[0].value}
    base8, base9 = _evaluate(rows["F8"], cells), _evaluate(rows["F9"], cells)
    assert abs(base9 - base8 * 12) < 1e-3          # annual tracks monthly at baseline

    # bump the first grey input cell on F7's row (extras → rolls into F8 → into F9)
    f7_row = next(r for r in ws.iter_rows(min_row=5) if r[0].value == "F7")
    inp = next(c.coordinate for c in f7_row
               if isinstance(cells.get(c.coordinate), (int, float)) and c.column >= 7)
    cells[inp] += 1000
    new8, new9 = _evaluate(rows["F8"], cells), _evaluate(rows["F9"], cells)
    assert abs(new8 - (base8 + 1000)) < 1e-6       # +1000 in extras flows straight to the monthly total
    assert abs(new9 - new8 * 12) < 1e-3            # and the annual follows


# ---------------------------------------------------------------- LibreOffice
_soffice = shutil.which("soffice") or shutil.which("libreoffice")


@pytest.mark.skipif(os.environ.get("RECALC") != "1" or not _soffice,
                    reason="set RECALC=1 and install LibreOffice to run the recalc gate")
def test_libreoffice_recalc_has_no_errors(wb_bytes):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "estimate.xlsx")
        with open(src, "wb") as fh:
            fh.write(wb_bytes)
        outd = os.path.join(d, "out")
        os.makedirs(outd)
        subprocess.run([_soffice, "--headless", "--calc", "--convert-to",
                        "xlsx:Calc MS Excel 2007 XML", "--outdir", outd, src],
                       check=True, timeout=180, capture_output=True)
        from openpyxl import load_workbook
        wb = load_workbook(os.path.join(outd, "estimate.xlsx"), data_only=True)
        bad = [(ws.title, v) for ws in wb.worksheets
               for row in ws.iter_rows(values_only=True) for v in row
               if isinstance(v, str) and v in _ERR]
        assert not bad, f"LibreOffice recalc produced errors: {bad}"
