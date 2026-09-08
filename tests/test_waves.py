"""Cycle 8 — score_dispositions (E4.2) + plan_waves (E4.1). Deterministic, pure."""
import csv
import io

from conftest import sample_bytes

from cost.config import load_config
from waves.disposition import score_dispositions, score_one
from waves.plan import plan_waves


def _cfg(**over):
    return load_config(overrides=over or None)


# --- disposition ------------------------------------------------------

def test_no_servers_scores_retire():
    r = score_one({"app_id": "x", "app_name": "Orphan", "criticality": 3}, {"servers": 0}, _cfg())
    assert r["disposition"] == "Retire" and r["confidence"] == "high"


def test_retire_marker():
    r = score_one({"app_id": "x", "app_name": "Analytics Sandbox", "criticality": 4},
                  {"servers": 2}, _cfg())
    assert r["disposition"] == "Retire" and r["needs_human_decision"]


def test_paas_db_small_low_crit_replatforms():
    r = score_one({"app_id": "x", "app_name": "Marketing", "criticality": 3,
                   "db_engine": "PostgreSQL 13", "tech_stack": "Django; PostgreSQL 13"},
                  {"servers": 2, "eol_servers": 0}, _cfg())
    assert r["disposition"] == "Replatform"
    assert "PostgreSQL" in " ".join(r["rationale"])


def test_clustered_db_stays_rehost_iaas():
    r = score_one({"app_id": "x", "app_name": "Order Mgmt", "criticality": 1,
                   "db_engine": "SQL Server 2019",
                   "tech_stack": "SQL Server 2019 Always On AG; IIS"},
                  {"servers": 4, "eol_servers": 0}, _cfg())
    assert r["disposition"] == "Rehost"
    assert any("cluster" in x.lower() for x in r["rationale"])


def test_tier1_paas_candidate_still_rehost_but_notes_alternative():
    r = score_one({"app_id": "x", "app_name": "Payments", "criticality": 1,
                   "db_engine": "PostgreSQL 13", "tech_stack": "Spring Boot; PostgreSQL 13"},
                  {"servers": 3}, _cfg())
    assert r["disposition"] == "Rehost"
    assert any("Replatform" in a for a in r["alternatives"])


def test_aggressive_appetite_lets_tier1_replatform():
    app = {"app_id": "x", "app_name": "Payments", "criticality": 1,
           "db_engine": "PostgreSQL 13", "tech_stack": "Spring Boot; PostgreSQL 13"}
    r = score_one(app, {"servers": 3}, _cfg(disposition={"appetite": "aggressive"}))
    assert r["disposition"] == "Replatform"


def test_eol_os_noted_on_rehost():
    r = score_one({"app_id": "x", "app_name": "Legacy CRM", "criticality": 2},
                  {"servers": 5, "eol_servers": 3}, _cfg())
    assert r["disposition"] == "Rehost"
    assert any("end-of-support" in x for x in r["rationale"])


def test_disposition_summary_over_sample():
    apps = _apps()
    roll = {a["app_id"]: {"servers": 4, "eol_servers": 1} for a in apps}
    r = score_dispositions(apps, roll, load_config())
    assert r["summary"]["applications"] == len(apps)
    assert sum(r["summary"]["by_disposition"].values()) == len(apps)
    assert r["summary"]["by_disposition"].get("Rehost", 0) >= 1


# --- waves --------------------------------------------------------

def test_chatty_apps_land_in_one_move_group():
    apps = [{"app_id": "a", "criticality": 3}, {"app_id": "b", "criticality": 3},
            {"app_id": "c", "criticality": 3}]
    servers = [{"server_id": "s1", "app_id": "a"}, {"server_id": "s2", "app_id": "b"},
               {"server_id": "s3", "app_id": "c"}]
    deps = [{"src_id": "s1", "dst_id": "s2", "confidence": "high",
             "last_seen": "2026-09-06", "flows_30d": 1000}]
    r = plan_waves(apps, servers, deps, _cfg(waves={"observation_window_end": "2026-09-07"}))
    groups = {g["group_id"]: set(g["apps"]) for g in r["move_groups"]}
    assert any({"a", "b"} <= s for s in groups.values())
    assert any(s == {"c"} for s in groups.values())


def test_stale_and_low_confidence_edges_excluded():
    apps = [{"app_id": "a", "criticality": 3}, {"app_id": "b", "criticality": 3}]
    servers = [{"server_id": "s1", "app_id": "a"}, {"server_id": "s2", "app_id": "b"}]
    deps = [{"src_id": "s1", "dst_id": "s2", "confidence": "high",
             "last_seen": "2026-01-01", "flows_30d": 5}]           # 8 months stale
    r = plan_waves(apps, servers, deps, _cfg(waves={"observation_window_end": "2026-09-07"}))
    assert r["graph"]["stale_edges_excluded"] == 1
    assert r["graph"]["app_edges"] == 0


def test_regulated_group_is_last_and_pilot_is_first():
    apps = [
        {"app_id": "reg", "criticality": 1, "compliance_scope": "PCI-DSS", "internet_facing": 1},
        {"app_id": "easy", "criticality": 4, "compliance_scope": ""},
        {"app_id": "mid", "criticality": 2, "compliance_scope": ""},
    ]
    servers = [{"server_id": f"s{i}", "app_id": a["app_id"]} for i, a in enumerate(apps)]
    r = plan_waves(apps, servers, [], _cfg())
    assert r["waves"][0]["kind"] == "pilot"
    assert "easy" in r["waves"][0]["apps"]
    last = r["waves"][-1]
    assert "reg" in last["apps"]
    assert r["waves"][-1]["risk_score"] >= r["waves"][0]["risk_score"]


def test_wave_server_cap_splits_into_multiple_waves():
    apps = [{"app_id": f"a{i}", "criticality": 3} for i in range(6)]
    servers = [{"server_id": f"s{i}-{j}", "app_id": f"a{i}"} for i in range(6) for j in range(15)]
    r = plan_waves(apps, servers, [], _cfg(waves={"max_servers_per_wave": 30, "max_apps_per_wave": 6}))
    assert len(r["waves"]) >= 3
    assert all(wv["server_count"] <= 30 or len(wv["groups"]) == 1 for wv in r["waves"])


def test_dropped_edge_surfaces_as_soft_blocking_dependency():
    apps = [{"app_id": "front", "criticality": 3}, {"app_id": "back", "criticality": 1,
            "compliance_scope": "PCI-DSS", "internet_facing": 1}]
    servers = [{"server_id": "f1", "app_id": "front"}, {"server_id": "b1", "app_id": "back"}]
    # low-confidence edge, dropped from grouping (min=medium) -> front & back split
    # (back is regulated -> last wave); the dropped edge is still surfaced.
    deps = [{"src_id": "f1", "dst_id": "b1", "confidence": "low",
             "last_seen": "2026-09-06", "flows_30d": 200}]
    r = plan_waves(apps, servers, deps, _cfg(waves={"observation_window_end": "2026-09-07",
                                                    "min_edge_confidence": "medium"}))
    assert r["graph"]["app_edges"] == 0                       # edge was dropped from the graph
    blocks = [b for wv in r["waves"] for b in wv["blocking_dependencies"]]
    assert any(b["app"] == "front" and b["depends_on"] == "back"
               and "unverified" in b["confidence"] for b in blocks)


def test_deterministic_over_sample_estate():
    apps = _apps()
    servers = list(csv.DictReader(io.StringIO(sample_bytes("servers.csv").decode("utf-8-sig"))))
    deps = list(csv.DictReader(io.StringIO(sample_bytes("dependencies.csv").decode("utf-8-sig"))))
    a = plan_waves(apps, servers, deps, load_config())
    b = plan_waves(apps, servers, deps, load_config())
    assert a == b
    kinds = [wv["kind"] for wv in a["waves"]]
    assert kinds[0] == "platform" and "pilot" in kinds       # app-31 is shared-infra
    assert kinds.index("pilot") == 1
    assert a["waves"][-1]["risk_score"] >= a["waves"][1]["risk_score"]  # risk rises after the pilot
    assert a["graph"]["app_nodes"] == len(apps)
    assert a["graph"]["platform_apps"] == ["app-31"]


def _apps():
    return list(csv.DictReader(io.StringIO(sample_bytes("applications.csv").decode("utf-8-sig"))))
