"""ca-calc as an event-driven Container Apps **Job** (PRD E13.13).

The KEDA `azure-queue` trigger on `job-calc` starts one execution when a
`calc-jobs` message appears; this entrypoint drains the queue once and exits, so
there is **no always-on replica** (the §21 Definition-of-Done: "no always-on
2-vCPU/4-GiB calculator worker").

    docker … python job.py          # the Job's command override

The same image also runs `app.py` (the FastAPI service) — that path stays for the
always-on Container App variant (`USE_CALC_JOB=false`) and local dev. This module
just calls `worker.run_once()`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)


def main() -> int:
    if not os.environ.get("STORAGE_QUEUE_URL"):
        logging.error("STORAGE_QUEUE_URL unset — nothing to consume")
        return 1
    from worker import run_once

    try:
        processed = asyncio.run(run_once())
    except Exception:  # noqa: BLE001
        logging.exception("ca-calc job failed")
        return 1
    # exit 0 even when the queue was empty by the time we ran (a benign race with
    # KEDA) — a non-zero exit would mark the Job execution Failed and retry it.
    logging.info("ca-calc job done (%s processed)", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
