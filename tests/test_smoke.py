"""PRD E9.2 — the post-deploy smoke test's pure logic (scripts/smoke.py).

The Azure/HTTP calls are stubbed; these lock the classification + exit-code +
config-parsing behaviour so a broken check can't slip through green.
"""
import json
import os
import sys

import pytest
from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "scripts"))

import smoke  # noqa: E402


# ------------------------------------------------------------------ host-up

@pytest.mark.parametrize("code, up", [
    (200, True), (204, True), (302, True), (401, True), (403, True), (404, True),
    (0, False), (500, False), (502, False), (503, False),
])
def test_host_up_classification(code, up):
    assert (code in smoke._HOST_UP) is up


@pytest.mark.parametrize("latest_health, expected", [("Healthy", "PASS"), ("Unhealthy", "FAIL")])
def test_revision_rollover_does_not_inspect_retiring_revision(monkeypatch, latest_health, expected):
    def az(args, timeout=90):
        if args[:2] == ["containerapp", "revision"]:
            return 0, [
                {"properties": {"active": True, "healthState": "Healthy", "provisioningState": "Provisioned",
                                "runningState": "Deprovisioning", "createdTime": "2026-09-09"}},
                {"properties": {"active": True, "healthState": latest_health, "provisioningState": "Provisioned",
                                "runningState": "Running", "createdTime": "2026-09-10"}},
            ], ""
        return _healthy_az(args, timeout)
    _stub(monkeypatch, az=az)
    result = smoke.run_checks({"AZURE_RESOURCE_GROUP": "rg-x", "SERVICE_WEB_NAME": "web-x"})
    assert next(c for c in result.checks if c["check"] == "web_revision")["status"] == expected


# ------------------------------------------------------------------ Result

@pytest.mark.parametrize("codes, expected", [([0, 503, 401], 401), ([503, 503, 503], 503), ([500], 500)])
def test_scale_from_zero_probe_retains_attempts_and_stops(monkeypatch, codes, expected):
    responses = iter(codes)
    monkeypatch.setattr(smoke, "_http_status", lambda _: next(responses))
    assert smoke._probe_host("https://example.invalid") == (expected, codes)

def test_result_counts_and_ok():
    r = smoke.Result()
    r.add("a", smoke.PASS, "")
    r.add("b", smoke.SKIP, "")
    d = r.to_dict()
    assert d["ok"] is True                       # skips don't fail
    assert d["counts"] == {"PASS": 1, "FAIL": 0, "SKIP": 1}

    r.add("c", smoke.FAIL, "boom")
    d = r.to_dict()
    assert d["ok"] is False
    assert [c["check"] for c in r.failed] == ["c"]


# ------------------------------------------------------------------ config

def test_load_config_from_env_only(monkeypatch):
    monkeypatch.setattr(smoke.shutil, "which", lambda _n: None)   # no azd
    monkeypatch.setenv("AZURE_RESOURCE_GROUP", "rg-x")
    monkeypatch.setenv("SERVICE_API_NAME", "func-x")
    monkeypatch.setenv("UNRELATED", "nope")
    cfg = smoke.load_config(from_env=True)
    assert cfg["AZURE_RESOURCE_GROUP"] == "rg-x"
    assert cfg["SERVICE_API_NAME"] == "func-x"
    assert "UNRELATED" not in cfg


# ------------------------------------------------------------------ run_checks

def _stub(monkeypatch, *, az=None, http=None):
    monkeypatch.setattr(smoke, "_az", az or (lambda a, timeout=90: (0, None, "")))
    monkeypatch.setattr(smoke, "_http_status", http or (lambda *a, **k: 200))


def _healthy_az(args, timeout=90):
    j = args[0]
    if j == "resource":
        return 0, ["Microsoft.Web/sites", "Microsoft.App/containerApps",
                   "Microsoft.Sql/servers", "Microsoft.Storage/storageAccounts",
                   "Microsoft.CognitiveServices/accounts", "Microsoft.Search/searchServices",
                   "Microsoft.ContainerRegistry/registries"], ""
    if j == "functionapp":
        return 0, {"kind": "functionapp,linux", "host": "func-x.azurewebsites.net"}, ""
    if j == "containerapp":
        return 0, [{"properties": {"active": True, "healthState": "Healthy",
                                   "provisioningState": "Provisioned", "runningState": "Running"}}], ""
    if j == "sql":
        return 0, "Online", ""
    if j == "storage":
        return 0, ["raw", "answers", "questions"], ""
    return 0, None, ""


def test_run_checks_all_green():
    import unittest.mock as m
    cfg = {"AZURE_RESOURCE_GROUP": "rg-x", "SERVICE_API_NAME": "func-x",
           "SERVICE_WEB_NAME": "landfall-web", "SERVICE_WEB_URI": "https://landfall-web.x.io",
           "AZURE_SQL_SERVER_FQDN": "sql-x.database.windows.net", "AZURE_SQL_DATABASE": "sqldb",
           "AZURE_STORAGE_ACCOUNT": "stx"}
    with m.patch.object(smoke, "_az", _healthy_az), \
         m.patch.object(smoke, "_http_status", lambda *a, **k: 401):
        r = smoke.run_checks(cfg, deep=False)
    d = r.to_dict()
    assert d["ok"] is True, d
    assert {c["check"] for c in r.checks} >= {
        "config", "resources", "function_registered", "function_host",
        "web_revision", "web_up", "sql_database", "blob_containers"}


def test_run_checks_flags_a_missing_resource_type():
    import unittest.mock as m

    def az(args, timeout=90):
        if args[0] == "resource":
            return 0, ["Microsoft.Web/sites"], ""          # everything else absent
        return _healthy_az(args, timeout)

    cfg = {"AZURE_RESOURCE_GROUP": "rg-x", "SERVICE_API_NAME": "func-x",
           "SERVICE_WEB_NAME": "w", "SERVICE_WEB_URI": "https://w.io",
           "AZURE_SQL_SERVER_FQDN": "s.database.windows.net", "AZURE_SQL_DATABASE": "d",
           "AZURE_STORAGE_ACCOUNT": "a"}
    with m.patch.object(smoke, "_az", az), m.patch.object(smoke, "_http_status", lambda *a, **k: 401):
        r = smoke.run_checks(cfg, deep=False)
    res = next(c for c in r.checks if c["check"] == "resources")
    assert res["status"] == smoke.FAIL


def test_run_checks_fails_on_dead_host():
    import unittest.mock as m
    cfg = {"AZURE_RESOURCE_GROUP": "rg-x", "SERVICE_API_NAME": "func-x",
           "SERVICE_WEB_NAME": "w", "SERVICE_WEB_URI": "https://w.io",
           "AZURE_SQL_SERVER_FQDN": "s.database.windows.net", "AZURE_SQL_DATABASE": "d",
           "AZURE_STORAGE_ACCOUNT": "a"}
    with m.patch.object(smoke, "_az", _healthy_az), \
         m.patch.object(smoke, "_http_status", lambda *a, **k: 0):     # connect error
        r = smoke.run_checks(cfg, deep=False)
    assert {c["check"] for c in r.failed} >= {"function_host", "web_up"}


def test_missing_config_is_a_hard_fail():
    r = smoke.run_checks({}, deep=False)
    cfg_check = next(c for c in r.checks if c["check"] == "config")
    assert cfg_check["status"] == smoke.FAIL


# ------------------------------------------------------------------ main / --json

def test_main_writes_json_and_returns_exit_code(tmp_path, monkeypatch):
    import unittest.mock as m
    out = tmp_path / "sub" / "smoke.json"
    monkeypatch.setattr(smoke, "load_config", lambda from_env=False: {"AZURE_RESOURCE_GROUP": "rg"})
    with m.patch.object(smoke, "run_checks") as rc:
        res = smoke.Result()
        res.add("x", smoke.FAIL, "nope")
        rc.return_value = res
        code = smoke.main(["--json", str(out)])
    assert code == 1
    assert json.loads(out.read_text())["ok"] is False
