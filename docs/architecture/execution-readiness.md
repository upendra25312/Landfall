# Migration Execution-Readiness Experience & Governance Architecture

> **Architecture Specification & Implementation Reference**  
> **Epic Reference:** E15.4 (§E15D.1–E15D.8)  
> **Status:** Production / Cycle 63  

---

## 1. Executive Summary

Epic **E15.4** transitions Landfall from an offline calculation estimator into a complete, interactive **Migration Execution-Readiness Experience**. It organizes migration assessments into **15 assessment-first areas**, integrates the **Microsoft Migration Execution Guide (MEG)** 5-state readiness evaluation model with interactive drill-downs, streamlines the Foundry prompt cards, introduces a deterministic **6-part recommendation explanation format**, and locks the boundary between immutable **Assessment Baselines** and live Microsoft research.

---

## 2. The 15 Assessment-First Dashboard Areas (E15D.1)

Rather than an arbitrary chat transcript or generic search UI, Landfall presents assessment findings across 15 structured, interconnected areas:

| Area ID | Area Title | Core Content & Machine Outputs | Primary MEG Phase |
|:---|:---|:---|:---|
| `01` | **Overview** | Executive KPI tiles (Servers, Apps, Monthly/Annual Run-rate, EAC PD, Services Cost). | Strategy |
| `02` | **Data & Discovery** | Inventory data quality score, null rates, orphan disks, discovery catalog gaps. | Plan |
| `03` | **Current Estate** | Environment distribution (Prod, NonProd, Dev, DR), OS EOL breakdown, compute/storage totals. | Plan |
| `04` | **Target Architecture** | Azure Landing Zone topology, hub-spoke peering, management groups, inline Draw.io diagram. | Ready |
| `05` | **Cost & POE** | Azure run-rate breakdown, top-3 cost drivers, reserved instances, Pricing Calculator POE (`landing_zone.xlsx`). | Plan / Ready |
| `06` | **Strategy (6R)** | Deterministic 6R application disposition mix (Rehost, Replatform, Repurchase, Retire, Retain, Refactor). | Plan |
| `07` | **Waves** | Risk-ordered move group packing, pilot waves, regulated cutover windows, wave risk scores. | Plan |
| `08` | **Timeline** | Migration schedule, throughput (servers/week), parallel execution lanes, ordered critical path. | Plan |
| `09` | **Resource Plan** | Role-level demand (10 MEG roles), EAC person-days, hours, peak/average FTE, monthly FTE curve. | Ready |
| `10` | **Capacity** | User-supplied capacity variance, capacity heatmap, and `RESOURCE-CONSTRAINED SCHEDULE` warnings. | Ready |
| `11` | **Readiness** | Interactive 5-state MEG readiness checklist (21 criteria) with evidence-backed drill-downs. | Ready / Adopt |
| `12` | **Risks** | Deterministic MEG risk register (unmonitored servers, single-region posture, DB replatforming). | Govern |
| `13` | **Deliverables** | Centralized artifact download hub (`.xlsx`, `.docx`, `.pptx`, `.drawio`, `resource_plan.xlsx`). | All |
| `14` | **MS Guidance** | Pinned MEG reference commit/hash, Microsoft Learn citations, and Baseline vs. Research flags. | Strategy / Govern |
| `15` | **Evidence** | Signed data-handling statement, machine assumptions register, traceable calculation appendix. | Govern / Manage |

---

## 3. Interactive Migration Readiness Dashboard (E15D.2)

Landfall evaluates estate readiness across 21 criteria in 15 categories, reporting strictly within the **5-state readiness model**:

$$\text{State} \in \{\text{READY}, \text{PARTIAL}, \text{GAP}, \text{NOT\_ASSESSED}, \text{NOT\_APPLICABLE}\}$$

Arbitrary maturity percentages (e.g. "68% ready") are prohibited.

### 3.1 Four-Part Drill-Down Contract
Clicking any readiness row in the dashboard reveals its underlying operational drawer:

```
┌──────────────────────────────────────────────────────────────┐
│ Category: Landing Zone Core                                  │
│ Criterion: Hybrid Connectivity & Spoke Routing               │
│ Status: PARTIAL                                              │
├──────────────────────────────────────────────────────────────┤
│ Evidence:                                                    │
│   Hub-spoke network topology with 9 spokes and 10.100.0.0/14 │
│   supernet designed. ExpressRoute gateway SKU specified.    │
│                                                              │
│ Missing Decision:                                            │
│   Customer network team must confirm on-premises ASN and     │
│   primary peering circuit ID.                                │
│                                                              │
│ Responsible Role:                                            │
│   Network Engineer                                           │
│                                                              │
│ Recommended Action:                                          │
│   Submit ExpressRoute circuit reservation request to telco   │
│   provider before Wave 1 prep kickoff.                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Prompt Card Simplification (E15D.3)

To prevent cognitive fatigue on the initial engagement screen, the chat interface displays **6 primary strategic prompt cards**:

1. `Full assessment`: Runs end-to-end deterministic assessment pipeline and publishes to dashboard.
2. `Azure architecture`: Designs the CAF Landing Zone, spokes, connectivity, identity, and security overlay.
3. `Cost & POE`: Right-sizes VMs, computes PAYG/RI/AHB pricing, and drives the Pricing Calculator POE.
4. `Migration plan`: Scores 6R dispositions, packs affinity move-groups, and establishes the critical path.
5. `Resource plan`: Derives role demand by month, checks capacity variance, and generates `resource_plan.xlsx`.
6. `Ask Microsoft`: Dispatches queries to Microsoft Learn MCP with confidentiality scrubbing and provenance.

---

## 5. "Explain this recommendation" 6-Part Anatomy (E15D.4)

When an architect or client asks *"Why did you recommend this?"*, Landfall returns a structured 6-part justification:

```
1. Recommendation:
   Azure Firewall Premium with Outbound TLS Inspection and IDPS

2. Customer Driver:
   PCI-DSS and HIPAA regulatory scopes present in estate inventory; internet-facing spoke egress.

3. Landfall Deterministic Rule:
   Regulated compliance flag triggers dedicated Confidential spoke with Layer-7 deep packet inspection.

4. Microsoft Guidance:
   Microsoft Cloud Security Benchmark (MCSB v1.0) & CAF Landing Zone Secure Hub-Spoke Baseline.

5. Confidence:
   High

6. Assumptions / Gaps:
   Customer enterprise PKI must supply an intermediate CA certificate in Azure Key Vault for TLS termination.
```

---

## 6. Assessment Baseline vs. Live Microsoft Research (E15D.5)

To maintain absolute reproducibility, Landfall enforces a strict boundary:

- **ASSESSMENT BASELINE**: Pinned, immutable assessment record (`latest.json`) calculated using pinned configuration, retail price dates, engine version, and MEG commit `09b2693`.
- **LIVE MICROSOFT RESEARCH**: Dynamic lookups against Microsoft Learn MCP for current documentation, release updates, or troubleshooting.

If live research indicates potential divergence (e.g. SKU deprecation, new VM series release), Landfall **flags the difference** as `ASSESSMENT BASELINE vs LIVE MICROSOFT RESEARCH`. The completed assessment is **never silently mutated**. Re-running requires an explicit operator request.

---

## 7. Provenance Metadata Contract (E15D.6)

Every deliverable artifact and dashboard view embeds the authoritative provenance block:
- **Engine Version**: `2.4.0`
- **Assessment Date**: ISO-8601 execution timestamp
- **Price Date**: Pinned Azure retail pricing date
- **MEG Reference Commit**: `09b269375dc7c48cee7541e4ca16faf02b3897ca`
- **MEG Artifact SHA-256**: `4b726f1c79e64e578ad2eb463690d563914e6e66e84d4da5898864f131a99ef8`
- **Resource Model Version**: `1.0.0`
- **Configuration Source**: `estimation_config.json`
