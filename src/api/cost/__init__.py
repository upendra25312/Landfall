"""
Deterministic cost engine (PRD epics E2 / E6).

  from cost.rightsize import rightsize_many
  from cost.config import load_config

All numeric work lives here as plain functions so the agent never does arithmetic
in context — it calls a tool, and re-running the tool gives the same answer.
`config.py` loads the firm's `estimation_config.json` over documented defaults.
"""
from .config import load_config, DEFAULTS
from .rightsize import rightsize_one, rightsize_many
from .compute_cost import estimate_compute_cost, HOURS_PER_MONTH
from .storage_cost import estimate_storage_cost, classify
from .run_rate import estimate_run_rate_extras

__all__ = [
    "load_config", "DEFAULTS",
    "rightsize_one", "rightsize_many",
    "estimate_compute_cost", "HOURS_PER_MONTH",
    "estimate_storage_cost", "classify",
    "estimate_run_rate_extras",
]
