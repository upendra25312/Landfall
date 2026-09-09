"""Web-tier telemetry (PRD E9.4).

The FastAPI chat app runs in its own container, so it can't share
`src/api/obs.py`. Same idea, different plumbing:

- `configure_telemetry()` wires `azure-monitor-opentelemetry` when
  `APPLICATIONINSIGHTS_CONNECTION_STRING` is set (it always is on `ca-web` — see
  `infra/resources.bicep`). It auto-instruments FastAPI, so every route gets
  `requests` telemetry (name, result code, duration) with no code, matching what
  Azure Functions gives the API tier. Absent the env var (local, tests) it is a
  no-op and the SDK is never imported.
- `event(name, **dims)` writes one structured log line. The OpenTelemetry logging
  handler maps `extra=` fields to `customDimensions`, so an event is queryable as
  `traces | where customDimensions.event == "web_chat"`.

`eng_hash()` keeps the raw customer/project out of telemetry. Every call is
best-effort — telemetry must never break a request.
"""
from __future__ import annotations

import hashlib
import logging
import os

_log = logging.getLogger("landfall.web")

_RESERVED = {  # LogRecord attributes an `extra=` key must not shadow
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


def configure_telemetry() -> None:
    """Forward web-tier logs + request telemetry to Application Insights. No-op
    unless the connection string is present. Never raises."""
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(logger_name="landfall")
        _log.info("Application Insights telemetry configured")
    except Exception:  # noqa: BLE001 - telemetry is never load-bearing
        logging.getLogger(__name__).exception("could not configure App Insights telemetry")


def eng_hash(engagement: str | None) -> str:
    if not engagement:
        return "none"
    return hashlib.sha256(engagement.strip().lower().encode()).hexdigest()[:12]


def event(name: str, **dims) -> None:
    """One telemetry event. Never raises."""
    try:
        extra = {"event": name}
        for k, v in dims.items():
            if v is None or k in _RESERVED:
                continue
            extra[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
        _log.info(name, extra=extra)
    except Exception:  # noqa: BLE001
        pass
