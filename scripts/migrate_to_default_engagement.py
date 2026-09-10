"""
Fold a pre-E11 single-tenant deployment into the `_default_/_default_` engagement
(PRD E11.11).

Cycles 1-17 wrote a flat layout:

    raw/inventory/*            raw/docs/*
    answers/estimate/latest.*
    dbo.servers / applications / ... rows with no (or empty) engagement_id

E11 keys everything by `<customer>/<project>`. This script moves the flat blobs
under `engagements/_default_/_default_/...`, writes that engagement's
`_engagement.json` if missing, and backfills the un-keyed SQL rows — so an
existing deploy keeps working while the flat paths are retired.

Idempotent. **Dry-run by default** — prints the plan and changes nothing. Pass
`--apply` to execute. `--skip-sql` / `--skip-blob` to do only one side.

Env (same as the other scripts):
  STORAGE_URL                     https://<acct>.blob.core.windows.net
  AZURE_SQL_SERVER_FQDN, AZURE_SQL_DATABASE   (for the SQL backfill)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

DEFAULT_ENGAGEMENT = "_default_/_default_"

# flat prefix (container, old prefix)  ->  new prefix within the same container
_BLOB_MOVES = [
    ("raw", "inventory/", f"engagements/{DEFAULT_ENGAGEMENT}/inventory/"),
    ("raw", "docs/", f"engagements/{DEFAULT_ENGAGEMENT}/docs/"),
    ("answers", "estimate/", f"engagements/{DEFAULT_ENGAGEMENT}/estimate/"),
]
_SQL_TABLES = ("servers", "applications", "dependencies", "performance",
               "storage", "ingest_log")


def _svc():
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    url = os.environ.get("STORAGE_URL")
    if not url:
        raise SystemExit("STORAGE_URL not set")
    return BlobServiceClient(url, credential=DefaultAzureCredential())


def _plan_blob(svc) -> list[tuple]:
    """[(container, src, dst)] for every flat blob that would move."""
    moves = []
    for container, old, new in _BLOB_MOVES:
        cc = svc.get_container_client(container)
        try:
            names = [b.name for b in cc.list_blobs(name_starts_with=old)]
        except Exception as exc:  # noqa: BLE001
            print(f"  ! cannot list {container}/{old}: {exc}")
            continue
        for name in names:
            rest = name[len(old):]
            if not rest or name.startswith("engagements/"):
                continue
            moves.append((container, name, new + rest))
    return moves


def _do_blob(svc, apply: bool) -> None:
    moves = _plan_blob(svc)
    if not moves:
        print("blob: nothing to migrate (no flat inventory/ docs/ estimate/ blobs).")
        return
    print(f"blob: {len(moves)} blob(s) to move" + ("" if apply else "  [dry-run]"))
    for container, src, dst in moves:
        print(f"  {container}: {src}  ->  {dst}")
        if not apply:
            continue
        cc = svc.get_container_client(container)
        data = cc.download_blob(src).readall()
        cc.upload_blob(dst, data, overwrite=True)
        cc.delete_blob(src)

    if apply:
        raw = svc.get_container_client("raw")
        key = f"engagements/{DEFAULT_ENGAGEMENT}/_engagement.json"
        try:
            raw.download_blob(key).readall()
            print("blob: _engagement.json already present.")
        except Exception:  # noqa: BLE001
            import datetime as _dt
            manifest = {
                "engagement": DEFAULT_ENGAGEMENT, "customer": "_default_", "project": "_default_",
                "customer_slug": "_default_", "project_slug": "_default_",
                "region": os.environ.get("AZURE_LOCATION") or "swedencentral",
                "target_region": os.environ.get("AZURE_LOCATION") or "swedencentral",
                "dr_region": None, "currency": "USD", "licensing_program": "MCA",
                "notes": "Seed engagement — folded in from the pre-E11 single-tenant layout.",
                "visibility": "all", "status": "active", "created_by": "migration",
                "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            }
            raw.upload_blob(key, json.dumps(manifest, indent=2).encode(), overwrite=True)
            print("blob: wrote _engagement.json for _default_/_default_.")


def _do_sql(apply: bool) -> None:
    if not os.environ.get("AZURE_SQL_SERVER_FQDN"):
        print("sql: AZURE_SQL_SERVER_FQDN not set — skipping the SQL backfill.")
        return
    try:
        import mssql_python
        from azure.identity import DefaultAzureCredential
    except Exception as exc:  # noqa: BLE001
        print(f"sql: driver unavailable ({exc}) — skipping.")
        return
    conn = mssql_python.connect(
        f"Server={os.environ['AZURE_SQL_SERVER_FQDN']};"
        f"Database={os.environ['AZURE_SQL_DATABASE']};Encrypt=yes;",
        token_provider=DefaultAzureCredential(), timeout=90)
    cur = conn.cursor()
    # the RLS filter predicate hides rows whose engagement_id != SESSION_CONTEXT,
    # so an UPDATE can't see the un-keyed rows while the policy is on.
    policy_on = False
    try:
        cur.execute("SELECT is_enabled FROM sys.security_policies WHERE name = 'EngagementFilter'")
        row = cur.fetchone()
        policy_on = bool(row and row[0])
    except Exception:  # noqa: BLE001
        pass

    total = 0
    if apply and policy_on:
        cur.execute("ALTER SECURITY POLICY dbo.EngagementFilter WITH (STATE = OFF)")
    try:
        for t in _SQL_TABLES:
            where = "engagement_id IS NULL OR LTRIM(RTRIM(engagement_id)) = '' OR engagement_id = 'None'"
            cur.execute(f"SELECT COUNT(*) FROM dbo.{t} WHERE {where}")
            n = cur.fetchone()[0]
            total += n
            print(f"  dbo.{t}: {n} un-keyed row(s)" + (" -> _default_/_default_" if n else ""))
            if apply and n:
                cur.execute(f"UPDATE dbo.{t} SET engagement_id = ? WHERE {where}",
                            [DEFAULT_ENGAGEMENT])
    finally:
        if apply and policy_on:
            cur.execute("ALTER SECURITY POLICY dbo.EngagementFilter WITH (STATE = ON)")
    if apply:
        conn.commit()
    print(f"sql: {total} row(s) " + ("backfilled." if apply else "would be backfilled  [dry-run]"))
    conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
    ap.add_argument("--skip-sql", action="store_true")
    ap.add_argument("--skip-blob", action="store_true")
    args = ap.parse_args(argv)

    print("=== migrate pre-E11 single-tenant data -> _default_/_default_ ===")
    print("MODE:", "APPLY" if args.apply else "DRY-RUN (pass --apply to execute)")
    if not args.skip_blob:
        _do_blob(_svc(), args.apply)
    if not args.skip_sql:
        _do_sql(args.apply)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
