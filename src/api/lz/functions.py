"""
Landing-zone design HTTP tool (PRD E3). Registered from function_app.py.

  POST /api/design_landing_zone
  body: {"applications": [ {app_id, app_name, criticality, internet_facing,
                           compliance_scope, db_engine, disposition} ],
         "server_summary": {total_servers, by_env, total_vcpu, total_ram_gb,
                            os_families},          # optional
         "config": { ...overrides merged over estimation_config.json... } }
"""
from __future__ import annotations

import json
import logging

import azure.functions as func

from cost.config import load_config
from .design import design_landing_zone

lz_bp = func.Blueprint()


@lz_bp.route(route="design_landing_zone", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def design_landing_zone_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    apps = body.get("applications") or []
    if not isinstance(apps, list) or not apps:
        return _json({"error": 'body must be {"applications": [ {app_id, criticality, internet_facing, compliance_scope} ], "server_summary": {...}}'}, 400)

    try:
        cfg = load_config(overrides=body.get("config"))
        result = design_landing_zone(apps[:2000], body.get("server_summary"), cfg)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("design_landing_zone failed")
        return _json({"error": f"landing-zone design failed: {exc}"}, 500)
    return _json(result)


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
