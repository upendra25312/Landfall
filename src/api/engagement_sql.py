"""
Scope a SQL connection to one engagement (PRD E11.3).

Every reader must call ``set_engagement(cursor, engagement_id)`` right after
opening a connection and before any SELECT. The Row-Level Security policy in
scripts/schema.sql filters every table by ``SESSION_CONTEXT('engagement_id')``;
with no context set it returns no rows, so this call is not optional.

INSERTs are not affected by the filter predicate — the loader writes
``engagement_id`` into each row explicitly — but the loader still sets the
context so its DELETE-before-INSERT only touches its own engagement.
"""
from __future__ import annotations

from engagement import normalize_engagement


def set_engagement(cursor, engagement_id: str) -> str:
    """Bind this connection's session to one engagement. Returns the canonical id.
    Raises ValueError for a malformed id (before any DB round-trip)."""
    eid = normalize_engagement(engagement_id)
    cursor.execute(
        "EXEC sp_set_session_context @key = N'engagement_id', @value = ?, @read_only = 1",
        [eid],
    )
    return eid
