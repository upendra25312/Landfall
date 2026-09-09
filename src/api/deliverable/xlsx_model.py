"""Turn the estimate's calculation appendix into a *live* Excel model (PRD E11.12 /
E5.4q): derived cells are formulas over their inputs — and, where an input equals
another figure's result, over that figure's cell — so changing an input reflows
the headline totals. Excel-2007 function set only (SUM + arithmetic).

The mapping is deterministic and prose-free: for each figure we test the numeric
relationship between its ``inputs`` and its stated ``result`` (sum / product /
constant multiple) rather than parsing the human ``formula`` string. A figure
whose result isn't reproduced by its inputs is written as a checked literal.
"""
from __future__ import annotations

_TOL = 0.01          # relative tolerance for "these numbers add up"
_ABS = 0.02


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(_ABS, _TOL * max(abs(a), abs(b)))


def _same(a: float, b: float) -> bool:
    """Near-exact: is `a` *the same number* as `b` (a figure's result), not merely
    within a modelling tolerance."""
    return abs(a - b) <= max(0.5, 1e-4 * abs(b))


def _flat_inputs(inputs) -> dict[str, float]:
    """The numeric, top-level entries of an appendix `inputs` dict, minus the ones
    that are context not operands."""
    if not isinstance(inputs, dict):
        return {}
    skip = {"block_excluded", "servers", "region", "reserved_term", "price_date",
            "contingency_pct", "pm_pct", "governance_pct"}
    return {k: float(v) for k, v in inputs.items() if _num(v) and k not in skip}


def _relation(vals: list[float], result: float):
    """('sum'|'product'|('mul', k)|None) — how `vals` combine to `result`."""
    if not vals:
        return None
    if _close(sum(vals), result):
        return "sum"
    prod = 1.0
    for v in vals:
        prod *= v
    if len(vals) >= 2 and _close(prod, result):
        return "product"
    if len(vals) == 1 and vals[0]:
        k = result / vals[0]
        if _close(k, round(k)) and 1 <= round(k) <= 60:
            return ("mul", int(round(k)))
    return None


def write_model_sheet(wb, package: dict) -> "object | None":
    """Add a 'Model' sheet. Returns the worksheet, or None if there is nothing to model."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    appendix = package.get("calculation_appendix") or []
    if not appendix:
        return None

    ws = wb.create_sheet("Model")
    bold = Font(bold=True)
    ws["A1"] = "Live calculation model"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = ("Grey input cells are editable; the Result column recalculates. "
                "Figures reference each other where a value is another figure's result.")
    ws["A2"].font = Font(italic=True, size=9)

    hdr = ["Ref", "Figure", "Result", "Unit", "Basis", "Inputs →"]
    r0 = 4
    for c, h in enumerate(hdr, 1):
        ws.cell(row=r0, column=c, value=h).font = bold

    result_cell: dict[str, str] = {}     # figure_id -> "C7"
    result_val: dict[str, float] = {}
    row = r0 + 1
    for a in appendix:
        fid = a.get("figure_id")
        res = a.get("result")
        ws.cell(row=row, column=1, value=fid)
        ws.cell(row=row, column=2, value=a.get("label"))
        ws.cell(row=row, column=4, value=a.get("unit"))
        ws.cell(row=row, column=5, value=a.get("formula") or "")

        flat = _flat_inputs(a.get("inputs"))
        rel = _relation(list(flat.values()), res) if _num(res) else None

        if rel is None or not flat:
            ws.cell(row=row, column=3, value=res)      # checked literal
            result_cell[fid] = f"C{row}"
            if _num(res):
                result_val[fid] = float(res)
            row += 1
            continue

        # lay the operands out across the row; reference another figure's Result
        # cell when this input *is* that figure's result.
        refs: list[str] = []
        col = 7
        for name, val in flat.items():
            ref_fig = next((g for g, gv in result_val.items() if _same(gv, val)), None)
            if ref_fig:
                refs.append(result_cell[ref_fig])
                ws.cell(row=row, column=col, value=f"{name} = {ref_fig}")
            else:
                ws.cell(row=row, column=col, value=name)
                ws.cell(row=row, column=col + 1, value=val)
                cell = ws.cell(row=row, column=col + 1)
                from openpyxl.styles import PatternFill
                cell.fill = PatternFill("solid", fgColor="EFEFEF")
                refs.append(f"{get_column_letter(col + 1)}{row}")
            col += 2

        if rel == "sum":
            formula = "=" + "+".join(refs)
        elif rel == "product":
            formula = "=" + "*".join(refs)
        else:                                          # ("mul", k)
            formula = f"={refs[0]}*{rel[1]}"
        ws.cell(row=row, column=3, value=formula)
        result_cell[fid] = f"C{row}"
        if _num(res):
            result_val[fid] = float(res)
        row += 1

    for c in range(1, 7):
        ws.column_dimensions[get_column_letter(c)].width = [7, 46, 16, 8, 34, 16][c - 1]
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
    return ws


def model_formulas(package: dict) -> list[dict]:
    """Same mapping, as data — for the recalc/consistency test. Each entry:
    {figure_id, result, kind, operands:[float], expected:float}."""
    out = []
    for a in package.get("calculation_appendix") or []:
        res = a.get("result")
        if not _num(res):
            continue
        flat = _flat_inputs(a.get("inputs"))
        rel = _relation(list(flat.values()), res)
        if rel is None or not flat:
            continue
        vals = list(flat.values())
        if rel == "sum":
            expected = sum(vals)
        elif rel == "product":
            p = 1.0
            for v in vals:
                p *= v
            expected = p
        else:
            expected = vals[0] * rel[1]
        out.append({"figure_id": a.get("figure_id"), "result": float(res),
                    "kind": rel if isinstance(rel, str) else "mul",
                    "operands": vals, "expected": expected})
    return out
