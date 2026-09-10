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


def test_fault_injection_every_tool_fails_cleanly():
    f = runner.run_faults(verbose=False)
    assert f["total"] >= 20
    failed = [(r["tool"], r["body"], r["detail"]) for r in f["results"] if not r["ok"]]
    assert f["passed"] == f["total"], f"tools that leaked on a bad request: {failed}"


def test_adversarial_guardrails_all_hold():
    a = runner.run_adversarial(verbose=False)
    assert a["total"] >= 60, "adversarial suite shrank unexpectedly (E13.3)"
    failed = [(r["category"], r["case"], r["detail"]) for r in a["results"] if not r["ok"]]
    assert a["passed"] == a["total"], f"guardrail regressions: {failed}"


def test_adversarial_covers_every_category():
    a = runner.run_adversarial(verbose=False)
    cats = {r["category"] for r in a["results"]}
    assert {"sql-guard", "engagement-isolation", "path-traversal",
            "upload-content", "output-guard", "system-prompt"} <= cats


def test_output_guard_flags_an_unsourced_number():
    from output_guard import check_message
    sourced = [119181, 833.7, 650286]
    assert check_message("Run-rate is $119,181/mo per the tool (F8).", sourced)["ok"]
    bad = check_message("Expect around $2,400,000/year once you add buffer.", sourced)
    assert not bad["ok"] and any("2,400,000" in v["claim"] for v in bad["violations"])


def test_output_guard_passes_a_real_package_render():
    from output_guard import check_message, sourced_from_package
    pkg = __import__("pipeline").run()
    r = check_message(pkg["summary_markdown"], sourced_from_package(pkg))
    assert r["ok"], f"assemble_estimate render has un-sourced numbers: {r['violations']}"


def test_scorecard_renders():
    card = runner.scorecard(runner.run_golden(verbose=False), runner.run_scenarios(verbose=False),
                            runner.run_faults(verbose=False), runner.run_adversarial(verbose=False))
    assert "Landfall eval scorecard" in card and "Overall" in card and "Fault injection" in card
    assert "Adversarial guardrails" in card
