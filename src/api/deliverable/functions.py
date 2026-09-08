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
import os

import azure.functions as func

import engagement as eng
from cost.config import load_config
from .assemble import assemble_estimate
from .export import export

deliverable_bp = func.Blueprint()

ESTIMATE_CONTAINER = eng.ANSWERS_CONTAINER
_blob_state: dict = {}


def _engagement_of(req, body: dict) -> str:
    raw = body.get("engagement") or req.params.get("engagement") or eng.DEFAULT_ENGAGEMENT
    return eng.normalize_engagement(raw)


def _container_client():
    if "cc" not in _blob_state:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        svc = BlobServiceClient(os.environ["STORAGE_URL"], credential=DefaultAzureCredential())
        _blob_state["cc"] = svc.get_container_client(ESTIMATE_CONTAINER)
    return _blob_state["cc"]


@deliverable_bp.route(route="assemble_estimate", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def assemble_estimate_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    if not isinstance(body, dict) or not body.get("inventory_summary"):
        return _json({"error": 'body needs at least {"inventory_summary": {...}} plus the tool outputs to assemble'}, 400)

    try:
        engagement = _engagement_of(req, body)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    try:
        cfg = load_config(overrides=body.get("config"))
        package = assemble_estimate(body, cfg)
        package.setdefault("meta", {})["engagement"] = engagement
    except Exception as exc:                       # noqa: BLE001
        logging.exception("assemble_estimate failed")
        return _json({"error": f"assemble failed: {exc}"}, 500)
    return _json(package)


@deliverable_bp.route(route="export_estimate", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def export_estimate_route(req: func.HttpRequest) -> func.HttpResponse:
    """Body: {"format": "xlsx"|"docx"|"pptx", "package": {...}} — or the assemble
    inputs directly (inventory_summary + the tool outputs), which are assembled first."""
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    fmt = (body.get("format") or req.params.get("format") or "xlsx").lower()
    try:
        cfg = load_config(overrides=body.get("config"))
        package = body.get("package") or assemble_estimate(body, cfg)
        blob, filename, mime = export(package, fmt)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("export_estimate failed")
        return _json({"error": f"export failed: {exc}"}, 500)
    return func.HttpResponse(blob, status_code=200, mimetype=mime,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@deliverable_bp.route(route="publish_estimate", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def publish_estimate_route(req: func.HttpRequest) -> func.HttpResponse:
    """Assemble the estimate and write it (+ the xlsx / docx / pptx) to blob so the
    assessment dashboard (src/web) can serve it. Body: the assemble_estimate inputs,
    or {"package": {...}}."""
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    if not isinstance(body, dict) or not (body.get("package") or body.get("inventory_summary")):
        return _json({"error": 'body needs the assemble_estimate inputs (or {"package": ...})'}, 400)

    try:
        engagement = _engagement_of(req, body)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)

    try:
        cfg = load_config(overrides=body.get("config"))
        package = body.get("package") or assemble_estimate(body, cfg)
        package.setdefault("meta", {})["engagement"] = engagement
        cc = _container_client()
        prefix = eng.estimate_prefix(engagement)
        written = []

        payload = json.dumps(package, default=str).encode("utf-8")
        cc.upload_blob(f"{prefix}/latest.json", payload, overwrite=True)
        written.append("latest.json")
        for fmt in ("xlsx", "docx", "pptx"):
            blob, _name, _mime = export(package, fmt)
            cc.upload_blob(f"{prefix}/latest.{fmt}", blob, overwrite=True)
            written.append(f"latest.{fmt}")
    except Exception as exc:                       # noqa: BLE001
        logging.exception("publish_estimate failed")
        return _json({"error": f"publish failed: {exc}"}, 500)

    return _json({
        "engagement": engagement,
        "published": written,
        "prefix": prefix,
        "package_id": package.get("meta", {}).get("package_id"),
        "figures": len(package.get("figures", [])),
        "dashboard_hint": f"open the Container App at /e/{engagement}",
    })


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
