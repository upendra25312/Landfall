"""C31 / E10.2 — the broken-dump corpus: every damaged file handled per E1.4."""
import os
import sys

import pytest
from conftest import ROOT

sys.path[:0] = [os.path.join(ROOT, "evidence", "broken-dumps")]

from check import run                                    # noqa: E402


_RES = run()
_CASES = [(r["file"], r) for r in _RES["results"]]


def test_corpus_has_at_least_six_files():
    assert _RES["corpus_size"] >= 6


@pytest.mark.parametrize("name,r", _CASES, ids=[c[0] for c in _CASES])
def test_each_dump_is_handled_per_e14(name, r):
    # E1.4: not loaded (unrecognised/rejected) OR loaded with the gap named — never silent
    assert r["ok"], (r["actual_status"], r["checks"], r["missing_phrases"])
    if r["actual_status"] in ("unrecognised", "rejected"):
        assert r["rows_loaded"] == 0
    else:
        assert r["findings"], "a degraded load must carry at least one finding"


def test_all_handled():
    assert _RES["all_handled"]


def test_results_md_is_current():
    from check import _md
    path = os.path.join(ROOT, "evidence", "broken-dumps", "RESULTS.md")
    with open(path, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert on_disk == _md(run()), "stale RESULTS.md — run `python evidence/broken-dumps/check.py`"
