"""Unit tests for Microsoft Migration Execution Guide (MEG) integration (Epic E15.2)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/api is importable
_HERE = Path(__file__).resolve().parent
_SRC_API = _HERE.parent / "src" / "api"
if str(_SRC_API) not in sys.path:
    sys.path.insert(0, str(_SRC_API))

from meg import (  # noqa: E402
    build_governance_matrix,
    evaluate_readiness,
    generate_risk_register,
    load_all_meg,
    load_checklist,
    load_lifecycle,
    load_metadata,
    load_risks,
    load_roles,
    load_wave_guidance,
)


# ---------------------------------------------------------------------------
# Metadata & Reference Artifact Loading Tests
# ---------------------------------------------------------------------------

def test_meg_metadata_pinned_commit_and_license():
    meta = load_metadata()
    assert meta["source_repository"] == "https://github.com/Azure/migration"
    assert meta["source_commit_sha"] == "09b269375dc7c48cee7541e4ca16faf02b3897ca"
    assert meta["license"] == "MIT"
    assert "Microsoft" in meta["copyright"]


def test_meg_lifecycle_contains_6_phases():
    lc = load_lifecycle()
    phases = lc.get("phases", [])
    assert len(phases) == 6
    phase_ids = [p["id"] for p in phases]
    assert phase_ids == ["strategy", "plan", "ready", "adopt", "govern", "manage"]


def test_meg_checklist_covers_15_categories():
    chk = load_checklist()
    categories = chk.get("categories", [])
    assert len(categories) == 15
    items = chk.get("items", [])
    assert len(items) >= 20

    # Ensure every item has id, category, title, eval_key, and guidance
    for item in items:
        assert item["id"].startswith("MEG-")
        assert item["category"] in categories
        assert item["eval_key"] != ""
        assert item["title"] != ""


def test_meg_roles_and_raci_baseline():
    roles_def = load_roles()
    assert roles_def["notice"] == "DRAFT — CUSTOMER VALIDATION REQUIRED"
    roles = roles_def.get("standard_roles", [])
    assert len(roles) >= 8
    # Ensure all are functional roles, no individual names
    for r in roles:
        assert r["title"] != ""
        assert " " in r["title"] or len(r["title"]) >= 3


def test_meg_risks_taxonomy_and_matrix():
    risks_def = load_risks()
    assert "Observed Risk" in risks_def["classifications"]
    assert "Derived Risk" in risks_def["classifications"]
    matrix = risks_def["rating_matrix"]
    assert matrix["High:High"] == "Critical"
    assert matrix["Low:Low"] == "Low"


def test_meg_wave_guidance():
    wg = load_wave_guidance()
    assert "pilot_wave" in wg["guidance"]
    assert wg["guidance"]["pilot_wave"]["soak_period_days"] >= 7


def test_load_all_meg():
    all_data = load_all_meg()
    assert set(all_data.keys()) == {
        "metadata", "lifecycle", "checklist", "roles", "risks", "wave_guidance"
    }


# ---------------------------------------------------------------------------
# Third Party Notices Verification
# ---------------------------------------------------------------------------

def test_third_party_notices_exists_and_contains_mit_notice():
    notices_file = _HERE.parent / "THIRD_PARTY_NOTICES.md"
    assert notices_file.exists(), "THIRD_PARTY_NOTICES.md must exist in repo root"
    content = notices_file.read_text(encoding="utf-8")
    assert "Microsoft Azure Migration Execution Guide" in content
    assert "09b269375dc7c48cee7541e4ca16faf02b3897ca" in content
    assert "Copyright (c) Microsoft Corporation." in content
    assert "MIT License" in content


# ---------------------------------------------------------------------------
# Readiness Evaluation Model Tests (E15B.6)
# ---------------------------------------------------------------------------

def test_evaluate_readiness_over_populated_assessment():
    mock_outputs = {
        "inventory_summary": {"servers": 250, "applications": 31},
        "data_quality": {
            "confidence": "Medium",
            "findings": ["66 of 250 servers have no CPU/RAM utilisation history"],
        },
        "compute_cost": {
            "totals": {"monthly": 95000.0, "annual": 1140000.0},
            "region": "swedencentral",
        },
        "storage_cost": {
            "totals": {"monthly": 15000.0},
            "lines": [{"type": "sql_mi", "monthly": 5000.0}],
        },
        "landing_zone": {
            "management_groups": {"root": {}, "alz": {}},
            "spokes": [{"zone": "workload", "name": "spoke-app1"}],
            "connectivity": {"hub": "hub-vnet"},
            "checklist_summary": {"met": 18, "total": 20, "met_pct": 90},
        },
        "dispositions": {
            "dispositions": [
                {"app_id": "app-01", "app_name": "Billing", "disposition": "Rehost", "eol_servers": 0},
                {"app_id": "app-02", "app_name": "Legacy ERP", "disposition": "Rehost", "eol_servers": 2},
            ]
        },
        "waves": {
            "waves": [{"wave": "pilot", "servers": 10}, {"wave": "wave-1", "servers": 50}],
            "stale_dependencies_count": 3,
        },
        "schedule": {"waves": [{"wave": "pilot"}], "total_weeks": 26},
        "effort": {"peak_fte": 4.5, "avg_fte": 2.8},
        "discovery": {"cutover_window": "Weekends (Sat 22:00 - Sun 06:00)"},
        "run_rate_extras": {"total_monthly": 12000.0},
    }

    report = evaluate_readiness(mock_outputs)

    assert report["framework"] == "Microsoft Azure Migration Execution Guide (MEG)"
    assert "Aligned with the Microsoft Azure Migration Execution Guide reference" in report["notice"]

    summary = report["summary"]
    assert summary["ready"] > 0
    assert summary["partial"] > 0
    assert summary["total_items"] == len(report["items"])

    # Ensure no arbitrary percentage score is emitted
    assert "maturity_percentage" not in summary
    assert "readiness_percentage" not in summary

    # Verify specific items
    items_by_id = {it["id"]: it for it in report["items"]}

    # MEG-DISC-01 should be READY
    assert items_by_id["MEG-DISC-01"]["status"] == "READY"
    assert "250 servers" in items_by_id["MEG-DISC-01"]["evidence"]

    # MEG-DISC-02 should be PARTIAL because confidence is Medium
    assert items_by_id["MEG-DISC-02"]["status"] == "PARTIAL"
    assert "utilisation history" in items_by_id["MEG-DISC-02"]["evidence"]

    # MEG-LZ-02 should be READY because met_pct is 90%
    assert items_by_id["MEG-LZ-02"]["status"] == "READY"
    assert "90%" in items_by_id["MEG-LZ-02"]["evidence"]

    # MEG-PM-01 should be READY
    assert items_by_id["MEG-PM-01"]["status"] == "READY"
    assert "26 weeks" in items_by_id["MEG-PM-01"]["evidence"]


def test_evaluate_readiness_empty_outputs_fails_closed():
    report = evaluate_readiness({})
    summary = report["summary"]
    # With no outputs, items should be GAP or NOT_ASSESSED, not READY
    assert summary["ready"] == 0
    assert summary["gap"] > 0
    assert summary["not_assessed"] > 0


# ---------------------------------------------------------------------------
# Risk Register Tests (E15B.7)
# ---------------------------------------------------------------------------

def test_generate_risk_register_deterministic_triggers():
    mock_outputs = {
        "data_quality": {
            "confidence": "Medium",
            "findings": ["66 of 250 servers have no CPU/RAM utilisation history"],
        },
        "dispositions": {
            "dispositions": [
                {"app_id": "app-01", "app_name": "App1", "disposition": "Rehost", "eol_servers": 5},
                {"app_id": "app-02", "app_name": "DB1", "disposition": "Replatform", "database_engine": "SQL Server"},
            ]
        },
        "landing_zone": {"dr": {"strategy": "none"}},
        "waves": {"stale_dependencies_count": 4},
        "discovery": {"unanswered_required": ["compliance_scope", "rpo_minutes"]},
    }

    risks = generate_risk_register(mock_outputs)
    assert len(risks) >= 4

    risk_ids = [r["risk_id"] for r in risks]
    assert "RSK-001" in risk_ids  # Perf gap
    assert "RSK-002" in risk_ids  # EOL OS
    assert "RSK-003" in risk_ids  # Single region / no DR
    assert "RSK-004" in risk_ids  # DB replatform
    assert "RSK-005" in risk_ids  # Stale dependencies
    assert "RSK-006" in risk_ids  # Discovery gaps

    # Verify column structure
    for r in risks:
        assert r["classification"] in ("Observed Risk", "Derived Risk", "Generic MEG Check")
        assert r["probability"] in ("Low", "Medium", "High")
        assert r["impact"] in ("Low", "Medium", "High")
        assert r["rating"] in ("Low", "Medium", "High", "Critical")
        assert r["owner_role"] != ""
        assert r["evidence"] != ""


# ---------------------------------------------------------------------------
# Governance Matrix Tests (E15B.8)
# ---------------------------------------------------------------------------

def test_build_governance_matrix_raci():
    gov = build_governance_matrix("RACI")
    assert gov["notice"] == "DRAFT — CUSTOMER VALIDATION REQUIRED"
    assert gov["methodology"] == "RACI"
    assert "Strategy" in gov["matrix"]
    assert "Lead Cloud Architect" in gov["matrix"]["Ready Landing Zone"]
    assert gov["matrix"]["Ready Landing Zone"]["Lead Cloud Architect"] == "A"


def test_build_governance_matrix_daci():
    gov = build_governance_matrix("DACI")
    assert gov["notice"] == "DRAFT — CUSTOMER VALIDATION REQUIRED"
    assert gov["methodology"] == "DACI"
    assert "disposition_decision" in gov["matrix"]
    assert gov["matrix"]["disposition_decision"]["approver"] == "Application Owner / SME"
