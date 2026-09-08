"""
Apply the inventory schema and grant the workload identity read-only access —
in pure Python (mssql-python + Entra token), so the postprovision hook needs
neither `sqlcmd` nor `azd` on PATH (PRD E9.1).

Reads from the environment (postprovision exports these from `azd env`):
  AZURE_SQL_SERVER_FQDN
  AZURE_SQL_DATABASE
  AZURE_USER_ASSIGNED_IDENTITY_NAME            (contained-user name for the grant)
  AZURE_USER_ASSIGNED_IDENTITY_PRINCIPAL_ID    (its object id — avoids Directory Readers)

Idempotent. Exits 0 on success; non-zero on a connection/auth failure so the hook
surfaces it.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
SCHEMA = HERE / "schema.sql"

_GRANT = """
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{name}')
    CREATE USER [{name}] FROM EXTERNAL PROVIDER WITH OBJECT_ID = '{oid}';
""".strip()
_ROLE = "ALTER ROLE db_datareader ADD MEMBER [{name}];"


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


_ONLY_COMMENTS = re.compile(r"\A(?:\s|--[^\n]*|/\*.*?\*/)*\Z", re.DOTALL)


def _run_batches(cur, script: str) -> int:
    """Execute a T-SQL script split on lines that are just GO. Comment-only
    batches are skipped (some drivers reject an empty statement)."""
    done = 0
    parts = re.split(r"(?im)^\s*GO\s*$", script)
    for sql in (p.strip() for p in parts):
        if sql and not _ONLY_COMMENTS.match(sql):
            cur.execute(sql)
            done += 1
    return done


def main() -> int:
    try:
        conn = _connect()
    except Exception as exc:                       # noqa: BLE001
        print(f"ERROR: could not connect to Azure SQL: {exc}", file=sys.stderr)
        return 2

    try:
        cur = conn.cursor()
        n = _run_batches(cur, SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
        print(f"schema.sql applied ({n} batches)")

        name = os.environ.get("AZURE_USER_ASSIGNED_IDENTITY_NAME")
        oid = os.environ.get("AZURE_USER_ASSIGNED_IDENTITY_PRINCIPAL_ID")
        if name and oid:
            cur.execute(_GRANT.format(name=name, oid=oid))
            cur.execute(_ROLE.format(name=name))
            conn.commit()
            print(f"granted db_datareader to [{name}] (query_inventory)")
        else:
            print("WARN: identity name/oid not set — skipped the read-only grant "
                  "(set AZURE_USER_ASSIGNED_IDENTITY_NAME / _PRINCIPAL_ID)", file=sys.stderr)
        return 0
    except Exception as exc:                       # noqa: BLE001
        print(f"ERROR applying SQL: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
