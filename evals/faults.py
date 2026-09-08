"""
Fault-injection harness (PRD E7.3).

Every deterministic HTTP tool must, on a broken request, return a clean error
(HTTP >= 400, a JSON body whose only content is an `error` string) — never a 200
with fabricated numbers. And `assemble_estimate` must degrade gracefully when an
upstream tool's slot carries an `{"error": ...}` instead of a result: the failed
tool's section is omitted, its figures are absent, and the register records the gap.

Offline. `query_inventory` / `azure_retail_prices` need a live model / network and
are covered by the live chaos drill (path-to-5x5 Phase 2), not here.
"""
from __future__ import annotations

import json

import azure.functions as func

from cost.functions import (vm_rightsize, estimate_compute_cost_route,
                            estimate_storage_cost_route, estimate_run_rate_extras_route)
from lz.functions import design_landing_zone_route
from waves.functions import score_dispositions_route, plan_waves_route
from deliverable.functions import assemble_estimate_route
from deliverable.assemble import assemble_estimate

_ROUTES = {
    "vm_rightsize": vm_rightsize,
    "estimate_compute_cost": estimate_compute_cost_route,
    "estimate_storage_cost": estimate_storage_cost_route,
    "estimate_run_rate_extras": estimate_run_rate_extras_route,
    "design_landing_zone": design_landing_zone_route,
    "score_dispositions": score_dispositions_route,
    "plan_waves": plan_waves_route,
    "assemble_estimate": assemble_estimate_route,
}

# a broken request per tool: empty body, then a malformed payload.
_BAD_BODIES = {
    "vm_rightsize": [b"", b"{}", b'{"servers": "not-a-list"}', b'{"servers": []}',
                     b'{"servers": [null, "x"]}'],
    "estimate_compute_cost": [b"", b"{}", b'{"servers": {}}', b'{"servers": [null]}'],
    "estimate_storage_cost": [b"", b"{}", b'{"storage": 5}', b'{"storage": [null, 1]}'],
    "estimate_run_rate_extras": [b"", b"{}", b'{"servers": null}', b'{"servers": [null]}'],
    "design_landing_zone": [b"", b"{}", b'{"applications": "x"}'],
    "score_dispositions": [b"", b"{}", b'{"applications": []}'],
    "plan_waves": [b"", b"{}", b'{"applications": [{"app_id":"a"}]}'],  # missing servers/deps
    "assemble_estimate": [b"", b"{}", b'{"foo": 1}'],
}

_NUM_HINT = ("monthly", "annual", "total", "cost", "pd", "vcpu", "sku", "usd", "spoke")


def _call(route_fn, body: bytes):
    req = func.HttpRequest(method="POST", url="http://x/api/t", body=body,
                           headers={"Content-Type": "application/json"})
    resp = route_fn(req)
    try:
        payload = json.loads(resp.get_body() or b"{}")
    except ValueError:
        payload = {"_raw": resp.get_body()}
    return resp.status_code, payload


def _looks_fabricated(payload: dict) -> bool:
    """An error response should carry an `error` string and nothing that reads like
    a real result (no numeric line items, totals, SKUs, ...)."""
    if set(payload) - {"error"}:
        return True
    v = payload.get("error", "")
    return not isinstance(v, str) or any(c.isdigit() for c in v.split(":")[0])


def run_faults(verbose: bool = True) -> dict:
    results = []
    for name, fn in _ROUTES.items():
        for body in _BAD_BODIES[name]:
            status, payload = _call(fn, body)
            clean_error = status >= 400 and isinstance(payload, dict) \
                and "error" in payload and not _looks_fabricated(payload)
            ok = clean_error
            results.append({"tool": name, "body": body.decode() or "<empty>",
                            "status": status, "ok": ok,
                            "detail": "" if ok else f"status={status} payload_keys={list(payload)}"})
            if verbose and not ok:
                print(f"  FAIL {name} <- {body!r}: {results[-1]['detail']}")

    # downstream: assemble with a failed tool slot
    inv = {"servers": 100, "applications": 10, "total_vcpu": 400}
    pkg = assemble_estimate({
        "inventory_summary": inv,
        "data_quality": {"confidence": "Medium"},
        "compute_cost": {"error": "cost estimate failed: price API 503"},
        "storage_cost": {"error": "storage estimate failed: timeout"},
    })
    dg = pkg["meta"]["tools_failed"]
    downstream_ok = (
        dg == ["compute_cost", "storage_cost"]
        and pkg["meta"]["tools_run"] == []
        and not any(f["source_tool"] in ("estimate_compute_cost", "estimate_storage_cost")
                    for f in pkg["figures"])
        and any("did not run" in i["text"] for i in pkg["register"]["data_gaps"])
    )
    results.append({"tool": "assemble_estimate", "body": "<failed upstream slots>",
                    "status": 200, "ok": downstream_ok,
                    "detail": "" if downstream_ok else f"tools_failed={dg} figs={[f['key'] for f in pkg['figures']]}"})
    if verbose and not downstream_ok:
        print(f"  FAIL downstream degradation: {results[-1]['detail']}")

    passed = sum(1 for r in results if r["ok"])
    return {"total": len(results), "passed": passed, "results": results}
