"""
Load the sample-estate CSVs into the Landfall Azure SQL database.

    python sample-estate/load_estate.py                # truncate + load, env-driven
    python sample-estate/load_estate.py --append       # keep existing rows
    python sample-estate/load_estate.py --server X --database Y

Auth is Entra ID via DefaultAzureCredential (az login, VS, or a managed identity).
Reads AZURE_SQL_SERVER_FQDN / AZURE_SQL_DATABASE from the environment when not passed
(azd writes them to .azure/<env>/.env).
"""
import argparse
import csv
import os
import sys

import mssql_python
from azure.identity import DefaultAzureCredential

HERE = os.path.dirname(__file__)
NULLABLE_BLANK = True  # "" -> NULL

# table -> (csv file, columns to insert in order)
TABLES = [
    ("dbo.applications", "applications.csv",
     ["app_id", "app_name", "business_owner", "criticality", "users", "tech_stack",
      "db_engine", "internet_facing", "compliance_scope", "disposition", "complexity", "wave"]),
    ("dbo.servers", "servers.csv",
     ["server_id", "hostname", "env", "os_name", "os_version", "os_eol_date", "vcpu",
      "ram_gb", "provisioned_disk_gb", "used_disk_gb", "cpu_avg_pct", "cpu_peak_pct",
      "ram_avg_pct", "cluster", "datacenter", "powerstate", "app_id", "notes"]),
    ("dbo.storage", "storage.csv",
     ["storage_id", "server_id", "type", "size_gb", "iops", "target_service"]),
    ("dbo.dependencies", "dependencies.csv",
     ["src_id", "dst_id", "port", "protocol", "direction", "confidence"]),
]
# dependencies.src_id/dst_id can be "internet" (not a real server) - drop those rows,
# the servers.app_id FK and storage.server_id FK must resolve.


def rows(path, cols):
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            yield [None if (NULLABLE_BLANK and r[c] == "") else r[c] for c in cols]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("AZURE_SQL_SERVER_FQDN"))
    ap.add_argument("--database", default=os.environ.get("AZURE_SQL_DATABASE"))
    ap.add_argument("--append", action="store_true", help="do not truncate first")
    args = ap.parse_args()
    if not args.server or not args.database:
        sys.exit("need --server/--database or AZURE_SQL_SERVER_FQDN / AZURE_SQL_DATABASE")

    # the Free-offer DB is serverless and auto-pauses; the first connect may need to
    # wake it, so allow a generous login timeout
    conn = mssql_python.connect(
        f"Server={args.server};Database={args.database};Encrypt=yes;",
        token_provider=DefaultAzureCredential(),
        timeout=90,
    )
    cur = conn.cursor()

    if not args.append:
        # child tables first (FKs)
        for t in ("dbo.dependencies", "dbo.storage", "dbo.servers", "dbo.applications"):
            cur.execute(f"DELETE FROM {t}")
        print("cleared existing rows")

    server_ids = {r[0] for r in rows(os.path.join(HERE, "servers.csv"), ["server_id"])}

    for table, fname, cols in TABLES:
        path = os.path.join(HERE, fname)
        data = list(rows(path, cols))
        if table == "dbo.dependencies":
            si, di = cols.index("src_id"), cols.index("dst_id")
            kept = [r for r in data if r[si] in server_ids and r[di] in server_ids]
            print(f"{table}: dropping {len(data) - len(kept)} edges touching non-server nodes (e.g. 'internet')")
            data = kept
        placeholders = ", ".join(["?"] * len(cols))
        cur.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", data
        )
        print(f"{table}: inserted {len(data)} rows")

    conn.commit()

    for t in ("servers", "applications", "dependencies", "storage"):
        cur.execute(f"SELECT COUNT(*) FROM dbo.{t}")
        print(f"  dbo.{t}: {cur.fetchone()[0]} rows")
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
