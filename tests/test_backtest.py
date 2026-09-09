"""C30 / E10.1 — the cost-method back-test: three methods converge on every estate."""
import os
import sys

import pytest
from conftest import ROOT

sys.path[:0] = [os.path.join(ROOT, "evidence", "backtest")]

from backtest import TOLERANCE, run                      # noqa: E402
from estate_gen import PRESETS, build_estate, estate_profile  # noqa: E402
from methods import price_all                            # noqa: E402
from pricebook import books                              # noqa: E402
from cost.config import load_config                      # noqa: E402


def test_all_three_estates_converge_within_tolerance():
    res = run()
    assert res["all_within_tolerance"], [
        (e["preset"], e["spread_pct"]) for e in res["estates"] if not e["within_tolerance"]]
    assert {e["preset"] for e in res["estates"]} == set(PRESETS)


@pytest.mark.parametrize("preset", PRESETS)
def test_methods_are_ordered_and_close(preset):
    cfg = load_config()
    est = build_estate(preset)
    ms = {m["method"]: m for m in price_all(est, cfg, books())}
    assert set(ms) == {"engine", "blended", "bands"}
    # every method is a positive monthly number and the engine is not the outlier low
    vals = {k: v["monthly"] for k, v in ms.items()}
    assert all(v > 0 for v in vals.values())
    assert vals["engine"] >= min(vals.values())
    spread = (max(vals.values()) - min(vals.values())) / sorted(vals.values())[1]
    assert spread <= TOLERANCE


def test_deterministic():
    a, b = run(), run()
    assert [e["methods"] for e in a["estates"]] == [e["methods"] for e in b["estates"]]


def test_estate_shapes_are_distinct():
    profs = [estate_profile(build_estate(p)) for p in PRESETS]
    sizes = sorted(p["servers"] for p in profs)
    assert sizes[0] < sizes[1] < sizes[2]
    assert profs[0]["compliance"] == [] and profs[-1]["compliance"]


def test_results_md_is_current():
    """RESULTS.md must match a fresh run (CI drift gate, mirrors evals/SCORECARD.md)."""
    from backtest import _md
    path = os.path.join(ROOT, "evidence", "backtest", "RESULTS.md")
    with open(path, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert on_disk == _md(run()), "stale RESULTS.md — run `python evidence/backtest/backtest.py`"
