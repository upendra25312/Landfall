"""
Deliverable HTTP tool (PRD E5). Registered from function_app.py.

  POST /api/assemble_estimate
  body: {
    "inventory_summary": {servers, applications, total_vcpu, ...},
    "data_quality": {confidence, findings},
    "compute_cost": {...},           # estimate_compute_cost output
    "storage_cost": {...},           # estimate_storage_cost output
    "run_rate_extras": {...},        # estimate_run_rate_extras output
    "landing_zone": {...},           # design_landing_zone output
    "dispositions": {...},           # score_dispositions output
    "waves": {...},                  # plan_waves output
    "generated_on": "2026-09-08",
    "config": { ...overrides... }
  }
"""
from __future__ import annotations

import json
import logging

import azure.functions as func

from cost.config import load_config
from .assemble import assemble_estimate

deliverable_bp = func.Blueprint()


@deliverable_bp.route(route="assemble_estimate", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def assemble_estimate_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    if not isinstance(body, dict) or not body.get("inventory_summary"):
        return _json({"error": 'body needs at least {"inventory_summary": {...}} plus the tool outputs to assemble'}, 400)

    try:
        cfg = load_config(overrides=body.get("config"))
        package = assemble_estimate(body, cfg)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("assemble_estimate failed")
        return _json({"error": f"assemble failed: {exc}"}, 500)
    return _json(package)


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
