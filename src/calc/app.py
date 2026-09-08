"""
ca-calc — Azure Pricing Calculator driver service (PRD E11.16).

  POST /build   body = {"spec": <lz.calculator_spec spec>,
                        "dest": {"storage_url", "container", "prefix"}}
                -> 202 {"status": "building", "prefix": ...}   (returns immediately)
                Then, in the background: drive the real calculator, parse its Excel
                export, reconcile against the spec's internal figure, and write
                  <prefix>/landing_zone.xlsx   the calculator's own file (the POE)
                  <prefix>/landing_zone.json   {status: ready|failed, totals, spec, ...}
                  <prefix>/landing_zone.png    screenshot
                to <container> using this container's managed identity.
  POST /build?wait=1   run synchronously and return the summary (local / test use)
  GET  /healthz

Why async: driving ~50 calculator line items through Playwright takes minutes; a
synchronous Function->ca-calc->wait call is cut off at the ~230s Azure Functions
HTTP limit (observed 2026-09-08). So the Function writes a "building" marker,
kicks this endpoint fire-and-forget, and returns 202; this service owns the
result and the dashboard/agent poll landing_zone.json.
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import logging
import os

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from driver import build_estimate
from calculator_export import parse_calculator_export, reconcile

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="ca-calc")

_CALCULATOR_URL = "https://azure.microsoft.com/pricing/calculator/"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _container_client(dest: dict):
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    cred = DefaultAzureCredential()
    svc = BlobServiceClient(dest["storage_url"], credential=cred)
    return svc.get_container_client(dest["container"])


def _put(cc, name: str, data, content_type: str) -> None:
    from azure.storage.blob import ContentSettings

    cc.upload_blob(name, data, overwrite=True,
                   content_settings=ContentSettings(content_type=content_type))


def _summary_from(spec: dict, parsed: dict, rec: dict, run: dict) -> dict:
    return {
        "status": "ready",
        "engagement": spec.get("engagement"),
        "estimate_name": parsed["estimate_name"],
        "region": spec.get("region_azure") or spec.get("region_default"),
        "currency": parsed["currency"],
        "monthly_total": parsed["total_monthly"],
        "annual": parsed["annual"],
        "upfront_total": parsed["total_upfront"],
        "support_monthly": parsed["support_monthly"],
        "line_items": parsed["line_items"],
        "line_count": parsed["line_count"],
        "created_at": parsed["created_at"],
        "calculator_url": run.get("calculator") or _CALCULATOR_URL,
        "monthly_header": run.get("monthly_header"),
        "reconciliation": rec,
        "applied": run.get("applied", []),
        "skipped": run.get("skipped", []),
        "spec": spec,
        "built_at": _now(),
        "source": "azure-pricing-calculator",
        "note": "Excel exported by the Azure Pricing Calculator - submit landing_zone.xlsx "
                "as the Proof of Estimate. All prices are the calculator's; quantities are "
                "Landfall figures (see spec + applied/skipped).",
    }


async def _run_and_store(spec: dict, dest: dict) -> None:
    prefix = dest["prefix"].rstrip("/")
    try:
        cc = _container_client(dest)
    except Exception:  # noqa: BLE001
        logging.exception("cannot reach blob storage - result will be lost")
        return
    try:
        run = await build_estimate(spec)
        xlsx = base64.b64decode(run["xlsx_b64"])
        parsed = parse_calculator_export(xlsx)
        rec = reconcile(parsed, spec.get("internal_monthly_estimate"))
        summary = _summary_from(spec, parsed, rec, run)

        _put(cc, f"{prefix}/landing_zone.xlsx", xlsx,
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        _put(cc, f"{prefix}/landing_zone.json",
             json.dumps(summary, default=str).encode(), "application/json")
        if run.get("screenshot_b64"):
            _put(cc, f"{prefix}/landing_zone.png",
                 base64.b64decode(run["screenshot_b64"]), "image/png")
        logging.info("stored POE for %s -> %s (monthly=%s)",
                     spec.get("engagement"), prefix, parsed.get("total_monthly"))
    except Exception as exc:  # noqa: BLE001
        logging.exception("calculator run failed for %s", spec.get("engagement"))
        try:
            _put(cc, f"{prefix}/landing_zone.json", json.dumps({
                "status": "failed",
                "engagement": spec.get("engagement"),
                "error": str(exc),
                "failed_at": _now(),
                "estimate_name": spec.get("estimate_name"),
                "spec": spec,
            }, default=str).encode(), "application/json")
        except Exception:  # noqa: BLE001
            logging.exception("could not even write the failure marker")


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "ca-calc"}


@app.post("/build")
async def build(req: Request, bg: BackgroundTasks):
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "body must be JSON"}, status_code=400)

    # accept both {"spec": {...}, "dest": {...}} and a bare spec (no dest -> sync only)
    spec = body.get("spec") if isinstance(body, dict) and "spec" in body else body
    dest = body.get("dest") if isinstance(body, dict) else None
    if not isinstance(spec, dict) or not spec.get("line_items"):
        return JSONResponse({"error": 'spec needs "line_items": [...]'}, status_code=400)

    wait = req.query_params.get("wait") in ("1", "true", "yes")

    if wait or not dest:
        try:
            run = await build_estimate(spec)
        except Exception as exc:  # noqa: BLE001
            logging.exception("sync build failed")
            return JSONResponse({"error": f"calculator run failed: {exc}"}, status_code=502)
        parsed = parse_calculator_export(base64.b64decode(run["xlsx_b64"]))
        rec = reconcile(parsed, spec.get("internal_monthly_estimate"))
        summary = _summary_from(spec, parsed, rec, run)
        if dest:
            try:
                cc = _container_client(dest)
                p = dest["prefix"].rstrip("/")
                _put(cc, f"{p}/landing_zone.xlsx", base64.b64decode(run["xlsx_b64"]),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                _put(cc, f"{p}/landing_zone.json", json.dumps(summary, default=str).encode(),
                     "application/json")
                if run.get("screenshot_b64"):
                    _put(cc, f"{p}/landing_zone.png", base64.b64decode(run["screenshot_b64"]),
                         "image/png")
            except Exception:  # noqa: BLE001
                logging.exception("sync store failed")
        return {**summary, "xlsx_b64": run["xlsx_b64"]}

    for k in ("storage_url", "container", "prefix"):
        if not dest.get(k):
            return JSONResponse({"error": f'dest needs "{k}"'}, status_code=400)
    bg.add_task(_run_and_store, spec, dest)
    return JSONResponse(
        {"status": "building", "engagement": spec.get("engagement"),
         "prefix": dest["prefix"],
         "note": "the calculator run is in progress; landing_zone.json will show "
                 "status ready or failed when it completes"},
        status_code=202)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
