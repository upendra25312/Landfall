"""Answer-quality telemetry (PRD E9.4).

`event(name, **dims)` writes one structured log line. On Azure Functions the
Application Insights logging integration maps `record.custom_dimensions` to
`customDimensions`, so each event is queryable in Log Analytics as:

    traces | where customDimensions.event == "query_inventory"

No new dependency, no SDK — just `logging`. Every call is best-effort: a
telemetry failure must never break a tool.

`eng_hash()` keeps the raw customer/project out of telemetry — an operator can
still group by engagement, just not read the client name from the logs.
"""
from __future__ import annotations

import hashlib
import logging

_log = logging.getLogger("landfall.obs")


def eng_hash(engagement: str | None) -> str:
    if not engagement:
        return "none"
    return hashlib.sha256(engagement.strip().lower().encode()).hexdigest()[:12]


def _clean(dims: dict) -> dict:
    out = {"event": dims.pop("_name", "event")}
    for k, v in dims.items():
        if v is None:
            continue
        out[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    return out


def event(name: str, **dims) -> None:
    """One telemetry event. Never raises."""
    try:
        dims["_name"] = name
        _log.info(name, extra={"custom_dimensions": _clean(dims)})
    except Exception:                                   # noqa: BLE001 - telemetry is never load-bearing
        pass
