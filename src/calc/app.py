"""
ca-calc — Azure Pricing Calculator driver service (PRD E11.16).

Runs a **queue consumer** (worker.consume_forever) as a background task: the
Function `build_calculator_estimate` stages a spec + drops a `calc-jobs` message,
this container drains it, drives the real calculator, and writes
`landing_zone.{xlsx,json,png}` to the engagement folder itself.

  GET  /healthz
  POST /build            body = a bare calculator spec  -> runs it synchronously
                         and returns the summary + xlsx_b64 (local / test use only)
  POST /build?wait=1     same, with an optional {"spec": ..., "dest": ...} envelope
                         (writes the blobs too)

Why the queue and not a direct HTTP call: the Function App can't reach this
container's internal ingress (no shared VNet), a multi-minute Playwright drive
overruns the ~230s Functions HTTP limit, and a queue message survives this
container being scaled down. See worker.py.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from driver import build_estimate
from calculator_export import parse_calculator_export, reconcile
from worker import consume_forever

logging.basicConfig(level=logging.INFO)
for _n in ("azure.core.pipeline.policies.http_logging_policy", "azure.identity", "azure.storage"):
    logging.getLogger(_n).setLevel(logging.WARNING)

_CALCULATOR_URL = "https://azure.microsoft.com/pricing/calculator/"
_tasks: set = set()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    if os.environ.get("STORAGE_QUEUE_URL"):
        t = asyncio.create_task(consume_forever())
        _tasks.add(t)
        t.add_done_callback(_tasks.discard)
        logging.info("ca-calc: queue consumer started")
    else:
        logging.warning("ca-calc: STORAGE_QUEUE_URL unset — queue consumer NOT started")
    yield
    for t in list(_tasks):
        t.cancel()


app = FastAPI(title="ca-calc", lifespan=_lifespan)


def _summary_from(spec, parsed, rec, run):
    return {
        "status": "ready",
        "engagement": spec.get("engagement"),
        "estimate_name": parsed["estimate_name"],
        "region": spec.get("region_azure") or spec.get("region_default"),
        "currency": parsed["currency"],
        "monthly_total": parsed["total_monthly"],
        "annual": parsed["annual"],
        "upfront_total": parsed["total_upfront"],
        "line_count": parsed["line_count"],
        "line_items": parsed["line_items"],
        "created_at": parsed["created_at"],
        "reconciliation": rec,
        "applied": run.get("applied", []),
        "skipped": run.get("skipped", []),
        "calculator_url": run.get("calculator") or _CALCULATOR_URL,
        "spec": spec,
        "source": "azure-pricing-calculator",
    }


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "ca-calc", "consumer": bool(_tasks)}


@app.post("/build")
async def build(req: Request):
    """Synchronous run — local / test only; production goes through the queue."""
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "body must be JSON"}, status_code=400)
    spec = body.get("spec") if isinstance(body, dict) and "spec" in body else body
    if not isinstance(spec, dict) or not spec.get("line_items"):
        return JSONResponse({"error": 'spec needs "line_items": [...]'}, status_code=400)
    try:
        run = await build_estimate(spec)
    except Exception as exc:  # noqa: BLE001
        logging.exception("sync build failed")
        return JSONResponse({"error": f"calculator run failed: {exc}"}, status_code=502)
    parsed = parse_calculator_export(base64.b64decode(run["xlsx_b64"]))
    rec = reconcile(parsed, spec.get("internal_monthly_estimate"))
    return {**_summary_from(spec, parsed, rec, run), "xlsx_b64": run["xlsx_b64"]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
