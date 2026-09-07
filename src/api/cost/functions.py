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

import time

import azure.functions as func

from .compute_cost import estimate_compute_cost
from .config import load_config
from .rightsize import rightsize_many

cost_bp = func.Blueprint()
_price_cache: dict = {}
_PRICE_TTL = 6 * 3600


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


@cost_bp.route(route="estimate_compute_cost", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def estimate_compute_cost_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    servers = body.get("servers") or []
    if not isinstance(servers, list) or not servers:
        return _json({"error": 'body must be {"servers": [ {server_id, vcpu, ram_gb, env, os_name, ...} ]}'}, 400)

    try:
        cfg = load_config(overrides=body.get("config"))
        rs = rightsize_many(servers[:2000], cfg)
        skus = {r["recommended"]["sku"] for r in rs["recommendations"]}
        skus |= {r["range"]["low"] for r in rs["recommendations"]}
        skus |= {r["range"]["high"] for r in rs["recommendations"]}
        tiers = {r["disk"]["tier"] for r in rs["recommendations"]}
        book, disks, price_date = _prices(cfg["pricing"]["region"], sorted(skus), sorted(tiers))
        result = estimate_compute_cost(servers[:2000], book, disks, cfg, price_date)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("estimate_compute_cost failed")
        return _json({"error": f"cost estimate failed: {exc}"}, 502)
    return _json(result)


def _prices(region: str, skus: list, tiers: list):
    from . import pricing

    key = (region, tuple(skus), tuple(tiers))
    hit = _price_cache.get(key)
    if hit and time.time() - hit[0] < _PRICE_TTL:
        return hit[1]
    book = pricing.fetch_pricebook(skus, region)
    disks = pricing.fetch_diskbook(tiers, region)
    value = (book, disks, pricing.last_price_date(book))
    _price_cache[key] = (time.time(), value)
    return value


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
