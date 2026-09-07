"""
Load normalised rows into Azure SQL and record the run (PRD E1.1 / E1.5).

Idempotent by source file: `load()` deletes the rows a file previously produced
(`WHERE source_file = ?`) and re-inserts, so re-uploading a corrected export
replaces only its own rows. Azure / mssql imports are lazy so `core` and `dq`
stay unit-testable without a database.
"""
from __future__ import annotations

import json
import logging
import os

# insert column order per table (schema.sql). `ingested_at` defaults in the DB.
TABLE_COLS = {
    "servers": ["server_id", "hostname", "env", "os_name", "os_version", "os_eol_date",
                "vcpu", "ram_gb", "provisioned_disk_gb", "used_disk_gb", "cpu_avg_pct",
                "cpu_peak_pct", "ram_avg_pct", "disk_iops_avg", "disk_iops_peak",
                "net_in_gb_30d", "net_out_gb_30d", "cluster", "datacenter", "powerstate",
                "app_id", "notes", "source_file"],
    "applications": ["app_id", "app_name", "business_owner", "criticality", "users",
                     "tech_stack", "db_engine", "internet_facing", "compliance_scope",
                     "disposition", "complexity", "wave", "source_file"],
    "dependencies": ["src_id", "dst_id", "port", "protocol", "direction", "confidence",
                     "bytes_30d_gb", "flows_30d", "last_seen", "source_file"],
    "storage": ["storage_id", "server_id", "type", "size_gb", "iops", "target_service",
                "source_file"],
    "performance": ["server_id", "sample_date", "cpu_avg_pct", "cpu_peak_pct", "cpu_p95_pct",
                    "mem_avg_pct", "mem_peak_pct", "mem_p95_pct", "disk_iops_avg",
                    "disk_iops_peak", "disk_read_iops_avg", "disk_write_iops_avg",
                    "disk_throughput_mbps_avg", "net_in_gb", "net_out_gb",
                    "net_in_peak_mbps", "net_out_peak_mbps", "source_file"],
}
_PK = {"servers": "server_id", "applications": "app_id", "storage": "storage_id"}


def _connect():
    import mssql_python
    from azure.identity import DefaultAzureCredential

    server = os.environ["AZURE_SQL_SERVER_FQDN"]
    database = os.environ["AZURE_SQL_DATABASE"]
    return mssql_python.connect(
        f"Server={server};Database={database};Encrypt=yes;",
        token_provider=DefaultAzureCredential(),
        timeout=90,
    )


def _dedupe(rows: list[dict], table: str) -> list[dict]:
    pk = _PK.get(table)
    if not pk:
        return rows
    seen, out = set(), []
    for r in reversed(rows):            # last write wins
        v = r.get(pk)
        if v in seen:
            continue
        seen.add(v)
        out.append(r)
    return list(reversed(out))


def load(table: str, rows: list[dict], conn=None) -> int:
    """Replace this source file's rows in `table`. Returns rows written."""
    if table not in TABLE_COLS:
        raise ValueError(f"unknown table {table!r}")
    rows = _dedupe(rows, table)
    if not rows:
        return 0
    cols = TABLE_COLS[table]
    source_file = rows[0]["source_file"]
    data = [[r.get(c) for c in cols] for r in rows]
    placeholders = ", ".join(["?"] * len(cols))

    own = conn is None
    conn = conn or _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM dbo.{table} WHERE source_file = ?", [source_file])
        cur.executemany(
            f"INSERT INTO dbo.{table} ({', '.join(cols)}) VALUES ({placeholders})", data
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
    logging.info("ingest.load %s: %d rows from %s", table, len(data), source_file)
    return len(data)


def existing_keys(conn=None) -> dict:
    """server_id / app_id sets already in the DB (for cross-file orphan checks)."""
    own = conn is None
    try:
        conn = conn or _connect()
    except Exception:                    # DB unreachable -> caller proceeds without it
        logging.exception("ingest.existing_keys: DB unavailable")
        return {}
    try:
        cur = conn.cursor()
        out = {}
        for tbl, col in (("servers", "server_id"), ("applications", "app_id")):
            try:
                cur.execute(f"SELECT {col} FROM dbo.{tbl}")
                out[tbl] = {r[0] for r in cur.fetchall()}
            except Exception:
                out[tbl] = set()
        return out
    finally:
        if own:
            conn.close()


def write_log(entry: dict, conn=None) -> None:
    cols = ["file_name", "profile", "target_table", "rows_in", "rows_loaded",
            "rows_rejected", "status", "dq_json"]
    vals = [entry.get(c) for c in cols[:-1]] + [json.dumps(entry.get("dq_json") or {})[:60000]]
    own = conn is None
    try:
        conn = conn or _connect()
    except Exception:
        logging.exception("ingest.write_log: DB unavailable, skipping ingest_log row")
        return
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO dbo.ingest_log ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
            vals,
        )
        if own:
            conn.commit()
    except Exception:
        logging.exception("ingest.write_log failed")
    finally:
        if own:
            conn.close()
