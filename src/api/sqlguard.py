"""
Read-only SQL guard for `query_inventory` (PRD E8.3).

    from sqlguard import safe_select, signature
    sql = safe_select(candidate)          # -> cleaned SQL, or raises ValueError

Rules: one statement, must be SELECT / WITH, references only the known inventory
tables, and contains no write / DDL / admin / timing construct. Pure — no Azure.
`signature()` returns a loggable fingerprint that never contains the SQL text
(E8.4).
"""
from __future__ import annotations

import hashlib
import re

MAX_SQL_LEN = 4000
ALLOWED_TABLES = {
    "servers", "applications", "dependencies", "storage", "performance", "ingest_log",
}

_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|exec|"
    r"execute|into|backup|restore|waitfor|delay|shutdown|reconfigure|dbcc|"
    r"openrowset|opendatasource|openquery|openxml|bulk|pwdencrypt|xp_\w*|sp_\w*|"
    r"sys\.|information_schema|fn_\w*|for\s+xml|for\s+json)\b",
    re.IGNORECASE,
)
_TABLE_REF = re.compile(r"\b(?:from|join)\s+(?:\[?dbo\]?\.)?\[?([a-z_][a-z0-9_]*)\]?",
                        re.IGNORECASE)
_STARTS = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def safe_select(sql: str, allowed_tables: set[str] | None = None) -> str:
    allowed = {t.lower() for t in (allowed_tables or ALLOWED_TABLES)}
    s = _strip_fences(sql)
    bare = _COMMENT.sub(" ", s).strip().rstrip(";").strip()

    if not bare:
        raise ValueError("empty query")
    if len(bare) > MAX_SQL_LEN:
        raise ValueError("query too long")
    if not _STARTS.match(bare):
        raise ValueError("not a SELECT / WITH")
    if ";" in bare:
        raise ValueError("multiple statements")
    if bare.count("(") != bare.count(")"):
        raise ValueError("unbalanced parentheses")
    m = _FORBIDDEN.search(bare)
    if m:
        raise ValueError(f"disallowed keyword: {m.group(0).strip().lower()}")

    refs = {t.lower() for t in _TABLE_REF.findall(bare)}
    # CTE names are allowed as table refs; strip them out before the allow-list check
    ctes = {c.lower() for c in re.findall(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(", bare, re.IGNORECASE)}
    unknown = refs - allowed - ctes
    if unknown:
        raise ValueError(f"unknown table(s): {', '.join(sorted(unknown))}")
    if not refs:
        raise ValueError("no table referenced")
    return bare


_SHAPE = [
    (re.compile(r"^\s*select\s+count\s*\(", re.IGNORECASE), "count"),
    (re.compile(r"\b(sum|avg|min|max)\s*\(", re.IGNORECASE), "aggregate"),
    (re.compile(r"\bgroup\s+by\b", re.IGNORECASE), "group_by"),
    (re.compile(r"^\s*select\s+top\b", re.IGNORECASE), "sample"),
]


def signature(question: str, sql: str | None = None) -> dict:
    """A loggable fingerprint — no question text, no SQL text (E8.4)."""
    q = (question or "").strip()
    sig = {"q_hash": hashlib.sha256(q.encode("utf-8")).hexdigest()[:12],
           "q_len": len(q)}
    if sql:
        bare = _COMMENT.sub(" ", sql)
        sig["tables"] = sorted({t.lower() for t in _TABLE_REF.findall(bare)})
        sig["shape"] = next((name for rx, name in _SHAPE if rx.search(bare)), "select")
    return sig
