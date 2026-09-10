"""Schema changes must fail before writes or roll back the entire transaction."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('apply_sql', ROOT / 'scripts/apply_sql.py')
sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sql)


@pytest.mark.parametrize('statement', [
    'DROP TABLE dbo.servers', 'drop/**/table dbo.servers',
    'TRUNCATE TABLE dbo.servers', 'DELETE FROM dbo.servers',
    "EXEC(N'DROP TABLE dbo.servers')", 'UPDATE dbo.servers SET vcpu=0',
    'ALTER SECURITY POLICY dbo.EngagementFilter WITH (STATE=OFF)',
])
def test_rejects_before_first_batch(statement):
    cursor = Mock()
    with pytest.raises(ValueError):
        sql._run_batches(cursor, 'SELECT 1;\nGO\n' + statement)
    cursor.execute.assert_not_called()


def test_additive_schema_covers_all_tables_and_preserves_rls():
    script = sql.SCHEMA.read_text(encoding='utf-8')
    sql.validate_schema(script)
    for table in ('servers', 'applications', 'dependencies', 'performance', 'storage', 'ingest_log'):
        assert f"IF OBJECT_ID('dbo.{table}', 'U') IS NULL" in script
        assert f"COL_LENGTH('dbo.{table}', 'engagement_id') IS NULL" in script
    assert 'ALTER SECURITY POLICY dbo.EngagementFilter WITH (STATE = ON)' in script


def test_failed_later_batch_rolls_back():
    conn = Mock()
    conn.cursor.return_value.execute.side_effect = [None, None, None, RuntimeError('DDL failed')]
    with pytest.raises(RuntimeError):
        sql.apply_schema(conn, 'SELECT 1;\nGO\nSELECT 2;')
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_success_commits_once():
    conn = Mock()
    assert sql.apply_schema(conn, '-- comment\nGO\nSELECT 1;') == 1
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
