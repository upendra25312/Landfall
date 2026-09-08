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
from .run_rate import estimate_run_rate_extras
from .storage_cost import estimate_storage_cost

cost_bp = func.Blueprint()
_price_cache: dict = {}
_PRICE_TTL = 6 * 3600


@cost_bp.route(route="vm_rightsize", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def vm_rightsize(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    servers, err = _rows(body, "servers")
    if err:
        return err

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
    servers, err = _rows(body, "servers")
    if err:
        return err

    try:
        cfg = load_config(overrides=body.get("config"))
        rs = rightsize_many(servers[:2000], cfg)
        skus = {r["recommended"]["sku"] for r in rs["recommendations"]}
        skus |= {r["range"]["low"] for r in rs["recommendations"]}
        skus |= {r["range"]["high"] for r in rs["recommendations"]}
        tiers = {r["disk"]["tier"] for r in rs["recommendations"]}
    except Exception as exc:                       # noqa: BLE001
        logging.exception("estimate_compute_cost: right-sizing the input failed")
        return _json({"error": f"could not right-size the servers provided: {exc}"}, 400)

    try:
        book, disks, price_date = _prices(cfg["pricing"]["region"], sorted(skus), sorted(tiers))
        result = estimate_compute_cost(servers[:2000], book, disks, cfg, price_date)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("estimate_compute_cost: pricing failed")
        return _json({"error": f"pricing lookup failed: {exc}"}, 502)
    return _json(result)


@cost_bp.route(route="estimate_storage_cost", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def estimate_storage_cost_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    rows, err = _rows(body, "storage")
    if err:
        return err

    try:
        cfg = load_config(overrides=body.get("config"))
        rates, price_date = _storage_rates(cfg["pricing"]["region"])
        result = estimate_storage_cost(rows[:5000], rates, cfg, price_date)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("estimate_storage_cost failed")
        return _json({"error": f"storage estimate failed: {exc}"}, 502)
    return _json(result)


@cost_bp.route(route="estimate_run_rate_extras", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def estimate_run_rate_extras_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    servers, err = _rows(body, "servers")
    if err:
        return err

    try:
        cfg = load_config(overrides=body.get("config"))
        infra = float(body.get("monthly_infra_cost") or 0.0)
        result = estimate_run_rate_extras(servers[:5000], infra, cfg, body.get("price_date"))
    except Exception as exc:                       # noqa: BLE001
        logging.exception("estimate_run_rate_extras failed")
        return _json({"error": f"run-rate estimate failed: {exc}"}, 500)
    return _json(result)


def _storage_rates(region: str):
    from . import pricing

    key = ("storage", region)
    hit = _price_cache.get(key)
    if hit and time.time() - hit[0] < _PRICE_TTL:
        return hit[1]
    book = pricing.fetch_storagebook(region)
    meta = book.pop("_meta", {})
    dates = meta.get("dates") or set()
    value = (book, max(dates) if dates else None)
    _price_cache[key] = (time.time(), value)
    return value


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


def _rows(body: dict, key: str):
    """Pull body[key] as a list of dict rows, dropping nulls / non-objects (an LLM
    caller sometimes emits a trailing `null` or a bare string in the array).
    Returns (rows, error_response_or_None)."""
    raw = body.get(key)
    if not isinstance(raw, list) or not raw:
        return [], _json({"error": f'body must be {{"{key}": [ {{...}} ]}} with at least one row'}, 400)
    rows = [r for r in raw if isinstance(r, dict)]
    if not rows:
        return [], _json({"error": f'"{key}" was a list but held no usable rows; each entry must be a JSON object'}, 400)
    return rows, None


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
