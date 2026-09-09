"""
Wave-engine HTTP tools (PRD E4). Registered from function_app.py.

  POST /api/score_dispositions   applications[] (+ server_rollup) -> 6R candidate per app
  POST /api/plan_waves           applications[] + servers[] + dependencies[] -> move-groups + waves
"""
from __future__ import annotations

import json
import logging

import azure.functions as func

from cost.config import load_config
from .disposition import score_dispositions
from .plan import plan_waves

waves_bp = func.Blueprint()


@waves_bp.route(route="score_dispositions", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def score_dispositions_route(req: func.HttpRequest) -> func.HttpResponse:
    body = _body(req)
    apps = body.get("applications") or []
    if not isinstance(apps, list) or not apps:
        return _json({"error": 'body must be {"applications": [ {app_id, criticality, db_engine, tech_stack, ...} ], "server_rollup": {app_id: {servers, eol_servers}}}'}, 400)
    try:
        cfg = load_config(overrides=body.get("config"))
        result = score_dispositions(apps[:2000], body.get("server_rollup"), cfg)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("score_dispositions failed")
        return _json({"error": f"disposition scoring failed: {exc}"}, 500)
    return _json(result)


@waves_bp.route(route="plan_waves", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def plan_waves_route(req: func.HttpRequest) -> func.HttpResponse:
    body = _body(req)
    apps = body.get("applications") or []
    servers = body.get("servers") or []
    deps = body.get("dependencies") or []
    if not isinstance(apps, list) or not apps or not isinstance(servers, list) or not servers:
        return _json({"error": 'body must be {"applications": [...], "servers": [ {server_id, app_id, env, os_eol_date} ], "dependencies": [ {src_id, dst_id, confidence, last_seen, flows_30d} ]}'}, 400)
    try:
        cfg = load_config(overrides=body.get("config"))
        result = plan_waves(apps[:2000], servers[:20000], deps[:200000], cfg,
                            body.get("dispositions"), body.get("start_date"))
    except Exception as exc:                       # noqa: BLE001
        logging.exception("plan_waves failed")
        return _json({"error": f"wave planning failed: {exc}"}, 500)
    return _json(result)


def _body(req: func.HttpRequest) -> dict:
    try:
        return req.get_json() or {}
    except ValueError:
        return {}


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
