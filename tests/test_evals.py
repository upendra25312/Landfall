"""Cycle 10 — eval harness gate (E7.1 / E7.2). Wraps evals/runner.py so CI catches
regressions. The runner itself is the source of truth (`python evals/runner.py`)."""
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "evals"))

runner = pytest.importorskip("runner")


def test_golden_sql_exact_match_gate():
    g = runner.run_golden(verbose=False)
    assert g["total"] >= 30, "need at least 30 golden queries (E7.1)"
    failed = [r["id"] for r in g["results"] if not (r["match"] and r["guard_ok"])]
    assert g["rate"] >= runner.GOLDEN_GATE, f"exact-match {g['rate']:.0%} < gate; failed {failed}"


def test_every_golden_query_passes_the_select_guard():
    g = runner.run_golden(verbose=False)
    rejected = [r["id"] for r in g["results"] if not r["guard_ok"]]
    assert not rejected, f"tools._safe_select rejected golden queries: {rejected}"


def test_full_estimate_scenarios_all_pass():
    s = runner.run_scenarios(verbose=False)
    assert s["total"] >= 8, "need at least 8 scenarios (E7.2)"
    failed = [(r["id"], [c for c in r["checks"] if not c[1]]) for r in s["results"] if not r["ok"]]
    assert s["passed"] == s["total"], f"scenario failures: {failed}"


def test_scorecard_renders():
    card = runner.scorecard(runner.run_golden(verbose=False), runner.run_scenarios(verbose=False))
    assert "Landfall eval scorecard" in card and "Overall" in card
