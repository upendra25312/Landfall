"""
Function blueprint for inventory ingestion (PRD E1.1 / E11.4).

  blob trigger  raw/engagements/{customer}/{project}/inventory/{name}
      (Event Grid source - Flex Consumption)
      -> normalize -> load to SQL (scoped to that engagement)
      -> write answers/engagements/<c>/<p>/_ingest/<name>.dq.{md,json}
  POST /api/ingest        run ingestion for one blob, or an uploaded file, for an
                          engagement (operator / test use - no Event Grid needed)
  GET  /api/ingest_status last run summary

Registered from function_app.py:  app.register_functions(ingest_bp)
"""
from __future__ import annotations

import json
import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

import engagement as eng
from .core import normalize
from .dq import build_report, render_markdown
from . import loader

ingest_bp = func.Blueprint()

_cred = DefaultAzureCredential()
_state: dict = {}


def _blob() -> BlobServiceClient:
    if "blob" not in _state:
        _state["blob"] = BlobServiceClient(os.environ["STORAGE_URL"], credential=_cred)
    return _state["blob"]


def _process(engagement: str, name: str, data: bytes) -> dict:
    """Normalize + load one file for one engagement. `name` is the bare file name."""
    engagement = eng.normalize_engagement(engagement)
    res = normalize(name, data)
    try:
        existing = loader.existing_keys(engagement)
    except Exception:                       # noqa: BLE001
        existing = {}
    report = build_report([res], existing)

    loaded, rejected, status = 0, 0, "ok"
    hard_errors = [i for i in res.issues if i.level == "error"]
    if res.table is None:
        status = "unrecognised"
    elif hard_errors:
        status = "rejected"
        rejected = len(res.rows)
    else:
        try:
            loaded = loader.load(res.table, res.rows, engagement)
        except Exception as exc:            # noqa: BLE001
            logging.exception("ingest load failed for %s/%s", engagement, name)
            status = f"load_error: {exc}"

    summary = {
        "engagement": engagement,
        "file": name,
        "profile": res.profile,
        "table": res.table,
        "rows_in": res.row_count_in,
        "rows_loaded": loaded,
        "rows_rejected": rejected,
        "status": status,
        "confidence_hint": report["confidence_hint"],
        "findings": report["findings"],
    }

    _write_report(engagement, name, report, summary)
    loader.write_log({
        "engagement_id": engagement,
        "file_name": name, "profile": res.profile, "target_table": res.table,
        "rows_in": res.row_count_in, "rows_loaded": loaded, "rows_rejected": rejected,
        "status": status, "dq_json": report,
    })
    _state["last"] = summary
    return summary


def _write_report(engagement: str, name: str, report: dict, summary: dict) -> None:
    stem = name.rsplit(".", 1)[0]
    prefix = eng.ingest_report_prefix(engagement)
    try:
        svc = _blob()
        svc.get_blob_client(eng.ANSWERS_CONTAINER, f"{prefix}/{stem}.dq.md").upload_blob(
            render_markdown(report, f"Data-quality report — {name}").encode("utf-8"),
            overwrite=True,
        )
        svc.get_blob_client(eng.ANSWERS_CONTAINER, f"{prefix}/{stem}.dq.json").upload_blob(
            json.dumps({"summary": summary, "report": report}, indent=2, default=str).encode(),
            overwrite=True,
        )
    except Exception:                       # noqa: BLE001
        logging.exception("could not write DQ report for %s/%s", engagement, name)


# --------------------------------------------------------------------------
@ingest_bp.blob_trigger(
    arg_name="src",
    path="raw/engagements/{customer}/{project}/inventory/{name}",
    connection="STORAGE_CONN",
    source=func.BlobSource.EVENT_GRID,      # required on Flex Consumption
)
def ingest_blob(src: func.InputStream):
    parsed = eng.parse_inventory_blob(src.name)
    if not parsed:
        logging.warning("ingest_blob: unrecognised path %s", src.name)
        return
    engagement, name = parsed
    if name.startswith("_"):               # skip _mapping.json / _engagement.json / artefacts
        return
    logging.info("ingest: %s :: %s (%s bytes)", engagement, name, src.length)
    _process(engagement, name, src.read())


@ingest_bp.route(route="ingest", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def ingest_http(req: func.HttpRequest) -> func.HttpResponse:
    """{"engagement": "<customer>/<project>", "blob": "servers.csv"} to pull from that
    engagement's inventory/ folder, or POST raw file bytes with
    ?engagement=<c>/<p>&name=servers.csv."""
    try:
        body = req.get_json() or {}
    except ValueError:
        body = {}
    engagement = req.params.get("engagement") or body.get("engagement")
    if not engagement:
        return _json({"error": 'body/param needs "engagement": "<customer>/<project>"'}, 400)
    try:
        engagement = eng.normalize_engagement(engagement)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)

    name = req.params.get("name")
    raw = req.get_body()
    if name and raw:
        data = raw
    else:
        blob_name = body.get("blob")
        if not blob_name:
            return _json({"error": 'POST {"engagement","blob"} or raw bytes with ?engagement=&name='}, 400)
        name = os.path.basename(blob_name)
        key = f"{eng.inventory_prefix(engagement)}/{name}"
        try:
            data = _blob().get_blob_client(eng.RAW_CONTAINER, key).download_blob().readall()
        except Exception as exc:            # noqa: BLE001
            return _json({"error": f"could not read raw/{key}: {exc}"}, 404)

    return _json(_process(engagement, name, data))


@ingest_bp.route(route="ingest_status", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def ingest_status(req: func.HttpRequest) -> func.HttpResponse:
    return _json(_state.get("last") or {"status": "no ingestion has run in this worker"})


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
