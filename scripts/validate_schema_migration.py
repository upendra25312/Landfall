"""Replay the additive schema twice; retain row-count and default-estate hashes only."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from apply_sql import SCHEMA, _connect, apply_schema
from smoke import _az, load_config

TABLES = ('applications', 'servers', 'dependencies', 'performance', 'storage', 'ingest_log')


def snapshot(conn):
    cur = conn.cursor()
    cur.execute("EXEC sys.sp_set_session_context @key=N'engagement_id', @value=N'_default_/_default_'")
    result = {}
    for table in TABLES:
        cur.execute(f'SELECT * FROM dbo.{table}')
        rows = sorted(json.dumps(list(r), default=str, sort_keys=True) for r in cur.fetchall())
        cur.execute("SELECT SUM(row_count) FROM sys.dm_db_partition_stats "
                    f"WHERE object_id=OBJECT_ID('dbo.{table}') AND index_id IN (0,1)")
        result[table] = {'global_rows': cur.fetchone()[0], 'default_rows': len(rows),
                         'default_sha256': hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
    conn.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rc, subscription, _ = _az(['account', 'show', '--query', 'id'])
    if rc or subscription != 'f609eb5b-df3e-4fab-9a1b-9a8fea2f157f':
        raise RuntimeError('Wrong Azure subscription')
    cfg = load_config()
    for key in ('AZURE_SQL_SERVER_FQDN', 'AZURE_SQL_DATABASE'):
        os.environ[key] = cfg[key]
    conn = _connect()
    try:
        before = snapshot(conn)
        passes = []
        for _ in range(2):
            batches = apply_schema(conn, SCHEMA.read_text(encoding='utf-8'))
            after = snapshot(conn)
            if after != before:
                raise RuntimeError('Row counts or default estate content changed')
            passes.append({'batches': batches, 'preserved': True})
        result = {'status': 'PASS', 'before': before, 'passes': passes,
                  'scope': 'Global row counts and full default-estate row hashes; no infrastructure provisioning'}
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('PASS: schema replayed twice; global row counts and default-estate hashes unchanged')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
