"""Deterministic synthetic price/rate books for the eval harness (no network)."""
from __future__ import annotations

import csv
import os

from cost.skus import DISK_TIERS, SKUS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "sample-estate")


def price_book() -> dict:
    b: dict = {}
    for rows in SKUS.values():
        for sku, v, _r in rows:
            lin = round(v * 0.05, 4)
            win = round(v * 0.09, 4)
            b[sku] = {
                "linux": {"payg": lin, "ri1y": round(lin * 0.62, 4), "ri3y": round(lin * 0.42, 4)},
                "windows": {"payg": win, "ri1y": round(win * 0.62, 4), "ri3y": round(win * 0.42, 4)},
            }
    return b


def disk_book() -> dict:
    return {t: round(g * 0.11, 2) for t, g, _ in DISK_TIERS}


def storage_rates() -> dict:
    return {
        "files_premium": 0.16, "files_standard_hot": 0.06,
        "anf_standard": 0.15, "anf_premium": 0.29, "anf_ultra": 0.39,
        "db_sql_mi": 0.13, "db_sql_hyperscale": 0.11, "db_flex_postgresql": 0.115,
        "db_flex_mysql": 0.115, "db_oracle": 0.16,
        "blob_hot_lrs": 0.018, "blob_cool_lrs": 0.01, "managed_premium_ssd_v2": 0.08,
    }


def load(name: str) -> list[dict]:
    with open(os.path.join(SAMPLE, name + ".csv"), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))
