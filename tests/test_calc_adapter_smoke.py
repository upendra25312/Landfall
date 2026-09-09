"""E11.19 — thin pytest wrapper around the live calculator adapter smoke.

Skipped unless CALC_SMOKE=1 (needs network + `playwright install chromium`).
The real weekly check is .github/workflows/calc-adapter-smoke.yml running
`python src/calc/smoke.py`; this just lets you run it via pytest locally.
"""
import os
import sys

import pytest
from conftest import ROOT

_CALC = os.path.join(ROOT, "src", "calc")
if _CALC not in sys.path:
    sys.path.append(_CALC)

pytestmark = pytest.mark.skipif(
    os.environ.get("CALC_SMOKE") != "1",
    reason="set CALC_SMOKE=1 (and `playwright install chromium`) to run the live smoke",
)


def test_all_verified_adapters_resolve():
    import asyncio

    from smoke import _run

    rows = asyncio.run(_run())
    broke = [r for r in rows
             if r["verified"] and (r["error"] or not r["added"] or r["missing"])]
    assert not broke, "verified adapters regressed: " + "; ".join(
        f"{r['service']}: {r['error'] or r['missing']}" for r in broke
    )
