"""E9.3 — the `DEPLOYMENT_TIER` switch. `free` (default) keeps the Free-tier /
Free-offer SKUs; `prod` moves to paid SKUs with SLAs. Verified two ways: a text
check on the Bicep (always) and a full `az bicep build` compile (when available).
"""
import json
import os
import shutil
import subprocess

import pytest
from conftest import ROOT

MAIN = os.path.join(ROOT, "infra", "main.bicep")
RES = os.path.join(ROOT, "infra", "resources.bicep")
PARAMS = os.path.join(ROOT, "infra", "main.parameters.json")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------- text checks

def test_param_declared_and_threaded_through():
    main, res = _read(MAIN), _read(RES)
    assert "param deploymentTier string = 'free'" in main
    assert "@allowed(['free', 'prod'])" in main
    assert "deploymentTier: deploymentTier" in main            # passed to the module
    assert "param deploymentTier string = 'free'" in res
    assert "var isProd = deploymentTier == 'prod'" in res
    assert '"deploymentTier": { "value": "${DEPLOYMENT_TIER=free}" }' in _read(PARAMS)


def test_default_is_free_everywhere_isprod_is_used():
    res = _read(RES)
    # each Free-tier resource is gated, and the free branch keeps today's SKU
    assert "isProd ? 'basic' : 'free'" in res                  # AI Search
    assert "isProd ? 'Standard_ZRS' : 'Standard_LRS'" in res   # storage
    assert "isProd ? 'Standard' : 'Basic'" in res              # ACR
    assert "isProd ? 1440 : 60" in res                         # SQL auto-pause
    assert "minReplicas: isProd ? 1 : 0" in res                # web app warm in prod
    assert "isProd ? 90 : 30" in res                           # log retention
    # the SQL free-limit only exists on the free branch
    assert "isProd ? {} : {" in res and "useFreeLimit: true" in res


def test_deploy_md_documents_the_cost_delta():
    txt = _read(os.path.join(ROOT, "DEPLOY.md"))
    assert "## Deployment tiers (`DEPLOYMENT_TIER`)" in txt
    assert "DEPLOYMENT_TIER prod" in txt
    for resource in ("Azure SQL", "AI Search", "Container Registry", "Log Analytics"):
        assert resource in txt
    assert "not in-place editable" in txt or "not** in-place editable" in txt


# --------------------------------------------------------------- compile check

def _az():
    return shutil.which("az") or shutil.which("az.cmd")


@pytest.mark.skipif(not _az(), reason="az CLI not available")
def test_bicep_compiles_and_carries_both_tier_branches(tmp_path):
    out = tmp_path / "main.json"
    r = subprocess.run([_az(), "bicep", "build", "--file", MAIN, "--outfile", str(out)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    arm = json.loads(out.read_text(encoding="utf-8"))

    p = arm["parameters"]["deploymentTier"]
    assert p["defaultValue"] == "free"
    assert set(p["allowedValues"]) == {"free", "prod"}

    blob = json.dumps(arm)
    for token in ("'prod'", "Standard_ZRS", "basic", "useFreeLimit", "107374182400"):
        assert token in blob, token
