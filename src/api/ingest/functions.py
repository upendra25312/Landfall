"""
Function blueprint for inventory ingestion (PRD E1.1).

  blob trigger  raw/inventory/{name}   (Event Grid source - Flex Consumption)
      -> normalize -> load to SQL -> write answers/_ingest/<name>.dq.md + .json
  POST /api/ingest        run ingestion for one blob by name, or an uploaded file
                          (operator / test use - no Event Grid needed)
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

from .core import normalize
from .dq import build_report, render_markdown
from . import loader

ingest_bp = func.Blueprint()

_cred = DefaultAzureCredential()
_state: dict = {}
INVENTORY_PREFIX = "inventory/"
REPORT_CONTAINER = "answers"
REPORT_PREFIX = "_ingest/"


def _blob() -> BlobServiceClient:
    if "blob" not in _state:
        _state["blob"] = BlobServiceClient(os.environ["STORAGE_URL"], credential=_cred)
    return _state["blob"]


def _process(name: str, data: bytes) -> dict:
    """Normalize + load one file. `name` is the bare file name (no container/prefix)."""
    res = normalize(name, data)
    try:
        existing = loader.existing_keys()
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
            loaded = loader.load(res.table, res.rows)
        except Exception as exc:            # noqa: BLE001
            logging.exception("ingest load failed for %s", name)
            status = f"load_error: {exc}"

    summary = {
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

    _write_report(name, report, summary)
    loader.write_log({
        "file_name": name, "profile": res.profile, "target_table": res.table,
        "rows_in": res.row_count_in, "rows_loaded": loaded, "rows_rejected": rejected,
        "status": status, "dq_json": report,
    })
    _state["last"] = summary
    return summary


def _write_report(name: str, report: dict, summary: dict) -> None:
    stem = name.rsplit(".", 1)[0]
    try:
        svc = _blob()
        svc.get_blob_client(REPORT_CONTAINER, f"{REPORT_PREFIX}{stem}.dq.md").upload_blob(
            render_markdown(report, f"Data-quality report — {name}").encode("utf-8"),
            overwrite=True,
        )
        svc.get_blob_client(REPORT_CONTAINER, f"{REPORT_PREFIX}{stem}.dq.json").upload_blob(
            json.dumps({"summary": summary, "report": report}, indent=2, default=str).encode(),
            overwrite=True,
        )
    except Exception:                       # noqa: BLE001
        logging.exception("could not write DQ report for %s", name)


# --------------------------------------------------------------------------
@ingest_bp.blob_trigger(
    arg_name="src",
    path="raw/inventory/{name}",
    connection="STORAGE_CONN",
    source=func.BlobSource.EVENT_GRID,      # required on Flex Consumption
)
def ingest_blob(src: func.InputStream):
    name = os.path.basename(src.name)
    if name.startswith("_"):               # skip _mapping.json / report artefacts
        return
    logging.info("ingest: raw/inventory/%s (%s bytes)", name, src.length)
    _process(name, src.read())


@ingest_bp.route(route="ingest", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def ingest_http(req: func.HttpRequest) -> func.HttpResponse:
    """{"blob": "servers.csv"} to pull from raw/inventory/, or POST raw file bytes
    with ?name=servers.csv."""
    name = req.params.get("name")
    body = req.get_body()
    if name and body:
        data = body
    else:
        try:
            blob_name = (req.get_json() or {}).get("blob")
        except ValueError:
            blob_name = None
        if not blob_name:
            return _json({"error": 'POST {"blob": "<file in raw/inventory/>"} or raw bytes with ?name='}, 400)
        name = os.path.basename(blob_name)
        data = _blob().get_blob_client("raw", f"{INVENTORY_PREFIX}{name}").download_blob().readall()

    return _json(_process(name, data))


@ingest_bp.route(route="ingest_status", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def ingest_status(req: func.HttpRequest) -> func.HttpResponse:
    return _json(_state.get("last") or {"status": "no ingestion has run in this worker"})


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status,
                             mimetype="application/json")
