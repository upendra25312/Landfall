"""Cycle 1 — data-quality report: it must name every defect and nothing spurious."""
from conftest import fixture_bytes, sample_bytes

from ingest.core import normalize
from ingest.dq import build_report, render_markdown


def test_broken_dump_flags_dupes_gaps_and_unmapped_columns():
    res = normalize("broken_servers.csv", fixture_bytes("broken_servers.csv"))
    rep = build_report([res])
    t = rep["tables"]["servers"]

    assert "srv-0001" in t["duplicate_keys"]
    assert t["unmapped_headers"] == ["rack_location"]
    assert t["null_rate"]["vcpu"] > 0                 # one blank vcpu
    assert t["null_rate"]["ram_gb"] > 0               # one blank ram
    assert t["no_perf_data"] == len(res.rows)         # no perf columns at all
    assert rep["confidence_hint"] in ("Low", "Medium")

    md = render_markdown(rep)
    assert "duplicate keys" in md.lower()
    assert "utilisation history" in md.lower()


def test_clean_sample_estate_is_medium_confidence_and_names_the_perf_gap():
    results = [
        normalize(f, sample_bytes(f))
        for f in ("servers.csv", "applications.csv", "dependencies.csv", "storage.csv")
    ]
    rep = build_report(results)
    # ~26% of the synthetic estate has no vCenter perf history -> not High, not Low
    assert rep["confidence_hint"] == "Medium"
    assert any("utilisation history" in f for f in rep["findings"])
    assert "servers" in rep["tables"] and rep["tables"]["servers"]["rows_normalised"] == 250


def test_orphan_app_id_is_reported_when_the_portfolio_is_missing():
    res = normalize("servers.csv", sample_bytes("servers.csv"))
    rep = build_report([res])                          # servers only, no applications file
    orphans = rep["tables"]["servers"]["orphan_app_id"]
    assert orphans                                     # every non-null app_id is unmatched
    assert any("upload the application portfolio" in f for f in rep["findings"])


def test_missing_dependencies_is_called_out():
    res = normalize("servers.csv", sample_bytes("servers.csv"))
    rep = build_report([res])
    assert any("No dependency data loaded" in f for f in rep["findings"])


def test_unrecognised_file_appears_in_the_report():
    res = normalize("mystery.csv", fixture_bytes("unknown.csv"))
    rep = build_report([res])
    assert "_unrecognised" in rep["tables"]
    assert any("could not be recognised" in f for f in rep["findings"])
    assert rep["confidence_hint"] == "Low"
