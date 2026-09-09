"""Close-out export (PRD E9.5) — dump every engagement to a retained location
BEFORE `azd down --purge` destroys the deployment.

Each engagement becomes one `<customer>__<project>.landfall.zip` (same format as
the web `GET /api/engagements/<c>/<p>/export`, re-importable via
`POST /api/engagements/import`): its `raw/` inventory + docs, its `answers/`
artifacts + chat, an `export.json`, and — with `--sql` — a CSV of each of the six
inventory tables scoped to that engagement.

    python scripts/export_all.py                 # -> ./_closeout/<UTC>/  (blobs only)
    python scripts/export_all.py --sql           # + per-engagement SQL CSVs
    python scripts/export_all.py --out /mnt/archive/landfall --sql
    python scripts/export_all.py --dry-run       # list engagements + sizes, write nothing

Reads STORAGE_URL (or AZURE_STORAGE_BLOB_ENDPOINT) and, for --sql,
AZURE_SQL_SERVER_FQDN + AZURE_SQL_DATABASE — all present in `azd env get-values`.
Auth is DefaultAzureCredential (run `az login` first, or use the deploy identity).
Exits non-zero if any engagement fails to export.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import sys
import zipfile

RAW_C, ANS_C = "raw", "answers"
SQL_TABLES = ("servers", "applications", "dependencies", "storage", "performance", "ingest_log")


def _storage_url() -> str:
    return (os.environ.get("STORAGE_URL")
            or os.environ.get("AZURE_STORAGE_BLOB_ENDPOINT")
            or "")


def _svc():
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    url = _storage_url()
    if not url:
        sys.exit("STORAGE_URL / AZURE_STORAGE_BLOB_ENDPOINT not set")
    return BlobServiceClient(url, credential=DefaultAzureCredential())


def list_engagements(svc) -> list[str]:
    """Every '<customer>/<project>' that has a manifest under raw/engagements/."""
    raw = svc.get_container_client(RAW_C)
    out = []
    for b in raw.list_blobs(name_starts_with="engagements/"):
        parts = b.name.split("/")
        if len(parts) == 4 and parts[3] == "_engagement.json":
            out.append(f"{parts[1]}/{parts[2]}")
    return sorted(set(out))


def _copy_tree(zf: zipfile.ZipFile, cont, base: str, top: str) -> tuple[int, int]:
    n = size = 0
    for b in cont.list_blobs(name_starts_with=base):
        rel = b.name[len(base):]
        if not rel or rel.endswith("/.keep") or (b.size or 0) == 0:
            continue
        data = cont.download_blob(b.name).readall()
        zf.writestr(f"{top}/{rel}", data)
        n += 1
        size += len(data)
    return n, size


def _sql_connect():
    """Connect, retrying while a serverless DB resumes from auto-pause (~40 s)."""
    import time

    import mssql_python
    from azure.identity import DefaultAzureCredential

    server = os.environ.get("AZURE_SQL_SERVER_FQDN")
    database = os.environ.get("AZURE_SQL_DATABASE")
    if not (server and database):
        raise SystemExit("--sql needs AZURE_SQL_SERVER_FQDN + AZURE_SQL_DATABASE")
    last = None
    for i in range(5):
        try:
            return mssql_python.connect(
                f"Server={server};Database={database};Encrypt=yes;",
                token_provider=DefaultAzureCredential(), timeout=90)
        except Exception as exc:                       # noqa: BLE001
            last = exc
            if "not currently available" in str(exc) or "resuming" in str(exc).lower():
                print(f"    SQL resuming, retry {i + 1}/4 in 20s...")
                time.sleep(20)
                continue
            raise
    raise last


def _sql_dump(zf: zipfile.ZipFile, eid: str) -> int:
    conn = _sql_connect()
    rows_total = 0
    try:
        cur = conn.cursor()
        # Row-Level Security filters every table by SESSION_CONTEXT('engagement_id')
        # and fails closed — bind the session before any SELECT (E11.3).
        cur.execute("EXEC sp_set_session_context @key = N'engagement_id', @value = ?, "
                    "@read_only = 1", [eid])
        for t in SQL_TABLES:
            cur.execute(f"SELECT * FROM dbo.{t} WHERE engagement_id = ?", eid)
            cols = [c[0] for c in cur.description]
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(cols)
            rows = cur.fetchall()
            for r in rows:
                w.writerow(list(r))
            zf.writestr(f"sql/{t}.csv", buf.getvalue())
            rows_total += len(rows)
    finally:
        conn.close()
    return rows_total


def export_one(svc, eid: str, with_sql: bool) -> dict:
    raw = svc.get_container_client(RAW_C)
    ans = svc.get_container_client(ANS_C)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        rn, rs = _copy_tree(zf, raw, f"engagements/{eid}/", "raw")
        an, a_s = _copy_tree(zf, ans, f"engagements/{eid}/", "answers")
        sql_rows = None
        if with_sql:
            try:
                sql_rows = _sql_dump(zf, eid)
            except Exception as exc:                   # noqa: BLE001
                # never let a SQL hiccup lose the blob export — raw/ is the source
                # of truth and re-ingests on import.
                sql_rows = f"error: {type(exc).__name__}: {exc}"
                zf.writestr("sql/_ERROR.txt", str(sql_rows))
                print(f"    WARN {eid}: SQL dump failed, blobs still exported — {exc}")
        zf.writestr("export.json", json.dumps({
            "engagement": eid,
            "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "format": "landfall-engagement/1",
            "close_out": True,
            "sql_rows": sql_rows,
        }, indent=2))
    return {"engagement": eid, "bytes": buf.getbuffer().nbytes, "raw_files": rn,
            "answer_files": an, "sql_rows": sql_rows, "_data": buf.getvalue()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Close-out export of every engagement (E9.5)")
    ap.add_argument("--out", default=None, help="target dir (default ./_closeout/<UTC>/)")
    ap.add_argument("--sql", action="store_true", help="also dump the 6 inventory tables per engagement")
    ap.add_argument("--dry-run", action="store_true", help="list engagements + sizes, write nothing")
    args = ap.parse_args(argv)

    svc = _svc()
    engagements = list_engagements(svc)
    if not engagements:
        print("no engagements found")
        return 0
    print(f"{len(engagements)} engagement(s): {', '.join(engagements)}")

    if args.dry_run:
        for eid in engagements:
            raw = svc.get_container_client(RAW_C)
            ans = svc.get_container_client(ANS_C)
            sz = sum((b.size or 0) for c in (raw, ans)
                     for b in c.list_blobs(name_starts_with=f"engagements/{eid}/"))
            print(f"  {eid:40} ~{sz / 1024:,.0f} KB")
        return 0

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or os.path.join("_closeout", stamp)
    os.makedirs(out, exist_ok=True)

    manifest, failed = [], []
    for eid in engagements:
        try:
            r = export_one(svc, eid, args.sql)
        except Exception as exc:                       # noqa: BLE001
            print(f"  FAIL {eid}: {type(exc).__name__}: {exc}")
            failed.append(eid)
            continue
        fn = eid.replace("/", "__") + ".landfall.zip"
        with open(os.path.join(out, fn), "wb") as fh:
            fh.write(r.pop("_data"))
        r["file"] = fn
        manifest.append(r)
        sql_note = f", {r['sql_rows']} sql rows" if r["sql_rows"] is not None else ""
        print(f"  ok   {eid:40} {r['bytes'] / 1024:,.0f} KB  "
              f"({r['raw_files']} raw, {r['answer_files']} answers{sql_note})")

    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"exported_at": stamp, "engagements": manifest, "failed": failed}, fh, indent=2)
    print(f"\n{len(manifest)} exported to {out}/" + (f"  ·  {len(failed)} FAILED" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
