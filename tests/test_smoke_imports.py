"""Cycle 1 — the Function app still parses and wires the ingestion blueprint."""
import ast
import os

from conftest import API


def test_function_app_parses_and_registers_all_blueprints():
    src = open(os.path.join(API, "function_app.py"), encoding="utf-8").read()
    ast.parse(src)
    for bp in ("ingest_bp", "cost_bp", "bp"):
        assert f"app.register_functions({bp})" in src


def test_ingest_and_cost_modules_parse():
    for rel in ("ingest/__init__.py", "ingest/core.py", "ingest/dq.py",
                "ingest/loader.py", "ingest/functions.py",
                "cost/__init__.py", "cost/config.py", "cost/skus.py",
                "cost/rightsize.py", "cost/functions.py"):
        ast.parse(open(os.path.join(API, rel), encoding="utf-8").read())


def test_vm_rightsize_route_lives_in_cost_not_tools():
    assert "route=\"vm_rightsize\"" in open(os.path.join(API, "cost/functions.py"), encoding="utf-8").read()
    assert "route=\"vm_rightsize\"" not in open(os.path.join(API, "tools.py"), encoding="utf-8").read()


def test_blob_trigger_uses_event_grid_source():
    src = open(os.path.join(API, "ingest/functions.py"), encoding="utf-8").read()
    assert 'path="raw/inventory/{name}"' in src
    assert "func.BlobSource.EVENT_GRID" in src
