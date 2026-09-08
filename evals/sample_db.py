"""
Load sample-estate/*.csv into an in-memory SQLite database and run T-SQL against
it through a small dialect shim — the offline substrate for the eval harness
(PRD E7.1). Test-only: the shim covers just the constructs the golden query set
uses, not T-SQL in general.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "sample-estate")
AS_OF = "2026-09-08"          # fixed "today" so evals are date-independent

# column -> python coercion. Anything not listed stays TEXT.
_NUM = {
    "servers": ["vcpu", "ram_gb", "provisioned_disk_gb", "used_disk_gb", "cpu_avg_pct",
                "cpu_peak_pct", "cpu_p95_pct", "ram_avg_pct", "ram_p95_pct",
                "disk_iops_avg", "disk_iops_peak", "net_in_gb_30d", "net_out_gb_30d"],
    "applications": ["criticality", "users", "internet_facing", "wave"],
    "dependencies": ["port", "bytes_30d_gb", "flows_30d"],
    "storage": ["size_gb", "iops"],
    "performance": ["cpu_avg_pct", "cpu_peak_pct", "cpu_p95_pct", "mem_avg_pct",
                    "mem_peak_pct", "mem_p95_pct", "disk_iops_avg", "disk_iops_peak",
                    "disk_read_iops_avg", "disk_write_iops_avg", "disk_throughput_mbps_avg",
                    "net_in_gb", "net_out_gb", "net_in_peak_mbps", "net_out_peak_mbps"],
}
_FILES = ["servers", "applications", "dependencies", "storage", "performance"]


def _coerce(v: str):
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except ValueError:
        return v


def build_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for name in _FILES:
        path = os.path.join(SAMPLE, name + ".csv")
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            continue
        cols = list(rows[0].keys())
        conn.execute(f"CREATE TABLE {name} ({', '.join(c + ' ' + _decl(name, c) for c in cols)})")
        nums = set(_NUM.get(name, []))
        conn.executemany(
            f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})",
            [tuple(_coerce(r[c]) if c in nums else (r[c] or None) for c in cols) for r in rows],
        )
    conn.commit()
    return conn


def _decl(table: str, col: str) -> str:
    return "REAL" if col in _NUM.get(table, []) else "TEXT"


# --- T-SQL -> SQLite shim ------------------------------------------------

def to_sqlite(sql: str) -> str:
    s = sql.strip().rstrip(";")
    s = re.sub(r"(?is)\bSYSUTCDATETIME\(\)|\bGETDATE\(\)|\bCURRENT_TIMESTAMP\b", f"'{AS_OF}'", s)
    s = re.sub(r"(?is)CAST\(\s*'%s'\s+AS\s+DATE\s*\)" % re.escape(AS_OF), f"'{AS_OF}'", s)
    s = re.sub(r"(?is)\bISNULL\s*\(", "IFNULL(", s)
    s = re.sub(r"(?is)\bLEN\s*\(", "LENGTH(", s)
    s = re.sub(r"(?is)CAST\(\s*(.+?)\s+AS\s+DECIMAL\([^)]*\)\s*\)", r"CAST(\1 AS REAL)", s)
    s = re.sub(r"(?is)CAST\(\s*(.+?)\s+AS\s+FLOAT\s*\)", r"CAST(\1 AS REAL)", s)
    # DATEDIFF(DAY, a, b) -> integer day difference
    s = re.sub(r"(?is)DATEDIFF\(\s*day\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
               r"CAST(julianday(\2) - julianday(\1) AS INTEGER)", s)
    # SELECT TOP n ... -> ... LIMIT n
    m = re.match(r"(?is)^\s*SELECT\s+TOP\s+(\d+)\s+(.*)$", s)
    if m:
        s = f"SELECT {m.group(2)} LIMIT {m.group(1)}"
    return s


def run_tsql(conn: sqlite3.Connection, sql: str):
    cur = conn.execute(to_sqlite(sql))
    return [tuple(r) for r in cur.fetchall()]


def scalar(conn: sqlite3.Connection, sql: str):
    rows = run_tsql(conn, sql)
    return rows[0][0] if rows and rows[0] else None
