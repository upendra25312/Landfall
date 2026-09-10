"""Microsoft Migration Execution Guide (MEG) integration package (Epic E15.2)."""
from .loader import (
    load_all_meg,
    load_checklist,
    load_lifecycle,
    load_metadata,
    load_risks,
    load_roles,
    load_wave_guidance,
)
from .readiness import evaluate_readiness
from .risks import generate_risk_register
from .governance import build_governance_matrix

__all__ = [
    "load_all_meg",
    "load_checklist",
    "load_lifecycle",
    "load_metadata",
    "load_risks",
    "load_roles",
    "load_wave_guidance",
    "evaluate_readiness",
    "generate_risk_register",
    "build_governance_matrix",
]
