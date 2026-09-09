"""E9 chaos drill — the degradation mitigations for scenarios.md stay in place."""
import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "evidence", "chaos"))
import probe  # noqa: E402


def test_probe_reports_all_mitigations_in_place(monkeypatch):
    # no azd/az in the test env -> the *-live checks are simply absent
    monkeypatch.setattr(probe, "_az_json", lambda *a, **k: None)
    monkeypatch.setattr(probe, "_cfg", lambda: {})
    res = probe.run()
    by = {c["scenario"]: c for c in res["checks"]}
    for sid in ("C1", "C2", "C3", "C4", "C5", "C6"):
        assert by[sid]["mitigation_in_place"], (sid, by[sid]["detail"])
    assert res["all_mitigations_in_place"]


def test_scenarios_and_results_documents_exist():
    for f in ("scenarios.md", "RESULTS.md", "probe.py"):
        assert os.path.exists(os.path.join(ROOT, "evidence", "chaos", f))
    txt = open(os.path.join(ROOT, "evidence", "chaos", "scenarios.md"), encoding="utf-8").read()
    assert txt.count("| C") >= 6                       # six numbered failure modes
    assert "never a wrong answer" in txt


def test_probe_catches_a_removed_mitigation(monkeypatch, tmp_path):
    """If someone drops the SQL-resume retry, C1 must fail."""
    real_src = probe._src

    def _src(path):
        if path == "src/api/tools.py":
            return "def query_inventory(): pass  # no retry here"
        return real_src(path)

    monkeypatch.setattr(probe, "_src", _src)
    monkeypatch.setattr(probe, "_az_json", lambda *a, **k: None)
    monkeypatch.setattr(probe, "_cfg", lambda: {})
    res = probe.run()
    c1 = next(c for c in res["checks"] if c["scenario"] == "C1")
    assert not c1["mitigation_in_place"]
    assert not res["all_mitigations_in_place"]
