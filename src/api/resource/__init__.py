"""
Landfall Resource Demand & Capacity Planning Package (PRD E15.3 / E15C).

Provides:
  - Deterministic role-level resource demand derivation (E15C.4)
  - Demand vs. capacity separation and constraint warnings (E15C.1, E15C.8)
  - Three resource scenarios: Conservative, Expected, Accelerated (E15C.7)
  - Commercial services cost modeling across delivery models (E15C.14)
  - SOW resource narrative & 12-column project plan (E15C.15, E15C.16)
  - 15-sheet openpyxl resource plan workbook generator (E15C.9)
"""
from __future__ import annotations

from resource.capacity import analyze_capacity_and_constraints
from resource.commercial import calculate_commercial_cost
from resource.engine import derive_resource_demand
from resource.model import (
    ROLES_BY_ID,
    ROLES_BY_TITLE,
    STANDARD_ROLES,
    DeliveryModel,
    PlanningMode,
    ResourceRequirementRow,
    RoleDefinition,
)
from resource.scenarios import generate_resource_scenarios
from resource.sow_project_plan import build_project_plan, build_sow_resource_section
from resource.workbook import generate_resource_workbook

__all__ = [
    "DeliveryModel",
    "PlanningMode",
    "ResourceRequirementRow",
    "RoleDefinition",
    "ROLES_BY_ID",
    "ROLES_BY_TITLE",
    "STANDARD_ROLES",
    "analyze_capacity_and_constraints",
    "build_project_plan",
    "build_sow_resource_section",
    "calculate_commercial_cost",
    "derive_resource_demand",
    "generate_resource_scenarios",
    "generate_resource_workbook",
]
