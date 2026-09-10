"""E13.11 — safe one-command teardown / rehydrate for the ephemeral operating model.

These are structural checks (the real proof is a live round-trip the operator runs
once — DEPLOY.md "Run a session / tear down after"). They lock in the load-bearing
safety properties so a future edit can't quietly remove them.
"""
import os
import shutil
import subprocess

import pytest
from conftest import ROOT

SCRIPTS = os.path.join(ROOT, "scripts")
INFRA = os.path.join(ROOT, "infra")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _code(*parts):
    """File contents with comment-only lines dropped, so ordering checks look at
    real statements, not the usage header."""
    out = []
    for ln in _read(*parts).splitlines():
        st = ln.strip()
        if st.startswith("#") or st.startswith("<#") or st == "":
            continue
        out.append(ln)
    return "\n".join(out)


# --------------------------------------------------------------- teardown.sh

def test_teardown_exports_before_it_destroys():
    s = _read("scripts", "teardown.sh")
    assert s.startswith("#!/bin/sh")
    assert "set -eu" in s
    c = _code("scripts", "teardown.sh")
    i_export = c.index("export_all.py")
    i_down = c.index("azd down")
    assert i_export < i_down, "teardown must export every engagement BEFORE azd down"
    assert "azd down --force --purge" in c
    assert "manifest.json" in c and "exit 1" in c
    # it verifies the RG is actually gone AFTER the teardown
    assert c.rindex("az group show") > i_down


def test_teardown_refuses_when_export_incomplete():
    c = _code("scripts", "teardown.sh")
    # the $FAILED count must gate `azd down`
    i_guard = c.index('"$FAILED" -eq 0 ]')
    assert i_guard < c.index("azd down")
    assert 'ABORT' in c


# --------------------------------------------------------------- rehydrate.sh

def test_rehydrate_refuses_on_a_live_resource_group():
    s = _read("scripts", "rehydrate.sh")
    assert s.startswith("#!/bin/sh") and "set -eu" in s
    c = _code("scripts", "rehydrate.sh")
    i_check = c.index("az group show")
    i_up = c.index("azd up")
    assert i_check < i_up, "rehydrate must confirm the RG is GONE before `azd up` (which re-runs postprovision → DROP schema)"
    assert "already exists" in c
    assert "create_agent.py" in c
    assert "smoke.py --cold" in c


def test_rehydrate_surfaces_the_stack_switches():
    s = _read("scripts", "rehydrate.sh")
    assert "DEPLOY_DRAWIO" in s and "WEB_AUTH_CLIENT_ID" in s


# --------------------------------------------------------------- powershell twins

@pytest.mark.parametrize("name", ["teardown.ps1", "rehydrate.ps1"])
def test_powershell_twin_exists_with_the_same_guards(name):
    c = _code("scripts", name)
    assert "azd" in c
    if name.startswith("teardown"):
        assert c.index("export_all.py") < c.index("azd down")
        assert "--purge" in c
    else:
        assert c.index("az group show") < c.index("azd up")
        assert "create_agent.py" in c


# --------------------------------------------------------------- infra wiring

def test_drawio_params_are_threaded_and_dormant():
    main = _read("infra", "main.bicep")
    for p in ("param deployDrawio bool = false",
              "param drawioImageName string = ''",
              "param drawioKey string = ''"):
        assert p in main, f"missing in main.bicep: {p}"
    # passed down to the resources module
    assert "deployDrawio: deployDrawio" in main
    assert "drawioImageName: drawioImageName" in main
    assert "drawioKey:" in main and "uniqueString(resourceToken, 'drawio-render')" in main

    params = _read("infra", "main.parameters.json")
    assert '"deployDrawio": { "value": "${DEPLOY_DRAWIO=false}" }' in params
    assert '"drawioImageName": { "value": "${SERVICE_DRAWIO_IMAGE_NAME=}" }' in params
    assert '"drawioKey": { "value": "${DRAWIO_KEY=}" }' in params

    # resources.bicep already gates every drawio resource on `deployDrawio`
    res = _read("infra", "resources.bicep")
    assert "= if (deployDrawio)" in res


def test_default_deploy_is_byte_identical_ie_drawio_off():
    """DEPLOY_DRAWIO defaults false → a normal `azd up` provisions nothing new."""
    assert "DEPLOY_DRAWIO=false" in _read("infra", "main.parameters.json")
    assert "param deployDrawio bool = false" in _read("infra", "main.bicep")


@pytest.mark.skipif(not shutil.which("az") and not shutil.which("az.cmd"),
                    reason="az not installed")
def test_bicep_compiles(tmp_path):
    az = shutil.which("az") or shutil.which("az.cmd")
    r = subprocess.run([az, "bicep", "build", "--file", os.path.join(INFRA, "main.bicep"),
                        "--outfile", str(tmp_path / "main.json")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --------------------------------------------------------------- smoke --cold

def test_smoke_has_a_cold_start_check():
    import sys
    sys.path.insert(0, SCRIPTS)
    import importlib
    smoke = importlib.import_module("smoke")
    importlib.reload(smoke)
    r = smoke.run_checks({"SERVICE_WEB_URI": "http://127.0.0.1:59999"}, cold=True, cold_budget_s=1)
    names = {c["check"] for c in r.checks}
    assert "cold_start" in names
    cs = next(c for c in r.checks if c["check"] == "cold_start")
    assert cs["status"] == "FAIL"          # nothing listening on :59999 → over budget
    assert "budget 1s" in cs["detail"]


def test_smoke_cli_accepts_cold_flags():
    s = _read("scripts", "smoke.py")
    assert '"--cold"' in s and '"--cold-budget"' in s
