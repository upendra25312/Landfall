"""Cycle 12 — sqlguard (E8.3 allow-list SELECT parse, E8.4 loggable signature)."""
import pytest

from sqlguard import ALLOWED_TABLES, safe_select, signature


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM servers",
    "SELECT env, COUNT(*) FROM dbo.servers GROUP BY env",
    "WITH x AS (SELECT app_id FROM applications) SELECT COUNT(*) FROM x",
    "SELECT TOP 5 s.hostname FROM servers s JOIN applications a ON s.app_id = a.app_id",
    "SELECT SUM(size_gb) FROM storage WHERE type = 'file'  -- file shares only",
])
def test_accepts_legitimate_read_only_analytics(sql):
    assert safe_select(sql)


@pytest.mark.parametrize("sql,reason", [
    ("SELECT * FROM servers; DROP TABLE servers", "multiple statements"),
    ("UPDATE servers SET vcpu = 0", "not a SELECT"),
    ("SELECT * FROM sys.databases", "sys."),
    ("SELECT * FROM information_schema.tables", "information_schema"),
    ("SELECT * FROM secrets", "unknown table"),
    ("SELECT * FROM servers WHERE 1=1 WAITFOR DELAY '0:0:10'", "waitfor"),
    ("SELECT * FROM servers INTO dumped", "into"),
    ("EXEC xp_cmdshell 'dir'", "not a SELECT"),
    ("SELECT * FROM OPENROWSET('x','y','z')", "openrowset"),
    ("SELECT (1", "unbalanced"),
    ("", "empty"),
])
def test_rejects_dangerous_or_out_of_scope(sql, reason):
    with pytest.raises(ValueError):
        safe_select(sql)


def test_comment_hidden_keyword_is_still_caught():
    with pytest.raises(ValueError):
        safe_select("SELECT * FROM servers /* harmless */ UNION SELECT name, 1,2 FROM sys.tables")


def test_cte_names_are_not_treated_as_unknown_tables():
    sql = ("WITH prod AS (SELECT * FROM servers WHERE env='prod') "
           "SELECT COUNT(*) FROM prod")
    assert safe_select(sql)


def test_allow_list_is_the_six_inventory_tables():
    assert ALLOWED_TABLES == {"servers", "applications", "dependencies",
                              "storage", "performance", "ingest_log"}


def test_signature_carries_no_text():
    q = "how many prod Windows servers over 8 vCPU"
    sql = "SELECT COUNT(*) FROM dbo.servers WHERE env = 'prod' AND vcpu > 8"
    sig = signature(q, sql)
    assert q not in str(sig) and "prod" not in str(sig) and "SELECT" not in str(sig)
    assert sig["tables"] == ["servers"] and sig["shape"] == "count"
    assert len(sig["q_hash"]) == 12
    # same question -> same hash (stable), different question -> different
    assert signature(q)["q_hash"] == sig["q_hash"]
    assert signature("something else")["q_hash"] != sig["q_hash"]
