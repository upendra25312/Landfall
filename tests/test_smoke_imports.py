"""Cycle 1 — the Function app still parses and wires the ingestion blueprint."""
import ast
import os

from conftest import API


def test_function_app_parses_and_registers_ingest_blueprint():
    src = open(os.path.join(API, "function_app.py"), encoding="utf-8").read()
    ast.parse(src)
    assert "from ingest.functions import ingest_bp" in src
    assert "app.register_functions(ingest_bp)" in src


def test_ingest_modules_parse():
    for rel in ("ingest/__init__.py", "ingest/core.py", "ingest/dq.py",
                "ingest/loader.py", "ingest/functions.py"):
        ast.parse(open(os.path.join(API, rel), encoding="utf-8").read())


def test_blob_trigger_uses_event_grid_source():
    src = open(os.path.join(API, "ingest/functions.py"), encoding="utf-8").read()
    assert 'path="raw/inventory/{name}"' in src
    assert "func.BlobSource.EVENT_GRID" in src
