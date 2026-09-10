"""
Resource Demand & Capacity Data Models (PRD E15C.1, E15C.2, E15C.3, E15C.6).

Defines:
  - Planning modes (MODE 1: Role-Based, MODE 2: Named Resource)
  - Delivery models and locations (Customer, Onshore, Nearshore, Offshore, Partner, Microsoft)
  - Standard functional roles and core skills catalogue aligned with MEG
  - Requirement row dataclass and dictionary schemas
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PlanningMode(str, Enum):
    ROLE_BASED = "MODE 1 — Role-Based Resource Planning"
    NAMED_RESOURCE = "MODE 2 — Named Resource Allocation"


class DeliveryModel(str, Enum):
    CUSTOMER = "Customer"
    ONSHORE = "Onshore"
    NEARSHORE = "Nearshore"
    OFFSHORE = "Offshore"
    PARTNER = "Partner"
    MICROSOFT = "Microsoft"


@dataclass(frozen=True)
class RoleDefinition:
    id: str
    title: str
    category: str
    skills: list[str]
    default_delivery_model: DeliveryModel = DeliveryModel.ONSHORE
    description: str = ""


# 10 standard functional roles aligned with MEG (references/meg/roles.json)
STANDARD_ROLES: list[RoleDefinition] = [
    RoleDefinition(
        id="prog_manager",
        title="Migration Programme Manager",
        category="management",
        skills=["Project Governance", "Critical Path Management", "Stakeholder Communications", "Risk Management"],
        default_delivery_model=DeliveryModel.ONSHORE,
        description="Drives project execution, timeline, critical path, cross-functional coordination, and executive status reporting."
    ),
    RoleDefinition(
        id="lead_architect",
        title="Lead Cloud Architect",
        category="architecture",
        skills=["Azure Landing Zone Design", "6R Disposition", "Technical Governance", "CAF / Well-Architected"],
        default_delivery_model=DeliveryModel.ONSHORE,
        description="Owns target Azure Landing Zone design, 6R disposition decisions, architectural patterns, and technical governance."
    ),
    RoleDefinition(
        id="migration_engineer",
        title="Infrastructure / Migration Engineer",
        category="engineering",
        skills=["Azure Migrate", "Azure Site Recovery (ASR)", "OS Remediation", "Replication & Cutover Execution"],
        default_delivery_model=DeliveryModel.NEARSHORE,
        description="Performs server replication setup, test failovers, cutover execution, and post-migration infrastructure validation."
    ),
    RoleDefinition(
        id="network_engineer",
        title="Network Engineer",
        category="networking",
        skills=["ExpressRoute / VPN", "Hub-Spoke Routing", "Azure Firewall", "DNS & IP Allocation", "NSGs"],
        default_delivery_model=DeliveryModel.ONSHORE,
        description="Manages hybrid connectivity, ExpressRoute/VPN, hub-spoke routing, IP allocation, DNS resolution, and firewall rules."
    ),
    RoleDefinition(
        id="security_lead",
        title="Security & Compliance Lead",
        category="security",
        skills=["Entra ID / RBAC", "Key Vault", "Defender for Cloud", "Compliance Controls (PCI/HIPAA)", "Policy"],
        default_delivery_model=DeliveryModel.ONSHORE,
        description="Validates identity, RBAC, encryption, Key Vault access, security policies, and regulatory compliance per spoke."
    ),
    RoleDefinition(
        id="dba_lead",
        title="Database Administrator (DBA)",
        category="data",
        skills=["Azure SQL MI", "PostgreSQL / MySQL Flexible Server", "Azure Database Migration Service (DMS)", "Data Sync"],
        default_delivery_model=DeliveryModel.NEARSHORE,
        description="Oversees database replatforming, schema conversion, replication sync, backup verification, and cutover integrity."
    ),
    RoleDefinition(
        id="app_owner",
        title="Application Owner / SME",
        category="business",
        skills=["Application Architecture", "Integration Testing", "User Acceptance Testing (UAT)", "Business Signoff"],
        default_delivery_model=DeliveryModel.CUSTOMER,
        description="Signs off on application disposition, acceptance testing criteria, maintenance windows, and business cutover."
    ),
    RoleDefinition(
        id="test_lead",
        title="Test Lead",
        category="testing",
        skills=["Test Automation", "Functional Testing", "NFR & Performance Testing", "UAT Coordination"],
        default_delivery_model=DeliveryModel.NEARSHORE,
        description="Directs functional testing, performance/NFR validation, dress rehearsals, and cutover testing gates."
    ),
    RoleDefinition(
        id="devops_ops_lead",
        title="DevOps & Operations Lead",
        category="operations",
        skills=["CI/CD Pipelines", "Azure Monitor / Log Analytics", "Backup & Disaster Recovery", "Runbook Automation"],
        default_delivery_model=DeliveryModel.NEARSHORE,
        description="Integrates CI/CD pipelines, Log Analytics, alerting, backup policies, runbooks, and Day-2 operational handover."
    ),
    RoleDefinition(
        id="finops_analyst",
        title="FinOps Analyst",
        category="commercial",
        skills=["Cost Management", "Reservations & Savings Plans", "Tagging Governance", "Budget Alerts"],
        default_delivery_model=DeliveryModel.OFFSHORE,
        description="Manages cloud cost visibility, Azure Reservations/AHB optimization, tagging compliance, and financial tracking."
    ),
    RoleDefinition(
        id="change_manager",
        title="Change Manager",
        category="management",
        skills=["Change Advisory Board (CAB)", "Release Communications", "Business Readiness", "Incident Playbooks"],
        default_delivery_model=DeliveryModel.CUSTOMER,
        description="Coordinates CAB approvals, stakeholder release comms, downtime scheduling, and change enablement."
    ),
]

ROLES_BY_ID: dict[str, RoleDefinition] = {r.id: r for r in STANDARD_ROLES}
ROLES_BY_TITLE: dict[str, RoleDefinition] = {r.title: r for r in STANDARD_ROLES}


@dataclass
class ResourceRequirementRow:
    """
    Structured resource demand row (PRD E15C.3).
    Authoritative representation of required effort by role, phase, wave, and period.
    """
    engagement: str
    workstream: str
    phase: str
    wave: str
    activity: str
    role: str
    skill: str
    delivery_location: str
    delivery_model: str
    start_date: str
    end_date: str
    effort_hours: float
    working_days: float
    hours_per_day: float = 8.0
    required_fte: float = 0.0
    available_fte: float | None = None
    utilization_pct: float | None = None
    rate: float | None = None
    cost: float | None = None
    dependency: str = ""
    notes: str = ""
    confidence: str = "Medium"
    source: str = "Landfall Deterministic Engine"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
