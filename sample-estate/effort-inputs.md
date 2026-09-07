# Effort & Resource Loading — Inputs and Roll-up for the Sample Estate

Populates the parametric model in `docs/effort-and-resource-loading.html` with the
**actuals** from `sample-estate/` (250 servers, 31 applications) and the client answers in
`discovery-answers.md`. Same unit rates as the model; only the reference-estate counts
change. **Synthetic — for demos and testing the Landfall agent.**

Client: Meridian Retail Group (MRG). Driver: Ashburn data-centre lease exit by 2027-08-31.

---

## 3 · Reference estate — actuals

| | Model placeholder | **This estate** |
|---|---|---|
| Servers / VMs | 150 | **250** (150 Windows, 100 Linux; all VMware vSphere 7.0) |
| Applications | 45 | **31** (30 business + 1 infrastructure-services bucket) |
| Migration waves | 6 | **7** (~4–6 apps / ~35 servers each; affinity-grouped, low-risk first) |
| App landing zones (spokes) | 12 | **11** (Retail/Ecommerce, Finance/ERP, Corporate/HR, Data/Analytics, Integration/API, Customer-web, **PCI-regulated spoke**, Identity, Shared-infra, File-services, Dev/test) |
| Distinct architecture patterns | 6 | **6** (3-tier IaaS · single-VM IaaS · IaaS + PaaS-DB · AKS · regulated 3-tier · file-services/ANF) |

| Dimension | Value |
|---|---|
| Environments | prod 173 · non-prod 47 · dev 27 · DR 3 |
| Compute footprint | 1,940 vCPU · ~10.3 TB RAM (median prod CPU avg ~12%, heavily over-provisioned) |
| Storage | ~186 TB provisioned block / ~106 TB used · ~38 TB file (5 shares) · ~11 TB DB |
| OS past end-of-support | **84 VMs** (32× WS 2012 R2, 24× RHEL 7.9, 17× Ubuntu 20.04, 11× Ubuntu 18.04) — rehost as-is, then ESU/upgrade |
| No performance history | **66 VMs (26%)** — conservative right-sizing, flagged low-confidence |
| Databases | 39 across SQL Server 2016/2019, Oracle 19c, PostgreSQL 13, MySQL 5.7, MongoDB 4.4 |
| Compliance scope | **PCI-DSS (4 apps), SOX (7), GDPR (4), HIPAA (1)** — regulated spoke + controls required |
| Connectivity | ExpressRoute 1 Gbps + backup VPN, single hub, Sweden Central; DR West Europe (AZ + region pair) |
| Delivery window | ~6 months mobilisation → end of hypercare (Ashburn runway to 2027-08 gives float) |

### Disposition mix (31 apps)

| Disposition | Count | Apps |
|---|---|---|
| **Rehost** | 22 | most business apps + the infrastructure-services bucket (AD/DNS/file/backup/monitoring VMs rehost in place) |
| **Replatform** | 6 | 3 Small (Marketing Automation, Inventory Forecasting, Facilities/IoT Gateway → PostgreSQL/MySQL Flexible Server), 2 Medium (Procurement Portal → SQL MI, Field Service backend), 1 Large (Partner API Platform → AKS + Flexible Server) |
| **Repurchase** | 1 | Learning Management → SaaS LMS (rehosted for interim, then cut over) |
| **Retire** | 2 | Print & Output Management, Analytics Sandbox |
| **Retain** | 0 | (existing Azure dev/test subscription documented as an exclusion, not a migration app) |

- **Servers under rehost:** ~**220** (250 − ~15 zombie/retire decommissioned − ~10 replatform tiers moving to PaaS/App Service − 5 net).
- **Replatform size mix:** 3 S · 2 M · 1 L.
- **Test size mix (31 apps):** 14 S · 10 M · 5 L · 2 XL (ERP, Ecommerce).

---

## 4 · Effort roll-up — this estate

| Workstream | Derivation | PD |
|---|---|---|
| Mobilisation & setup | fixed | 10 |
| Landing zone & foundation | 47 + (11 spokes × 0.5) | 53 |
| **Compliance / regulated-spoke controls** | AS-06 does not hold (PCI/SOX/GDPR/HIPAA) — mid of 15–30 range | 20 |
| Assessment — servers | 250 × 0.15 | 38 |
| Assessment — applications | 31 × 1.5 | 47 |
| Wave & move-group design | 10 + 31 × 0.5 | 26 |
| Target architecture / HLD | 6 patterns × 3 + 8 | 26 |
| Rehost execution | 220 × 0.5 | 110 |
| Replatform execution | 3×8 + 2×14 + 1×22 | 74 |
| Repurchase execution | 1 × 6 | 6 |
| Retire / Retain | 2×0.25 + 1×0.5 | 1 |
| Testing (functional + NFR) | 14×1 + 10×2.5 + 5×5 + 2×10 | 84 |
| Wave cutover support | 7 × 3 | 21 |
| Hypercare | 15 × 2 months | 30 |
| Knowledge transfer & handover | fixed | 8 |
| **Delivery subtotal** | | **554** |
| PMO @ 15% | | 83 |
| Architecture governance @ 10% | | 55 |
| **Base estimate** | | **692** |
| Inventory-quality contingency @ **12%** | perf data on 184/250; inventory otherwise current | 83 |
| **Estimate at completion** | | **775 PD** |

| Metric | Value |
|---|---|
| Person-days EAC | **775** |
| Person-months | ~36 |
| Elapsed months | 6 (with float against the 2027-08 Ashburn stop) |
| Peak FTE | ~7.0 |

**Vs. the model's reference estate (823 PD):** more servers (+100) but fewer apps (−14),
and apps are the heavier driver — net slightly lower delivery effort, offset by the +20 PD
compliance block and a lower (12% vs 15%) contingency because the inventory is current.

### 4.2 — manual assessment note

Combined server + application assessment is **85 PD** (38 + 47), roughly double a
tooling-assisted equivalent. The 66 VMs without performance history and the 15 zombie
candidates are where this effort concentrates. If MRG permits a 2-week paid discovery,
contingency drops toward +5% (≈ −50 PD) and replatform sizing tightens.

---

## 5 · Resource loading — 6-month plan

FTE by role by month (M1–M6), person-months (PM). Scaled from the model to ~775 PD / ~36 PM.

| Role | M1 | M2 | M3 | M4 | M5 | M6 | PM |
|---|---|---|---|---|---|---|---|
| Engagement / Delivery Lead | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 3.0 |
| Lead Cloud Architect | 1.0 | 1.0 | 0.8 | 0.6 | 0.5 | 0.4 | 4.3 |
| Landing Zone / Platform Engineer | 1.0 | 1.0 | 0.5 | 0.3 | 0.3 | 0.2 | 3.3 |
| Security / Compliance Specialist (PCI spoke) | 0.5 | 0.7 | 0.5 | 0.3 | 0.3 | 0.2 | 2.5 |
| Network Specialist | 0.6 | 0.6 | 0.4 | 0.3 | 0.2 | 0.2 | 2.3 |
| Migration Engineer — Rehost (×2) | 0.5 | 2.0 | 2.0 | 2.0 | 2.0 | 1.0 | 9.5 |
| App / Data Migration Engineer — Replatform | 0.3 | 0.8 | 1.2 | 1.2 | 1.2 | 0.8 | 5.5 |
| Test Lead / Engineer | — | 0.3 | 1.0 | 1.0 | 1.0 | 0.8 | 4.1 |
| PMO / Migration Coordinator | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 0.5 | 3.0 |
| **Total FTE** | **5.4** | **7.4** | **7.4** | **6.7** | **6.5** | **4.6** | **38.0** |

38.0 PM × ~21.7 working days ≈ 825 PD capacity vs 775 PD EAC — ~6% headroom absorbs
cutover-weekend overtime and the PCI sign-off gates.

### Phase overlay

| Phase | Months | Exit criteria |
|---|---|---|
| Mobilise & Assess | M1 – mid M2 | Validated inventory, disposition, 7-wave plan signed off by the Steering Committee |
| Landing Zone Build | M1 – M2 | ALZ live, ExpressRoute tested, PCI-regulated spoke passes internal security review, first spoke ready |
| Wave 0 pilot | mid M2 | Learning Management + Analytics Sandbox migrated, Print retired — runbook proven |
| Migrate — Waves 1–4 (low/medium risk) | M2 – M4 | ~55% servers in Azure, non-prod ahead of prod, run-books proven |
| Migrate — Waves 5–7 (ERP, PCI, Ecommerce) | M4 – M5 | All in-scope workloads migrated; QSA-witnessed test for PCI waves passed |
| Hypercare & Handover | M5 – M6 | 5-day stability per wave met, Ashburn source powered off, KT accepted |

---

## 6 · Commercial roll-up (illustrative — apply the live rate card)

| Component | PD | Blended rate | Amount (USD) |
|---|---|---|---|
| Delivery (excl. contingency) | 692 | $780 | $539,760 |
| Contingency @ 12% | 83 | $780 | $64,740 |
| Expenses & travel (2 DC decommission visits + cutover weekends) | — | — | ~$22,000 |
| **Services total (T&M ceiling)** | **775** | | **~$626,000** |

Separate proposal line items (not above):

- **Azure run-rate** — now produced by the `estimate_compute_cost` tool (deterministic,
  right-sizes + prices in one call). For this estate, Sweden Central, 1-year RI at 80%
  coverage, AHB on Windows: **compute ~$56k/mo effective, managed disk ~$30k/mo**, total
  **~$86k/mo (~$1.04M/yr)**, range ~$70k–$139k/mo. That is *before* storage right-sizing,
  dev/test pricing on non-prod, and the file-share / DB / PaaS storage lines (E2.3). Tune
  `estimation_config.json` and re-run. (The earlier "~$28–38k/month" figure was a
  hand estimate against a more aggressive 40% right-sizing assumption — superseded.)
  ExpressRoute + backup + LZ fixed services are separate lines; retire against the **$3.0M
  MACC**.
- **Storage run-rate (file / DB / object)** — the `estimate_storage_cost` tool over the
  `storage` table. For this estate, Sweden Central: **file shares ~$8.2k/mo** (5 shares,
  30 TB on Files Premium / NetApp), **PaaS-DB volumes ~$8.3k/mo** (39 volumes, ~53 TB —
  *storage only*; DB compute/licensing is a separate replatform line), **object $0**
  (none). Total **~$16.5k/mo (~$0.2M/yr)**, range ~$12.4k–$20.7k. The 522 block volumes
  (~161 TB) are already in the compute BoM's per-VM managed disk, not double-counted here.
- **Run-rate extras** — the `estimate_run_rate_extras` tool (233 powered-on servers).
  Backup ~$4.2k/mo, internet egress ~$0.5k/mo, monitoring ~$11.5k/mo (Log Analytics
  ~$8.0k at 0.5 GB/server/day + Defender for Servers ~$3.5k), support (Standard) $0.1k/mo
  → **~$16.3k/mo (~$0.2M/yr)**. **One-time migration cost ~$77k** (dual-run: 1.5 months
  at 50% of the infra bill; Azure Migrate/ASR tooling is inside its 180-day free window).
  Excludes ExpressRoute/VPN and LZ fixed services.
- **Full Azure run-rate** = compute+disk ~$86k + storage ~$16.5k + extras ~$16.3k ≈
  **~$119k/mo (~$1.43M/yr)**, plus ~$77k one-time. All from `estimation_config.json` —
  tune and re-run.
- **Microsoft funding** — **Azure Migrate and Modernize (AMM)** partner-led engagement is
  pre-approved (discovery-answers C3); nets down a meaningful share of eligible delivery
  cost. Cloud Accelerate Factory / FastTrack for the landing zone reduces LZ build PD.
- **Managed run** after hypercare — separate RFP (C6).

All figures **DRAFT — architect and commercial review required before external issue.**
