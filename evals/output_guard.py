"""
Output guard (PRD E7.4) — flag any numeric claim in an assistant message that is
not backed by a tool result or a citation.

    from output_guard import check_message
    r = check_message(text, sourced_values=[119181, 833.7, ...])
    if not r["ok"]: ...   # r["violations"] lists the un-sourced claims

Heuristic, deliberately conservative: it only challenges numbers that read as
*claims* — money, percentages, counts with a unit, or magnitudes >= 1000 / scale
words (million, k). A number is allowed when it (a) matches a tool-sourced value
within tolerance, (b) sits in a line that carries a citation (a figure id like F7,
a tool name, "appendix", "per the tool"), or (c) is an obvious structural number
(a short ordinal / list index). Everything else is a violation.
"""
from __future__ import annotations

import re

_CITE = re.compile(
    r"\bF\d+\b|\bS\d+\b|\b[AXG]\d+\b|\bappendix\b|\bfigure\b|\bregister\b|per the tool|"
    r"\bassum|\bbasis\b|contingenc|\bexcludes?\b|\bPM \d|governance|reserved|coverage|"
    r"\b(?:query_inventory|vm_rightsize|estimate_compute_cost|estimate_storage_cost|"
    r"estimate_run_rate_extras|design_landing_zone|score_dispositions|plan_waves|"
    r"assemble_estimate|azure_retail_prices)\b",
    re.IGNORECASE,
)

# a number that looks like a claim: optional $, digits/commas, optional decimals,
# optional scale/unit suffix.
_NUM = re.compile(
    r"(?P<cur>[$€£]\s?)?"
    r"(?P<val>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<suf>million|billion|thousand|bn|mn|[MBKk]\b|%|PD\b|person-days?|vCPU\b|"
    r"servers?\b|GB\b|TB\b|/mo\b|/month\b|/yr\b|/year\b)?",
    re.IGNORECASE,
)
_SCALE = {"million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
          "thousand": 1e3, "k": 1e3}
_STRUCTURAL_MAX = 32          # bare small integers (step 3, 8 sections) are structural


def _norm_sourced(values) -> list[float]:
    out = []
    for v in values or []:
        try:
            out.append(abs(float(v)))
        except (TypeError, ValueError):
            continue
    return out


def _claim_value(m: re.Match) -> float | None:
    raw = m.group("val").replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    suf = (m.group("suf") or "").lower().strip()
    if suf in _SCALE:
        val *= _SCALE[suf]
    return val


def _is_claim(m: re.Match) -> bool:
    suf = (m.group("suf") or "").lower().strip()
    if m.group("cur") or suf:
        return True
    val = _claim_value(m)
    return val is not None and val >= 1000


_DATEISH = re.compile(r"\d{4}-\d{2}|\b(19|20)\d{2}\b")


def check_message(text: str, sourced_values=None, tolerance: float = 0.02) -> dict:
    sourced = _norm_sourced(sourced_values)
    violations = []
    for line in (text or "").splitlines():
        line_cited = bool(_CITE.search(line))
        for m in _NUM.finditer(line):
            if not _is_claim(m):
                continue
            # skip dates / years (not numeric claims)
            around = line[max(0, m.start() - 5):m.end() + 5]
            if _DATEISH.search(m.group(0)) or re.search(r"\d{4}-\d{2}", around):
                continue
            val = _claim_value(m)
            if val is None:
                continue
            if val <= _STRUCTURAL_MAX and not m.group("cur") and not (m.group("suf") or "").strip():
                continue
            if line_cited:
                continue
            if any(abs(val - s) <= max(tolerance * max(val, s), 0.5) for s in sourced):
                continue
            # also accept a rounded match (e.g. "$1.4M" vs 1,430,167)
            if any(_rounded_match(val, s) for s in sourced):
                continue
            violations.append({"claim": m.group(0).strip(), "line": line.strip()[:160]})
    return {"ok": not violations, "violations": violations}


def _rounded_match(a: float, b: float) -> bool:
    """True when `a` is a plausible rounded quote of `b` — e.g. "$1.4M" for
    1,430,167. Just a slightly looser relative tolerance than the exact check."""
    if b == 0:
        return a == 0
    return abs(a - b) / b <= 0.03


def _walk_numbers(obj, out: list):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_numbers(v, out)


def sourced_from_package(package: dict) -> list[float]:
    """Every number a Landfall estimate package legitimately produced — figures,
    the calculation appendix, and everything the section bodies render."""
    vals: list[float] = []
    _walk_numbers(package.get("figures"), vals)
    _walk_numbers(package.get("calculation_appendix"), vals)
    for s in package.get("sections", []):
        _walk_numbers(s.get("body"), vals)
    # numbers embedded in register / assumption prose are self-citing but harvest
    # them too as a backstop
    for cat in ("assumptions", "exclusions", "data_gaps"):
        for i in package.get("register", {}).get(cat, []):
            for tok in re.findall(r"\d+(?:\.\d+)?", i.get("text", "")):
                vals.append(float(tok))
    return [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
