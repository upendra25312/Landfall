"""Cycle 1 — loader pure logic (no database): dedupe + schema column alignment."""
import os
import re

from conftest import ROOT

from ingest.loader import _dedupe, TABLE_COLS


def test_dedupe_keeps_last_write_per_primary_key():
    rows = [
        {"server_id": "s1", "vcpu": 2, "source_file": "a.csv"},
        {"server_id": "s2", "vcpu": 4, "source_file": "a.csv"},
        {"server_id": "s1", "vcpu": 8, "source_file": "a.csv"},
    ]
    out = _dedupe(rows, "servers")
    assert [r["server_id"] for r in out] == ["s2", "s1"]
    assert next(r for r in out if r["server_id"] == "s1")["vcpu"] == 8


def test_dependencies_are_never_deduped():
    rows = [{"src_id": "a", "dst_id": "b", "source_file": "d.csv"} for _ in range(3)]
    assert len(_dedupe(rows, "dependencies")) == 3


def test_loader_columns_match_schema_sql():
    schema = open(os.path.join(ROOT, "scripts", "schema.sql"), encoding="utf-8").read()
    for table, cols in TABLE_COLS.items():
        block = re.search(rf"CREATE TABLE dbo\.{table} \((.*?)\n\);", schema, re.S)
        assert block, f"no CREATE TABLE for {table}"
        declared = set(re.findall(r"^\s{4}(\w+)\s", block.group(1), re.M))
        missing = set(cols) - declared
        assert not missing, f"{table}: loader inserts columns not in schema: {missing}"
