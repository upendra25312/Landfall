"""
Apply the inventory schema and grant the workload identity data access —
in pure Python (mssql-python + Entra token), so the postprovision hook needs
neither `sqlcmd` nor `azd` on PATH (PRD E9.1).

The Function App's user-assigned identity runs both the ingestion loader
(INSERT/DELETE on the inventory tables) and `query_inventory` (text-to-SQL), so
it is granted db_datareader + db_datawriter. `query_inventory` is held to
SELECT-only in code by `src/api/sqlguard.py` (single SELECT/WITH, keyword deny
list, table allow-list) — that guard, not a DB permission, is what stops the
text-to-SQL path from writing. Splitting ingest and query onto separate
identities is tracked as a hardening follow-up (PRD E8).

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
_ROLES = ("db_datareader", "db_datawriter")
_ROLE = "ALTER ROLE {role} ADD MEMBER [{name}];"


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


_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _is_only_comments(sql: str) -> bool:
    """True if the batch is nothing but whitespace + SQL comments. Strips the
    comments first — a single `\\A(?:\\s|--…|/\\*…\\*/)*\\Z` regex over a batch that
    ends in real SQL backtracks catastrophically (observed: 10 min at 100% CPU
    on schema.sql)."""
    stripped = _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", sql))
    return not stripped.strip()


def _run_batches(cur, script: str) -> int:
    """Execute a T-SQL script split on lines that are just GO. Comment-only
    batches are skipped (some drivers reject an empty statement)."""
    validate_schema(script)
    done = 0
    parts = re.split(r"(?im)^\s*GO\s*$", script)
    for sql in (p.strip() for p in parts):
        if sql and not _is_only_comments(sql):
            cur.execute(sql)
            done += 1
    return done


def validate_schema(script: str) -> None:
    """Fail before executing any batch. This accepts trusted repository SQL only.

    Inspect strings too so dynamic SQL cannot hide destructive statements. Remove
    comments as whitespace so DROP/**/TABLE cannot bypass the check.
    """
    clean = _LINE_COMMENT.sub(' ', _BLOCK_COMMENT.sub(' ', script))
    if re.search(r'\b(DROP|TRUNCATE|DELETE|MERGE|UPDATE)\b', clean, re.I):
        raise ValueError('Schema migration contains destructive SQL')
    if re.search(r'\bSTATE\s*=\s*OFF\b', clean, re.I):
        raise ValueError('Schema migration must not disable row-level security')


def apply_schema(conn, script: str) -> int:
    """Apply all batches atomically; serialize concurrent provision hooks."""
    validate_schema(script)
    try:
        cur = conn.cursor()
        cur.execute("SET XACT_ABORT ON; IF @@TRANCOUNT = 0 BEGIN TRANSACTION;")
        cur.execute("""DECLARE @result INT;
EXEC @result = sys.sp_getapplock @Resource=N'landfall-schema',
    @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=30000;
IF @result < 0 THROW 51002, 'Could not lock schema migration', 1;""")
        n = _run_batches(cur, script)
        conn.commit()
        return n
    except Exception:
        conn.rollback()
        raise


def main() -> int:
    script = SCHEMA.read_text(encoding="utf-8")
    validate_schema(script)
    try:
        conn = _connect()
    except Exception as exc:                       # noqa: BLE001
        print(f"ERROR: could not connect to Azure SQL: {exc}", file=sys.stderr)
        return 2

    try:
        cur = conn.cursor()
        n = apply_schema(conn, script)
        print(f"schema.sql applied ({n} batches)")

        name = os.environ.get("AZURE_USER_ASSIGNED_IDENTITY_NAME")
        oid = os.environ.get("AZURE_USER_ASSIGNED_IDENTITY_PRINCIPAL_ID")
        if name and oid:
            cur.execute(_GRANT.format(name=name, oid=oid))
            for role in _ROLES:
                cur.execute(_ROLE.format(role=role, name=name))
            conn.commit()
            print(f"granted {' + '.join(_ROLES)} to [{name}] "
                  "(ingestion loader writes; query_inventory is SELECT-only in code)")
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
