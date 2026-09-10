"""C29 / E4.3 — build_schedule: the wave plan -> a dated schedule + critical path."""
import csv
import io

from conftest import sample_bytes

from cost.config import load_config
from waves.plan import plan_waves
from waves.schedule import build_schedule


def _cfg(**over):
    return load_config(overrides=over or None)


def _plan(**wave_over):
    apps = list(csv.DictReader(io.StringIO(sample_bytes("applications.csv").decode("utf-8-sig"))))
    servers = list(csv.DictReader(io.StringIO(sample_bytes("servers.csv").decode("utf-8-sig"))))
    deps = list(csv.DictReader(io.StringIO(sample_bytes("dependencies.csv").decode("utf-8-sig"))))
    return plan_waves(apps, servers, deps, _cfg(**wave_over), start_date="2026-01-05")


def test_plan_waves_attaches_a_schedule():
    p = _plan()
    s = p["schedule"]
    assert s["start"] == "2026-01-05"
    assert s["end"] > s["start"]
    assert len(s["waves"]) == len(p["waves"])
    assert s["total_weeks"] > 0


def test_each_wave_has_dates_and_a_duration():
    s = _plan()["schedule"]
    for w in s["waves"]:
        assert w["prep_start"] <= w["exec_start"] < w["go_live"] <= w["soak_end"]
        assert w["duration_weeks"] == w["prep_weeks"] + w["exec_weeks"] + w["soak_weeks"]


def test_bigger_wave_takes_longer():
    cfg = _cfg(schedule={"throughput_servers_per_week": 10, "min_wave_weeks": 1})
    plan = plan_waves(
        [{"app_id": "a", "criticality": 3}, {"app_id": "b", "criticality": 3}],
        [{"server_id": f"s{i}", "app_id": "a"} for i in range(50)]
        + [{"server_id": f"t{i}", "app_id": "b"} for i in range(5)],
        [], cfg, start_date="2026-01-05")
    big = max(plan["schedule"]["waves"], key=lambda w: w["servers"])
    small = min(plan["schedule"]["waves"], key=lambda w: w["servers"])
    assert big["exec_weeks"] > small["exec_weeks"]


def test_sequential_critical_path_is_every_wave():
    s = _plan()["schedule"]
    assert [c["wave"] for c in s["critical_path"]] == [w["wave"] for w in s["waves"]]
    assert all(c.get("reason") for c in s["critical_path"])


def test_parallel_waves_shorten_the_programme():
    p1 = plan_waves(*_inputs(), _cfg(schedule={"parallel_waves": 1}), start_date="2026-01-05")
    p2 = plan_waves(*_inputs(), _cfg(schedule={"parallel_waves": 3}), start_date="2026-01-05")
    assert p2["schedule"]["total_weeks"] <= p1["schedule"]["total_weeks"]
    assert p2["schedule"]["parallel_waves"] == 3


def test_blackout_window_pushes_a_wave():
    base = plan_waves(*_inputs(), _cfg(), start_date="2026-01-05")["schedule"]
    bo = plan_waves(*_inputs(),
                    _cfg(schedule={"blackout_windows": [
                        {"name": "year-end freeze", "start": "2026-02-01", "end": "2026-04-01"}]}),
                    start_date="2026-01-05")["schedule"]
    assert bo["end"] > base["end"]
    assert any(w["blackout_shift"] for w in bo["waves"])
    assert any("year-end freeze" in a for a in bo["assumptions"])


def test_deterministic():
    a = build_schedule(_plan(), _cfg(), start_date="2026-01-05")
    b = build_schedule(_plan(), _cfg(), start_date="2026-01-05")
    assert a == b


def test_start_date_none_uses_a_monday():
    s = build_schedule(_plan(), _cfg())          # no start_date
    from datetime import date
    assert date.fromisoformat(s["start"]).weekday() == 0


def _inputs():
    apps = list(csv.DictReader(io.StringIO(sample_bytes("applications.csv").decode("utf-8-sig"))))
    servers = list(csv.DictReader(io.StringIO(sample_bytes("servers.csv").decode("utf-8-sig"))))
    deps = list(csv.DictReader(io.StringIO(sample_bytes("dependencies.csv").decode("utf-8-sig"))))
    return apps, servers, deps
