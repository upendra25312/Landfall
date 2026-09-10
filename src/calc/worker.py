"""
ca-calc queue consumer (PRD E11.16).

`build_calculator_estimate` (the Function) stages the spec at
`<prefix>/_calc_spec.json`, writes a `building` marker, and drops one message on
the `calc-jobs` queue:

    {"engagement", "container", "prefix", "spec_blob", "queued_at"}

This worker drains the queue: for each message it reads the spec, drives the real
Azure Pricing Calculator (Playwright), parses + reconciles the export, and writes

    <prefix>/landing_zone.xlsx   the calculator's own file (the POE)
    <prefix>/landing_zone.json   {status: ready|failed, totals, spec, ...}
    <prefix>/landing_zone.png    screenshot

using this container's workload identity (Storage Blob Data Owner + Storage Queue
Data Contributor on `uami`). A message is deleted whether the run succeeds or
fails (a failure writes a `failed` marker) so a broken job never poison-loops.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as _dt
import json
import logging
import os

from driver import build_estimate
from calculator_export import parse_calculator_export, reconcile

for _n in ("azure.core.pipeline.policies.http_logging_policy", "azure.identity", "azure.storage"):
    logging.getLogger(_n).setLevel(logging.WARNING)

_POLL_IDLE_S = 10
_VISIBILITY_S = 1800          # 30 min — longer than the worst-case calculator drive
_MAX_DEQUEUE = 3
_RUN_BUDGET_S = 1500          # hard cap on one calculator drive


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _clients():
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient
    from azure.storage.queue import QueueClient

    cred = DefaultAzureCredential()
    blob = BlobServiceClient(os.environ["STORAGE_URL"], credential=cred)
    queue = QueueClient(account_url=os.environ["STORAGE_QUEUE_URL"].rstrip("/"),
                        queue_name=os.environ.get("CALC_QUEUE", "calc-jobs"),
                        credential=cred)
    return blob, queue


def _put(cc, name, data, ctype):
    from azure.storage.blob import ContentSettings
    cc.upload_blob(name, data, overwrite=True,
                   content_settings=ContentSettings(content_type=ctype))


async def _process(blob, job: dict) -> None:
    container, prefix = job["container"], job["prefix"].rstrip("/")
    cc = blob.get_container_client(container)
    spec = json.loads(cc.get_blob_client(job["spec_blob"]).download_blob().readall())

    try:
        run = await asyncio.wait_for(build_estimate(spec), timeout=_RUN_BUDGET_S)
        xlsx = base64.b64decode(run["xlsx_b64"])
        parsed = parse_calculator_export(xlsx)
        rec = reconcile(parsed, spec.get("internal_monthly_estimate"))
        summary = {
            "status": "ready",
            "engagement": spec.get("engagement"),
            "estimate_name": parsed["estimate_name"],
            "region": spec.get("region_azure") or spec.get("region_default"),
            "currency": parsed["currency"],
            "monthly_total": parsed["total_monthly"],
            "annual": parsed["annual"],
            "upfront_total": parsed["total_upfront"],
            "support_monthly": parsed["support_monthly"],
            "line_items": parsed["line_items"],
            "line_count": parsed["line_count"],
            "created_at": parsed["created_at"],
            "calculator_url": run.get("calculator"),
            "monthly_header": run.get("monthly_header"),
            "reconciliation": rec,
            "applied": run.get("applied", []),
            "skipped": run.get("skipped", []),
            "spec": spec,
            "built_at": _now(),
            "source": "azure-pricing-calculator",
            "note": "Excel exported by the Azure Pricing Calculator - submit landing_zone.xlsx "
                    "as the Proof of Estimate. All prices are the calculator's; quantities are "
                    "Landfall figures (see spec + applied/skipped).",
        }
        _put(cc, f"{prefix}/landing_zone.xlsx", xlsx,
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        _put(cc, f"{prefix}/landing_zone.json", json.dumps(summary, default=str).encode(),
             "application/json")
        if run.get("screenshot_b64"):
            _put(cc, f"{prefix}/landing_zone.png", base64.b64decode(run["screenshot_b64"]),
                 "image/png")
        logging.info("POE ready for %s (monthly=%s)", spec.get("engagement"), parsed.get("total_monthly"))
    except Exception as exc:  # noqa: BLE001
        logging.exception("calculator run failed for %s", spec.get("engagement"))
        _put(cc, f"{prefix}/landing_zone.json", json.dumps({
            "status": "failed", "engagement": spec.get("engagement"), "error": str(exc),
            "failed_at": _now(), "estimate_name": spec.get("estimate_name"), "spec": spec,
        }, default=str).encode(), "application/json")


async def run_once(max_jobs: int = 8) -> int:
    """Drain the queue once and exit — the entrypoint for the event-driven
    Container Apps **Job** (E13.13). KEDA starts one execution per batch of
    `queueLength` messages; this drains whatever is visible (up to `max_jobs`),
    then returns so the replica terminates. Returns the number of jobs processed.
    """
    try:
        blob, queue = _clients()
    except Exception:  # noqa: BLE001
        logging.exception("ca-calc job: cannot build storage clients")
        return 0
    done = 0
    while done < max_jobs:
        msgs = list(queue.receive_messages(visibility_timeout=_VISIBILITY_S, max_messages=1))
        if not msgs:
            break
        for m in msgs:
            try:
                job = json.loads(m.content)
                if m.dequeue_count and m.dequeue_count > _MAX_DEQUEUE:
                    logging.error("dropping calc job after %s attempts: %s",
                                  m.dequeue_count, m.content[:200])
                else:
                    await _process(blob, job)
                    done += 1
            except Exception:  # noqa: BLE001
                logging.exception("calc job errored (deleting to avoid poison loop)")
            finally:
                try:
                    queue.delete_message(m)
                except Exception:  # noqa: BLE001
                    logging.exception("could not delete calc message")
    logging.info("ca-calc job: processed %s job(s), exiting", done)
    return done


async def consume_forever() -> None:
    try:
        blob, queue = _clients()
    except Exception:  # noqa: BLE001
        logging.exception("ca-calc worker: cannot build storage clients — not consuming")
        return
    logging.info("ca-calc worker: polling queue %s", queue.queue_name)
    while True:
        try:
            msgs = queue.receive_messages(visibility_timeout=_VISIBILITY_S, max_messages=1)
            got = False
            for m in msgs:
                got = True
                try:
                    job = json.loads(m.content)
                    if m.dequeue_count and m.dequeue_count > _MAX_DEQUEUE:
                        logging.error("dropping calc job after %s attempts: %s",
                                      m.dequeue_count, m.content[:200])
                    else:
                        await _process(blob, job)
                except Exception:  # noqa: BLE001
                    logging.exception("calc job errored (deleting to avoid poison loop)")
                finally:
                    try:
                        queue.delete_message(m)
                    except Exception:  # noqa: BLE001
                        logging.exception("could not delete calc message")
            if not got:
                await asyncio.sleep(_POLL_IDLE_S)
        except Exception:  # noqa: BLE001
            logging.exception("ca-calc worker loop error")
            await asyncio.sleep(_POLL_IDLE_S)
