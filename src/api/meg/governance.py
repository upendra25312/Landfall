"""Governance and RACI/DACI Matrix Generator (Epic E15.2 / E15B.8).

Generates a suggested governance baseline using standardized functional roles
from the Microsoft Azure Migration Execution Guide (MEG).

Rule: Never invents people's names; all mappings are functional roles and explicitly
marked 'DRAFT — CUSTOMER VALIDATION REQUIRED'.
"""
from __future__ import annotations

from typing import Any

from .loader import load_roles


def build_governance_matrix(
    methodology: str = "RACI",
) -> dict[str, Any]:
    """Generate a baseline RACI or DACI governance matrix for an engagement.

    Args:
        methodology: "RACI" or "DACI".

    Returns:
        Structured governance dictionary containing roles, matrix mappings, and required notices.
    """
    roles_def = load_roles()
    roles = roles_def.get("standard_roles", [])
    raci_map = roles_def.get("default_raci", {})
    daci_map = roles_def.get("default_daci", {})

    roles_by_id = {r["id"]: r["title"] for r in roles}

    if methodology.upper() == "DACI":
        return {
            "notice": "DRAFT — CUSTOMER VALIDATION REQUIRED",
            "methodology": "DACI",
            "roles": roles,
            "matrix": daci_map,
            "description": "Driver, Approver, Contributor, Informed decision framework for migration governance.",
        }

    # Default to RACI
    # Expand role IDs to human-readable role titles in RACI matrix
    expanded_raci: dict[str, dict[str, str]] = {}
    for phase, assignments in raci_map.items():
        phase_readable = phase.replace("_", " ").title()
        expanded_raci[phase_readable] = {
            roles_by_id.get(rid, rid): code
            for rid, code in assignments.items()
        }

    return {
        "notice": "DRAFT — CUSTOMER VALIDATION REQUIRED",
        "methodology": "RACI",
        "roles": roles,
        "matrix": expanded_raci,
        "legend": {
            "R": "Responsible (Does the work to complete the task)",
            "A": "Accountable (Sole decision maker / ultimate ownership)",
            "C": "Consulted (Provides two-way input and SME domain guidance)",
            "I": "Informed (Kept updated on progress and outcomes)",
        },
    }
