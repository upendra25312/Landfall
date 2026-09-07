"""
Landfall inventory ingestion — the data-lake Normalize pipeline (PRD epic E1).

A client drops an inventory export into `raw/inventory/`. This package detects the
file's shape, maps its columns to `scripts/schema.sql`, normalises units, loads the
rows into Azure SQL keyed by source file (idempotent re-ingest), and writes a
data-quality report to `answers/_ingest/` for the pre-sales team.

Layers:
  core.py       pure logic — read a table, detect a source profile, normalise rows
  dq.py         pure logic — build the data-quality report
  loader.py     Azure SQL + Blob + ingest_log (imports azure/mssql lazily)
  functions.py  the Function blueprint (Event Grid blob trigger + HTTP helpers)
"""
from .core import normalize, detect_profile, PROFILES, NormResult
from .dq import build_report, render_markdown

__all__ = [
    "normalize",
    "detect_profile",
    "PROFILES",
    "NormResult",
    "build_report",
    "render_markdown",
]
