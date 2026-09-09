"""
Landing-zone HTTP tools (PRD E3 + E11.16). Registered from function_app.py.

  POST /api/design_landing_zone       CAF ALZ design from the app portfolio
  POST /api/build_calculator_estimate  drive the real Azure Pricing Calculator
                                       (via the ca-calc container) and store its
                                       own Excel export as the engagement's POE
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os

import azure.functions as func

import engagement as eng
from cost.config import load_config
from .design import design_landing_zone
from .calculator_spec import build_calculator_spec

lz_bp = func.Blueprint()

_state: dict = {}

CALC_QUEUE = os.environ.get("CALC_QUEUE", "calc-jobs")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


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


def _queue():
    if "queue" not in _state:
        from azure.identity import DefaultAzureCredential
        from azure.storage.queue import QueueClient
        base = os.environ["STORAGE_QUEUE_URL"].rstrip("/")
        _state["queue"] = QueueClient(account_url=base, queue_name=CALC_QUEUE,
                                      credential=DefaultAzureCredential())
    return _state["queue"]


@lz_bp.route(route="build_calculator_estimate", methods=["POST", "GET"],
             auth_level=func.AuthLevel.ANONYMOUS)
def build_calculator_estimate_route(req: func.HttpRequest) -> func.HttpResponse:
    """POST {"engagement": "<customer>/<project>", "include_dr_compute": false}
    -> starts a background Azure Pricing Calculator run and returns 202 immediately.

    GET  ?engagement=<customer>/<project>
    -> the current landing_zone.json (status: building | ready | failed) for polling.

    Async by necessity: driving ~50 calculator line items through Playwright takes
    minutes and a synchronous call is cut at the ~230s Functions HTTP limit. This
    route builds the calculator spec from the engagement's published estimate
    (`latest.json` + `tools_raw.json`) + `_engagement.json`, writes the spec to
    `{prefix}/_calc_spec.json` + a `building` marker, and puts one message on the
    `calc-jobs` queue. The `ca-calc` container drains the queue, drives the real
    calculator, and writes `landing_zone.{xlsx,json,png}` to the engagement folder
    itself (shared workload identity)."""
    try:
        raw_eng = (req.params.get("engagement")
                   or ((req.get_json() or {}) if req.method == "POST" else {}).get("engagement"))
    except ValueError:
        raw_eng = req.params.get("engagement")
    if not raw_eng:
        return _json({"error": 'need engagement — {"engagement": "<customer>/<project>"} '
                               '(POST) or ?engagement= (GET)'}, 400)
    try:
        engagement = eng.normalize_engagement(raw_eng)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)

    prefix = eng.estimate_prefix(engagement)

    if req.method == "GET":
        status = _read_json(eng.ANSWERS_CONTAINER, f"{prefix}/landing_zone.json")
        if not status:
            return _json({"engagement": engagement, "status": "none",
                          "hint": "no POE yet — POST to build_calculator_estimate to start one"}, 404)
        return _json({k: status[k] for k in (
            "engagement", "status", "estimate_name", "region", "currency", "monthly_total",
            "annual", "line_count", "created_at", "built_at", "reconciliation", "skipped",
            "calculator_url", "error") if k in status}
            | {"download": "landing_zone.xlsx (dashboard)"})

    # ---- POST: start a run --------------------------------------------------
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}

    if not os.environ.get("STORAGE_QUEUE_URL"):
        return _json({"error": "STORAGE_QUEUE_URL not configured — the ca-calc queue is not wired yet"}, 503)

    try:
        result = stage_calc_run(engagement, include_dr_compute=bool(body.get("include_dr_compute")))
    except _CalcSpecError as exc:
        return _json({"error": str(exc)}, exc.status)

    return _json({
        "engagement": engagement,
        "status": "building",
        "spec_line_count": result["spec_line_count"],
        "internal_monthly_estimate": result["internal_monthly_estimate"],
        "poll": f"GET /api/build_calculator_estimate?engagement={engagement}",
        "dashboard_hint": f"the calculator run takes a few minutes — open the dashboard "
                          f"for {engagement} and watch the 'Azure landing zone — Pricing "
                          f"Calculator POE' card; it will show the monthly total and a "
                          f"Download Excel (POE) button when ready",
    }, 202)


class _CalcSpecError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def stage_calc_run(engagement: str, *, include_dr_compute: bool = False) -> dict:
    """Build the Azure Pricing Calculator spec from the engagement's published
    estimate, stage it at `{prefix}/_calc_spec.json` + a `building` marker, and
    drop one `calc-jobs` message. Shared by the `build_calculator_estimate` route
    and the `publish_estimate` auto-kick (E11.18). Raises `_CalcSpecError`
    (carrying an HTTP status) on any hard failure.

    `engagement` must already be normalized (`eng.normalize_engagement`).
    """
    if not os.environ.get("STORAGE_QUEUE_URL"):
        raise _CalcSpecError("STORAGE_QUEUE_URL not configured — the ca-calc queue is not wired yet", 503)

    prefix = eng.estimate_prefix(engagement)
    latest = _read_json(eng.ANSWERS_CONTAINER, f"{prefix}/latest.json")
    tools_raw = _read_json(eng.ANSWERS_CONTAINER, f"{prefix}/tools_raw.json") or {}
    manifest = _read_json(eng.RAW_CONTAINER, eng.engagement_file(engagement)) or {}
    if not latest and not tools_raw:
        raise _CalcSpecError(f"no published estimate for {engagement} — run publish_estimate first", 409)

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
            include_dr_compute=include_dr_compute,
            generated_on=meta.get("generated_on"),
        )
    except ValueError as exc:
        raise _CalcSpecError(f"cannot build a calculator spec: {exc}", 400) from exc

    marker = {
        "engagement": engagement,
        "status": "building",
        "estimate_name": spec.get("estimate_name"),
        "region": engagement_meta["target_region"],
        "currency": engagement_meta["currency"],
        "started_at": _now(),
        "spec_line_count": len(spec.get("line_items", [])),
        "internal_monthly_estimate": spec.get("internal_monthly_estimate"),
    }
    try:
        cc = _blob().get_container_client(eng.ANSWERS_CONTAINER)
        cc.upload_blob(f"{prefix}/_calc_spec.json", json.dumps(spec, default=str).encode(),
                       overwrite=True)
        cc.upload_blob(f"{prefix}/landing_zone.json", json.dumps(marker, default=str).encode(),
                       overwrite=True)
    except Exception as exc:                       # noqa: BLE001
        logging.exception("could not stage the calculator spec")
        raise _CalcSpecError(f"could not stage the calculator run: {exc}", 500) from exc

    try:
        _queue().send_message(json.dumps({
            "engagement": engagement,
            "container": eng.ANSWERS_CONTAINER,
            "prefix": prefix,
            "spec_blob": f"{prefix}/_calc_spec.json",
            "queued_at": _now(),
        }))
    except Exception as exc:                       # noqa: BLE001
        logging.exception("could not enqueue the calculator job")
        raise _CalcSpecError(f"could not start the calculator run: {exc}", 502) from exc

    return {"engagement": engagement, "status": "building",
            "spec_line_count": marker["spec_line_count"],
            "internal_monthly_estimate": marker["internal_monthly_estimate"]}


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
