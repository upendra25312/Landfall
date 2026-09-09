# Azure Landing Zone — design checklist (vendored design reference)

**Source:** Microsoft Cloud Adoption Framework — Azure landing zone design areas and the
per-service *design checklist* pattern used by the Azure Architecture Center
(<https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/>,
<https://learn.microsoft.com/azure/architecture/landing-zones/>). Distilled and
retrieved **2026-09-09** for use as a fixed ruleset by `src/api/lz/conformance.py`.
This is a *reference*, not a live document — re-vendor when the CAF guidance changes.

`conformance.py` scores each item below against the deterministic output of
`design_landing_zone` (`src/api/lz/design.py`) and reports `met` / `partial` / `gap`
/ `n/a` with evidence and, for anything short of `met`, a recommendation.

## Identity

- **ID-1 — Entra ID for control-plane authentication; no shared account keys.** Azure
  RBAC via Entra ID groups; disable local/shared credentials on management surfaces.
- **ID-2 — Privileged Identity Management (PIM) for just-in-time Azure RBAC.** No
  standing owner/contributor at management-group or subscription scope.
- **ID-3 — Emergency-access ("break-glass") accounts, excluded from Conditional Access
  and monitored.** Bastion / no standing RDP-SSH for admin access.

## Resource organization

- **RO-1 — CAF management-group hierarchy: an intermediate root with `platform` and
  `landing zones` groups (plus `sandbox`, `decommissioned`).**
- **RO-2 — Dedicated platform subscriptions for connectivity, identity and
  management.**
- **RO-3 — Landing-zone subscriptions per workload / archetype, not one shared
  subscription.**

## Networking

- **NET-1 — Hub-and-spoke or Virtual WAN topology with a central connectivity
  subscription.**
- **NET-2 — Central, controlled egress through Azure Firewall or an NVA
  (forced tunnelling where required).**
- **NET-3 — Private DNS zones for Azure PaaS plus a DNS resolver / forwarding
  design.**
- **NET-4 — Planned, non-overlapping IP address space reconciled with on-prem
  IPAM.**
- **NET-5 — Hybrid connectivity (ExpressRoute with VPN backup) sized for the
  migration.**

## Security

- **SEC-1 — Private Endpoints for PaaS data services; public network access denied by
  policy.**
- **SEC-2 — Customer-managed keys (Key Vault / Managed HSM) for regulated data
  stores.**
- **SEC-3 — Regulatory-compliance initiative (PCI DSS, HIPAA HITRUST, FedRAMP, …)
  assigned where a compliance scope exists.**
- **SEC-4 — DDoS Network Protection on virtual networks that host internet-facing
  workloads.**

## Governance

- **GOV-1 — Azure Policy baseline assigned at management-group scope (inherited, not
  per-subscription).**
- **GOV-2 — Guardrail policies for allowed regions, allowed SKUs and required
  tags.**
- **GOV-3 — Regulated workloads isolated by a dedicated management group + policy
  overlay.**

## Management

- **MON-P-1 — Centralized Log Analytics workspace in the management subscription.**
- **MON-P-2 — Azure Monitor diagnostic settings routed to the central workspace by
  policy.**
- **MON-P-3 — Patch / update management strategy (Azure Update Manager) for migrated
  VMs.**

## Monitoring

- **MON-1 — Platform vs. workload monitoring separation (platform team owns the
  baseline).**
- **MON-2 — Alerting baseline with action groups for platform-critical signals.**
- **MON-3 — Service-health and resource-health alerts configured.**

## Reliability

- **REL-1 — Two or more regions for tier-1 / tier-2 workloads (paired region for
  DR).**
- **REL-2 — Availability zones for production workloads that support them.**
- **REL-3 — Documented RPO / RTO per resiliency tier.**
- **REL-4 — Backup with a GRS / geo-redundant vault for tiers that recover from
  backup.**

## Cost

- **COST-1 — Reserved Instances or a savings plan for steady-state compute.**
- **COST-2 — Budgets and cost alerts per landing-zone subscription.**
- **COST-3 — Tagging standard that supports cost allocation / showback.**

## Data

- **DATA-1 — Data residency honoured by the primary-region choice.**
- **DATA-2 — Private connectivity for data-platform services (no public endpoints).**
- **DATA-3 — Backup and retention defined for migrated data stores.**
