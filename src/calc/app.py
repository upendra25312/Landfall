"""
ca-calc — Azure Pricing Calculator driver service (PRD E11.16).

  POST /build   body = a lz.calculator_spec line-item spec
                -> { xlsx_b64, screenshot_b64, applied[], skipped[],
                     monthly_header, calculator }
  GET  /healthz

Stateless. The caller (src/api/lz/functions.build_calculator_estimate) parses the
returned xlsx, reconciles it against Landfall's internal number, and writes
landing_zone.{xlsx,json,png} to the engagement's blob folder. This service does
one thing: drive the real calculator and hand back its export.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from driver import build_estimate

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="ca-calc")


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "ca-calc"}


@app.post("/build")
async def build(req: Request):
    try:
        spec = await req.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "body must be a JSON calculator spec"}, status_code=400)
    if not isinstance(spec, dict) or not spec.get("line_items"):
        return JSONResponse({"error": 'spec needs "line_items": [...]'}, status_code=400)
    try:
        result = await build_estimate(spec)
    except Exception as exc:  # noqa: BLE001
        logging.exception("build failed")
        return JSONResponse({"error": f"calculator run failed: {exc}"}, status_code=502)
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
