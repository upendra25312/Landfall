"""
Landing-zone HTTP tools (PRD E3 + E11.16). Registered from function_app.py.

  POST /api/design_landing_zone       CAF ALZ design from the app portfolio
  POST /api/build_calculator_estimate  drive the real Azure Pricing Calculator
                                       (via the ca-calc container) and store its
                                       own Excel export as the engagement's POE
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request

import azure.functions as func

import engagement as eng
from cost.config import load_config
from .design import design_landing_zone
from .calculator_spec import build_calculator_spec
from .calculator_export import parse_calculator_export, reconcile

lz_bp = func.Blueprint()

_state: dict = {}


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


# --------------------------------------------------------------------------
# build_calculator_estimate (E11.16)
# --------------------------------------------------------------------------
def _blob():
    if "svc" not in _state:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
        _state["svc"] = BlobServiceClient(os.environ["STORAGE_URL"], credential=DefaultAzureCredential())
    return _state["svc"]


def _read_json(container: str, name: str) -> dict | None:
    try:
        data = _blob().get_blob_client(container, name).download_blob().readall()
        return json.loads(data)
    except Exception:                              # noqa: BLE001
        return None


@lz_bp.route(route="build_calculator_estimate", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def build_calculator_estimate_route(req: func.HttpRequest) -> func.HttpResponse:
    """Body: {"engagement": "<customer>/<project>", "include_dr_compute": false}.

    Reads the engagement's published estimate (`latest.json` + `tools_raw.json`) and
    `_engagement.json`, builds an Azure Pricing Calculator line-item spec, hands it to
    the `ca-calc` container which drives the real calculator and returns its Excel
    export, then stores `landing_zone.{xlsx,json,png}` in the engagement folder so the
    dashboard can show the POE. `CALC_URL` env points at the container."""
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    raw_eng = body.get("engagement") or req.params.get("engagement")
    if not raw_eng:
        return _json({"error": 'body needs {"engagement": "<customer>/<project>"}'}, 400)
    try:
        engagement = eng.normalize_engagement(raw_eng)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)

    calc_url = os.environ.get("CALC_URL", "").rstrip("/")
    if not calc_url:
        return _json({"error": "CALC_URL not configured — the ca-calc container is not deployed yet"}, 503)

    prefix = eng.estimate_prefix(engagement)
    latest = _read_json(eng.ANSWERS_CONTAINER, f"{prefix}/latest.json")
    tools_raw = _read_json(eng.ANSWERS_CONTAINER, f"{prefix}/tools_raw.json") or {}
    manifest = _read_json(eng.RAW_CONTAINER, eng.engagement_file(engagement)) or {}
    if not latest and not tools_raw:
        return _json({"error": f"no published estimate for {engagement} — run publish_estimate first"}, 409)

    meta = (latest or {}).get("meta", {})
    engagement_meta = {
        "engagement": engagement,
        "customer": manifest.get("customer") or engagement.split("/")[0],
        "project": manifest.get("project") or engagement.split("/")[1],
        "target_region": manifest.get("target_region") or manifest.get("region") or meta.get("region"),
        "dr_region": manifest.get("dr_region"),
        "currency": (manifest.get("currency") or meta.get("currency") or "USD"),
        "licensing_program": manifest.get("licensing_program") or "MCA",
    }

    try:
        spec = build_calculator_spec(
            engagement_meta,
            design=tools_raw.get("landing_zone"),
            compute=tools_raw.get("compute_cost"),
            storage=tools_raw.get("storage_cost"),
            run_rate=tools_raw.get("run_rate_extras"),
            include_dr_compute=bool(body.get("include_dr_compute")),
            generated_on=meta.get("generated_on"),
        )
    except ValueError as exc:
        return _json({"error": f"cannot build a calculator spec: {exc}"}, 400)

    try:
        req_body = json.dumps(spec).encode()
        r = urllib.request.Request(f"{calc_url}/build", data=req_body,
                                   headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(r, timeout=600) as resp:
            run = json.loads(resp.read())
    except Exception as exc:                       # noqa: BLE001
        logging.exception("ca-calc call failed")
        return _json({"error": f"ca-calc run failed: {exc}"}, 502)
    if run.get("error"):
        return _json({"error": f"ca-calc: {run['error']}"}, 502)

    xlsx = base64.b64decode(run["xlsx_b64"])
    parsed = parse_calculator_export(xlsx)
    rec = reconcile(parsed, spec.get("internal_monthly_estimate"))

    summary = {
        "engagement": engagement,
        "estimate_name": parsed["estimate_name"],
        "region": engagement_meta["target_region"],
        "currency": parsed["currency"],
        "monthly_total": parsed["total_monthly"],
        "annual": parsed["annual"],
        "upfront_total": parsed["total_upfront"],
        "line_items": parsed["line_items"],
        "line_count": parsed["line_count"],
        "created_at": parsed["created_at"],
        "calculator_url": run.get("calculator"),
        "reconciliation": rec,
        "applied": run.get("applied", []),
        "skipped": run.get("skipped", []),
        "spec": spec,
        "source": "azure-pricing-calculator",
        "note": "Excel exported by the Azure Pricing Calculator — submit landing_zone.xlsx "
                "as the Proof of Estimate. All prices are the calculator's; quantities are "
                "Landfall figures (see spec + applied/skipped).",
    }

    try:
        cc = _blob().get_container_client(eng.ANSWERS_CONTAINER)
        cc.upload_blob(f"{prefix}/landing_zone.xlsx", xlsx, overwrite=True)
        cc.upload_blob(f"{prefix}/landing_zone.json",
                       json.dumps(summary, default=str).encode(), overwrite=True)
        if run.get("screenshot_b64"):
            cc.upload_blob(f"{prefix}/landing_zone.png",
                           base64.b64decode(run["screenshot_b64"]), overwrite=True)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("storing landing_zone.* failed")
        return _json({"error": f"calculator run OK but storing the result failed: {exc}"}, 500)

    _state["last"] = summary
    return _json({k: summary[k] for k in
                  ("engagement", "monthly_total", "annual", "currency", "region",
                   "line_count", "created_at", "reconciliation", "skipped", "calculator_url")}
                 | {"stored": ["landing_zone.xlsx", "landing_zone.json", "landing_zone.png"],
                    "dashboard_hint": f"open the dashboard for {engagement} — the "
                                      "'Azure landing zone — Pricing Calculator POE' card"})


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
