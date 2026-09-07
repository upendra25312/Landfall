"""
Load the firm's estimation config over documented defaults (PRD E6.1).

Resolution order for the file:
  1. explicit path passed to load_config()
  2. $ESTIMATION_CONFIG
  3. estimation_config.json next to the repo root (dev / local)
Anything the file omits falls back to DEFAULTS below, so a partial file is fine.
"""
from __future__ import annotations

import copy
import json
import os

DEFAULTS: dict = {
    "pricing": {
        "region": "swedencentral",
        "currency": "USD",
        "reserved_term": "1yr",                 # none | 1yr | 3yr
        "reservation_coverage_pct": 80,
        "azure_hybrid_benefit_windows": True,
        "azure_hybrid_benefit_sql": True,
        "dev_test_pricing_nonprod": False,
    },
    "rightsize": {
        "utilisation_metric": "p95",            # p95 | peak | avg
        "cpu_target_utilisation_pct": 65,
        "ram_target_utilisation_pct": 80,
        "min_vcpu_retain_pct": 50,              # never cut below this fraction of current
        "min_ram_retain_pct": 60,
        "vcpu_floor": 2,
        "ram_floor_gb": 4,
        "headroom_band_pct": 20,                # +/- for the low/high range
        "no_perf_data": {
            "cpu_scale_pct": 100,               # 100 = keep as-is (no blind haircut)
            "ram_scale_pct": 100,
            "confidence": "low",
        },
    },
    "uplift": {
        "nonprod_compute_pct": 0,
        "dr_compute_pct": 100,
    },
    "effort": {
        "bands_pd": {"S": 8, "M": 14, "L": 22, "XL": 40},
        "assessment_pd_per_server": 0.15,
        "assessment_pd_per_app": 1.5,
        "rehost_pd_per_server": 0.5,
        "pm_pct": 15,
        "governance_pct": 10,
        "contingency_pct": None,                # None => derive from the data-quality score
    },
    "rates": {
        "blended_day_rate": 780,
        "currency": "USD",
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if k.startswith("$"):
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _repo_config() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for up in range(5):
        cand = os.path.join(here, *([".."] * up), "estimation_config.json")
        if os.path.exists(cand):
            return cand
    return None


def load_config(path: str | None = None, overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    p = path or os.environ.get("ESTIMATION_CONFIG") or _repo_config()
    if p and os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                _deep_merge(cfg, json.load(fh))
            cfg["_source"] = p
        except (OSError, json.JSONDecodeError) as exc:
            cfg["_source"] = f"defaults (could not read {p}: {exc})"
    else:
        cfg["_source"] = "defaults (no estimation_config.json found)"
    if overrides:
        _deep_merge(cfg, overrides)
    return cfg
