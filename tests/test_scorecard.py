"""C32 / E10.6 — evidence/SCORECARD.md: the rubric stays current and honest."""
import os
import sys

from conftest import ROOT

sys.path[:0] = [os.path.join(ROOT, "evidence")]

from scorecard import build, rubric, _live, _md      # noqa: E402

_NINE = {"Correctness", "Defensibility", "Completeness", "Robustness", "Usability",
         "Understandability", "Operability", "Security", "Reliability"}


def test_all_nine_dimensions_present():
    rows = build()["rows"]
    assert {r["dim"] for r in rows} == _NINE


def test_overall_is_the_mean_and_in_range():
    sc = build()
    assert 0 <= sc["overall"] <= 5
    assert abs(sc["overall"] - sum(r["score"] for r in sc["rows"]) / 9) < 0.01


def test_every_dimension_below_five_names_a_gap():
    for r in build()["rows"]:
        if r["score"] < 5.0:
            assert r["gap"], f"{r['dim']} is < 5 but has no stated gap"
        assert r["evidence"], f"{r['dim']} cites no evidence"


def test_live_pulls_reflect_the_finished_artefacts():
    live = _live()
    assert live["backtest"].get("pass") is True, live["backtest"]
    assert live["broken_dumps"].get("pass") is True, live["broken_dumps"]
    assert live["evals"].get("overall") == "PASS", live["evals"]
    # the done dimensions score 5 because their artefacts pass
    scores = {r["dim"]: r["score"] for r in rubric(live)}
    assert scores["Correctness"] == 5.0
    assert scores["Robustness"] == 5.0
    assert scores["Reliability"] == 5.0


def test_evidence_links_resolve():
    root = ROOT
    for r in build()["rows"]:
        for _label, path in r["evidence"]:
            # links are relative to evidence/
            target = os.path.normpath(os.path.join(root, "evidence", path))
            assert os.path.exists(target), f"broken evidence link: {path}"


def test_scorecard_md_is_current():
    path = os.path.join(ROOT, "evidence", "SCORECARD.md")
    with open(path, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert on_disk == _md(build()), \
        "stale evidence/SCORECARD.md — run `python evidence/scorecard.py`"
