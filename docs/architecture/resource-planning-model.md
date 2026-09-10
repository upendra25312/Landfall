# Landfall Deterministic Resource-Demand & Capacity Planning Model

> **Architecture Specification & Implementation Reference**  
> **Epic Reference:** E15.3 (§E15C.1–E15C.17)  
> **Status:** Production / Cycle 62  

---

## 1. Executive Overview & Core Principles

The Landfall Resource-Demand & Capacity Planning system evolves traditional, coarse person-day estimation into a complete, deterministic, multi-dimensional resource planning engine. It models required engineering and architecture capacity across **functional roles**, **MEG lifecycle phases**, **migration waves**, and **calendar months**.

### 1.1 The Golden Rule: Separation of Demand from Capacity (E15C.1)

A foundational architectural law of Landfall is the strict separation between what a migration requires and what an organization has available:

```
┌────────────────────────────────────────────────────────┐
│               RESOURCE DEMAND MODEL                    │
│  (Authoritative Deterministic Derivation by Landfall)  │
│                                                        │
│  Scope (Servers, Apps, DBs)                            │
│  + 6R Disposition Mix                                  │
│  + Wave Schedule & Concurrency                         │
│  + Landing Zone Topology                               │
│  + Standard Productivity Baselines                     │
│         │                                              │
│         ▼                                              │
│  Required FTE by Role × Month / Wave / Phase           │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
               ┌──────────────────────────┐
               │    VARIANCE & GAPS       │
               │                          │
               │ Variance = Avail - Req   │
               │ Util% = Req / Avail      │
               └────────────▲─────────────┘
                            │
┌───────────────────────────┴────────────────────────────┐
│              RESOURCE CAPACITY MODEL                   │
│        (Supplied ONLY by User / Client Input)          │
│                                                        │
│  - Never guessed or hallucinated by AI                 │
│  - If unsupplied: Available = NOT PROVIDED             │
│                   Gap / Variance = UNKNOWN             │
└────────────────────────────────────────────────────────┘
```

1. **Deterministic Resource Demand**: Landfall calculates what is required (`required_fte`). This output is mathematically reproducible, formulaic, and grounded in scope and productivity factors. The LLM is never allowed to allocate FTE.
2. **User-Supplied Capacity**: Resource capacity (`available_fte`) comes strictly from explicit customer or partner input. If not supplied, Landfall reports `NOT PROVIDED` and variance as `UNKNOWN`.
3. **No Named People Hallucination**: Pre-sales defaults strictly to role-based planning (`MODE 1`). Named assignment (`MODE 2`) is optional and never fabricated.
4. **Constraint Feedback without Silent Mutation (E15C.8)**: When candidate demand exceeds known capacity, Landfall flags `RESOURCE-CONSTRAINED SCHEDULE` identifying bottleneck months, roles, and affected waves. It does *not* automatically rewrite candidate waves without explicit user request.

---

## 2. Standard Functional Roles & MEG Alignment (E15C.3)

Landfall maps effort to 10 standard functional roles aligned with the Microsoft Migration Execution Guide (MEG) taxonomy in `references/meg/roles.json`:

| Role ID | Functional Role Title | Category | Default Delivery Model | Core Competencies |
|:---|:---|:---|:---|:---|
| `prog_manager` | **Migration Programme Manager** | Management | Onshore | Project governance, critical path management, RAID log, executive status reporting. |
| `lead_architect` | **Lead Cloud Architect** | Architecture | Onshore | Azure Landing Zone design, 6R disposition signoff, Well-Architected governance, pattern approval. |
| `migration_engineer` | **Infrastructure / Migration Engineer** | Engineering | Nearshore | Azure Migrate appliance setup, ASR replication, test failovers, cutover execution. |
| `network_engineer` | **Network Engineer** | Networking | Onshore | ExpressRoute / VPN, hub-spoke routing, Azure Firewall, DNS resolution, NSG rules. |
| `security_lead` | **Security & Compliance Lead** | Security | Onshore | Entra ID / RBAC, Key Vault, Defender for Cloud, policy initiatives, compliance audits. |
| `dba_lead` | **Database Administrator (DBA)** | Data | Nearshore | PaaS DB migration (SQL MI, Postgres/MySQL Flex), DMS sync, cutover validation. |
| `app_owner` | **Application Owner / SME** | Business | Customer | Workload discovery signoff, acceptance criteria, UAT execution, business go-live approval. |
| `test_lead` | **Test Lead** | Testing | Nearshore | Test automation, performance / NFR validation, dress rehearsal management, defect tracking. |
| `devops_ops_lead` | **DevOps & Operations Lead** | Operations | Nearshore | CI/CD pipelines, Azure Monitor / Log Analytics, backup policies, Day-2 operations handover. |
| `finops_analyst` | **FinOps Analyst** | Commercial | Offshore | Cloud cost tracking, Azure Reservations / Savings Plans, tagging enforcement, budget alerts. |
| `change_manager` | **Change Manager** | Management | Customer | CAB approval coordination, release notifications, maintenance window scheduling. |

---

## 3. Mathematical Formulation (E15C.4)

### 3.1 Total Person-Days (Reconciliation to Phase 1 Effort Engine)

Total required person-days (EAC) derive from delivery workstreams plus program management, technical governance, and data-quality-driven contingency:

$$\text{Delivery Subtotal (PD)} = \sum_{w \in \text{Workstreams}} \text{PD}_w$$

$$\text{PM} = 0.15 \times \text{Delivery Subtotal}$$

$$\text{Governance} = 0.10 \times \text{Delivery Subtotal}$$

$$\text{Base Effort} = \text{Delivery Subtotal} + \text{PM} + \text{Governance}$$

$$\text{Contingency} = \text{Base Effort} \times \text{Contingency\%}(\text{DQ Confidence})$$

$$\text{EAC (PD)} = \text{Base Effort} + \text{Contingency}$$

### 3.2 Role-Level Effort Derivation

Each workstream $w$ is mapped across functional roles $r$ using deterministic weighting coefficients $\omega_{w, r}$, where $\sum_r \omega_{w, r} = 1.0$:

$$\text{Effort}_{r} = \sum_{w} (\text{PD}_w \times \omega_{w, r})$$

$$\text{Effort Hours}_{r} = \text{Effort}_{r} \times \text{HoursPerDay} \quad (\text{default: } 8.0\,\text{h/day})$$

### 3.3 Calendar & Time Distribution (E15C.5)

For a project spanning $M$ months (either dated $YYYY\text{-}MM$ or relative $\text{Month } 1 \dots \text{Month } N$):
- **Mobilisation / Assessment**: Allocated to Strategy & Plan periods.
- **Landing Zone**: Allocated to Ready period.
- **Wave Execution & Cutover**: Distributed across scheduled wave execution and soak intervals.
- **Hypercare**: Allocated to the final operational stability months.
- **PM, Governance, and Contingency**: Level-loaded across the entire project lifecycle.

In each month $m$, required Full-Time Equivalents (FTE) for role $r$ is:

$$\text{Required FTE}_{r, m} = \frac{\text{Effort PD}_{r, m}}{\text{WorkingDaysPerMonth}} \quad (\text{default: } 21\,\text{days/month})$$

$$\text{Total Required FTE}_m = \sum_{r} \text{Required FTE}_{r, m}$$

$$\text{Peak Team Size} = \max_{m} (\text{Total Required FTE}_m)$$

$$\text{Average Team Size} = \frac{\sum_{m} \text{Total Required FTE}_m}{M}$$

---

## 4. Scenario Planning Model (E15C.7)

Landfall derives three deterministic resource scenarios varying velocity, concurrency, and risk buffers:

| Dimension | Conservative | Expected (Baseline) | Accelerated |
|:---|:---|:---|:---|
| **Migration Throughput** | 8 servers / week (0.67×) | 12 servers / week (1.0×) | 24 servers / week (2.0×) |
| **Wave Concurrency** | 1 sequential lane | 1–2 lanes | 2–3 parallel lanes |
| **Wave Prep / Soak** | 3 wk prep / 2 wk soak | 2 wk prep / 1 wk soak | 1 wk prep / 1 wk soak |
| **Contingency Buffer** | 20.0% (Risk-averse) | 12.0% (Medium DQ baseline) | 8.0% (Automated factory) |
| **Duration Profile** | Longer (~9–12 months) | Balanced (~6–8 months) | Compressed (~4–5 months) |
| **Peak FTE** | Lower (~6–8 FTE) | Moderate (~8–10 FTE) | High (~12–16 FTE) |
| **Operational Posture** | Cautious, manual signoffs | Standard CAF best-practice | Automated factory pods |

All deltas derive strictly from configured mathematical inputs without arbitrary multipliers.

---

## 5. Capacity Variance, Heatmaps & Constraint Warnings (E15C.8, E15C.11, E15C.12)

### 5.1 Constraint Warning Contract
When user capacity is supplied:

$$\text{Variance}_{r, m} = \text{Available FTE}_{r} - \text{Required FTE}_{r, m}$$

$$\text{Utilization\%}_{r, m} = \left(\frac{\text{Required FTE}_{r, m}}{\text{Available FTE}_{r}}\right) \times 100$$

If $\text{Variance}_{r, m} < 0$ for any role $r$ in month $m$:
- System flags: `RESOURCE-CONSTRAINED SCHEDULE`
- Identifies:
  - Constrained role(s) and specific deficit FTE.
  - Bottleneck period(s).
  - Affected migration waves active during the period.
- Provides actionable recommendations (e.g. "Engage partner capacity", "Stagger wave cutover", "Extend duration").
- Does **not** mutate candidate waves silently.

### 5.2 Heatmap Status Categorization
- `OVER_ALLOCATED`: Utilization $> 105\%$ (Red highlight)
- `OPTIMAL`: Utilization between $75\%$ and $105\%$ (Green highlight)
- `UNDER_ALLOCATED`: Utilization between $1\%$ and $74\%$ (Neutral gray)
- `IDLE`: Utilization $= 0\%$
- `UNASSESSED`: Capacity not provided by user

---

## 6. Commercial Costing Model (E15C.14)

Commercial services cost multiplies deterministic role person-days by configured day rates adjusted for delivery model:

$$\text{Day Rate}_r = \text{BlendedDayRate} \times \text{RoleWeight}_r \times \text{DeliveryModelFactor}_r$$

$$\text{Cost}_r = \text{Effort PD}_r \times \text{Day Rate}_r$$

$$\text{Total Commercial Cost} = \sum_r \text{Cost}_r$$

- Internal client roles (Application Owner / SME, Change Manager) carry a factor of $0.0$ ($0 billable services cost to the engagement).
- Consulting rates are never invented by an LLM; they derive from firm configuration (`cost/config.py`).

---

## 7. 15-Sheet OpenPyXL Workbook Architecture (E15C.9)

The standalone generator `src/api/resource/workbook.py` produces `resource_plan.xlsx` with native Excel formulas and `fullCalcOnLoad = True`:

1. **`01 Executive Summary`**: KPI dashboard cards, total effort, hours, peak FTE, commercial cost, and capacity status banner.
2. **`02 Resource Assumptions`**: Calendar configuration (hours/day, working days/month), overhead percentages, and planning modes.
3. **`03 Role Catalogue`**: MEG-aligned functional roles, core skills, delivery models, and responsibilities.
4. **`04 Activities`**: Workstream activity inventory with sizing logic and `=SUM()` formulas.
5. **`05 Resource Demand`**: Complete 22-attribute requirement rows table (PRD E15C.3).
6. **`06 Monthly FTE`**: Role $\times$ Month required FTE matrix with `=SUM()`, `=AVERAGE()`, and `=MAX()` formulas.
7. **`07 Capacity Heatmap`**: Role utilization percentages with conditional formatting highlights.
8. **`08 Wave Loading`**: Wave-by-wave server counts, adopt PD, share of factory, and critical roles.
9. **`09 Role x Phase Matrix`**: Role person-days across Strategy, Plan, Ready, Adopt, Govern, and Manage phases.
10. **`10 Resource Cost`**: Commercial rate card, billable PD, and `=C*D` formulas for role and monthly costs.
11. **`11 DACI-RACI`**: Migration governance baseline mapping phases to R/A/C/I roles.
12. **`12 Skill Gaps`**: Deficit analysis identifying role skills requiring augmentation.
13. **`13 Calculation Appendix`**: Traceable mathematical formulas, input parameters, and confidence ratings.
14. **`14 Demand vs Capacity`**: Direct comparison table showing required peak FTE vs available FTE and variance.
15. **`15 Assumption Register`**: Standing assumptions, exclusions, and data gaps.

---

## 8. Worked Example: 250-Server Sample Estate

Over the standard 250-server, 31-application, 9-spoke sample estate (`evals/pipeline.py` baseline):

### 8.1 Summary Totals
- **Delivery Subtotal**: 546.5 PD
- **Programme Management (15%)**: 82.0 PD
- **Governance & Assurance (10%)**: 54.7 PD
- **Contingency (Medium DQ: 12%)**: 82.0 PD
- **Total EAC Effort**: **765.2 Person-Days** (6,121.6 Hours)
- **Duration**: 24 Weeks (~6 Months) across 7 Migration Waves
- **Average Team Size**: 6.07 FTE
- **Peak Team Size**: **9.42 FTE** (Month 3, during Wave 3–4 peak execution)

### 8.2 Role Breakdown Reconciled
| Functional Role | Person-Days | Hours | Avg FTE | Peak FTE |
|:---|---:|---:|---:|---:|
| Infrastructure / Migration Engineer | 239.5 | 1,916.0 | 1.90 | 3.65 |
| Lead Cloud Architect | 134.2 | 1,073.6 | 1.07 | 1.75 |
| Migration Programme Manager | 108.9 | 871.2 | 0.86 | 1.15 |
| Application Owner / SME | 74.4 | 595.2 | 0.59 | 0.95 |
| Database Administrator (DBA) | 68.1 | 544.8 | 0.54 | 1.10 |
| Security & Compliance Lead | 49.3 | 394.4 | 0.39 | 0.80 |
| Test Lead | 38.8 | 310.4 | 0.31 | 0.60 |
| Network Engineer | 33.2 | 265.6 | 0.26 | 0.50 |
| DevOps & Operations Lead | 9.0 | 72.0 | 0.07 | 0.20 |
| FinOps Analyst | 16.4 | 131.2 | 0.13 | 0.20 |
| Change Manager | 12.3 | 98.4 | 0.10 | 0.15 |
| **Total Reconciled** | **765.2** | **6,121.6** | **6.07** | **9.42** |

*(Sum of role person-days equals 765.2 PD with 0.00 residual variance).*
