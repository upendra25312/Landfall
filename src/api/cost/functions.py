"""
Cost-engine HTTP tools (PRD E2). Registered from function_app.py.

  POST /api/vm_rightsize   servers[] -> deterministic Azure VM SKU + disk tier per server
                           (RAM-aware; config-driven; low/expected/high range)

Body: {"servers": [ {server_id, vcpu, ram_gb, cpu_p95_pct?, cpu_peak_pct?, cpu_avg_pct?,
                     ram_avg_pct?/mem_*_pct?, used_disk_gb?, disk_iops_peak?} ],
       "config": { ...optional overrides merged over estimation_config.json... } }
"""
from __future__ import annotations

import json
import logging

import azure.functions as func

from .config import load_config
from .rightsize import rightsize_many

cost_bp = func.Blueprint()


@cost_bp.route(route="vm_rightsize", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def vm_rightsize(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    servers = body.get("servers") or []
    if not isinstance(servers, list) or not servers:
        return _json({"error": 'body must be {"servers": [ {server_id, vcpu, ram_gb, ...} ]}'}, 400)

    try:
        cfg = load_config(overrides=body.get("config"))
        result = rightsize_many(servers[:2000], cfg)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("vm_rightsize failed")
        return _json({"error": f"rightsize failed: {exc}"}, 500)
    return _json(result)


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
