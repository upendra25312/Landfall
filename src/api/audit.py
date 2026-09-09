"""
Per-engagement audit trail (PRD E11.10 — "every run is attributable").

One append-only JSON-lines blob per engagement:

    answers/engagements/<customer>/<project>/_audit.jsonl

Each line: {"at": <utc iso>, "actor": <entra user or "unknown">, "event": <slug>,
            ...event-specific detail}. Events: `engagement_created`, `run_engagement`,
`publish_estimate`, `calc_run_staged`. Best-effort — a failed audit write never
fails the operation it records.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging

import engagement as eng

AUDIT_FILE = "_audit.jsonl"
_MAX_RETURN = 500


def audit_key(engagement_id: str) -> str:
    return f"{eng.answers_prefix(engagement_id)}/{AUDIT_FILE}"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def record(container_client, engagement_id: str, event: str,
           actor: str | None = None, **detail) -> None:
    """Append one audit line. `container_client` is a blob ContainerClient for the
    `answers` container. Swallows every error (logs it)."""
    entry = {"at": _now(), "actor": actor or "unknown", "event": event}
    entry.update({k: v for k, v in detail.items() if v is not None})
    key = audit_key(engagement_id)
    try:
        bc = container_client.get_blob_client(key)
        try:
            prev = bc.download_blob().readall()
        except Exception:                          # noqa: BLE001 - first entry
            prev = b""
        bc.upload_blob(prev + json.dumps(entry, default=str).encode() + b"\n",
                       overwrite=True)
    except Exception:                             # noqa: BLE001
        logging.exception("audit: could not record %s for %s", event, engagement_id)


def read(container_client, engagement_id: str, limit: int = _MAX_RETURN) -> list[dict]:
    """Return the engagement's audit entries, newest first (at most `limit`)."""
    try:
        raw = container_client.get_blob_client(audit_key(engagement_id)).download_blob().readall()
    except Exception:                             # noqa: BLE001
        return []
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:                         # noqa: BLE001
            continue
    out.reverse()
    return out[: max(1, int(limit or _MAX_RETURN))]
