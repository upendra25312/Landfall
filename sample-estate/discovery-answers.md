# Discovery Questionnaire — Completed Response

**Client:** Meridian Retail Group (MRG) — omnichannel retailer, ~4,800 staff
**Respondent:** MRG Enterprise Architecture, with input from Infrastructure, DBA, Network, Security and App teams
**Date:** 2026-09-07 · **Questionnaire version:** 1.0
**Status:** Synthetic. Answers are consistent with the `sample-estate/` inventory
(`servers.csv`, `applications.csv`, `dependencies.csv`, `storage.csv`) — 250 VMware VMs,
31 applications. Use for demos and testing the Landfall agent, not a real engagement.

> Cross-reference: the estate this describes has **150 Windows / 100 Linux** VMs across
> **Ashburn (144)**, **Dallas (103)** and a small **Reno DR** site (3); **1,940 vCPU**,
> **~10.3 TB RAM**, **~186 TB** provisioned block storage (~106 TB used); **84 VMs past
> OS end-of-support**; **66 VMs (26%) with no performance history**.

---

## 1 · Data pack

| Artefact | Provided as | Notes |
|---|---|---|
| Server / VM inventory | `servers.csv` | vCenter export, 2026-08-30. Covers all three sites. |
| Performance data | embedded in `servers.csv` (`cpu_avg_pct`, `cpu_peak_pct`, `ram_avg_pct`) | Present for 184 of 250 VMs; 66 recently built or migrated between clusters and have <30 days history. |
| Application portfolio | `applications.csv` | CMDB extract, reviewed by app owners Aug 2026. 31 apps (30 business + 1 infrastructure-services bucket). |
| Dependency map | `dependencies.csv` | Derived from firewall logs + vRNI netflow (90-day) + SME validation. 467 edges. Confidence graded per edge. |
| Database inventory | in `applications.csv` (`db_engine`, `tech_stack`) and `storage.csv` (`type='db'`) | 39 database volumes across SQL Server, Oracle, PostgreSQL, MySQL, MongoDB. |
| Storage & backup | `storage.csv` | Array + per-VM disk export. Backup policy summarised in §5. |
| Network diagrams | *not included in this pack* | Described in §9; Visio pack to follow. |
| Architecture / design docs | *not included* | Standards summarised in §11–12. |
| Licensing position | described in §3 | Windows/SQL under active SA; quantities in C4. |

---

## 2 · Business & programme context

- **B1 — Primary driver / hard date.** Data-centre lease exit. The **Ashburn (DC-ASHBURN)** colocation contract ends **2027-09-30** with no renewal option; **Dallas (DC-DALLAS)** lease ends 2028-06-30. Ashburn is the hard stop — all Ashburn workloads (144 VMs) must be out by 2027-08-31 to allow decommissioning. Secondary drivers: eliminate ~$1.1M/yr colo + hardware refresh, improve resilience (current DR is unproven).
- **B2 — Budget envelope.** Capital-funded migration programme approved at **$2.4M** services + first-year Azure run-rate; overruns require steering-committee approval.
- **B3 — Definition of done.** **Full exit of both data centres.** No hybrid steady state beyond a short coexistence window per wave. Mainframe/AS-400 — none in scope (see I6).
- **B4 — Target region(s).** Primary **Sweden Central** (MRG EMEA HQ, GDPR data-residency preference for EU customer data); DR **West Europe**. US-origin operational data has no residency constraint but stays in-region for latency.
- **B5 — Appetite for change.** Predominantly **rehost**. Opportunistic replatform where the lift is small and the payback is clear (single-DB apps → Azure SQL / Flexible Server; the two container-ready apps → AKS). No refactoring in this programme.
- **B6 — Blackout periods.** Retail peak **15 Nov – 2 Jan** (no production cutovers). Quarter-end finance freeze last 3 business days + first 2 of each quarter. Payroll runs 25th–month-end.
- **B7 — Sponsor / go-no-go.** Executive sponsor: CIO. Wave go/no-go: the Migration Steering Committee (CIO, Head of Infrastructure, Head of Apps, CISO, Finance BRM).
- **B8 — Incumbent partner.** Colo + network managed by an incumbent MSP under contract to 2027-12-31; their scope is facilities and WAN only. No application or cloud scope — no conflict, but WAN change requests route through them.

---

## 3 · Commercial & Microsoft programmes

- **C1 — Agreement type.** Microsoft Customer Agreement (MCA-E), annual, renews **2027-03-31**.
- **C2 — MACC.** Yes — a **$3.0M / 3-year** Azure Consumption Commitment signed 2026-03; ~$180k retired to date. This programme's run-rate retires against it.
- **C3 — Microsoft funding / account team.** **Azure Migrate and Modernize (AMM)** partner-led engagement pre-approved by the MRG Microsoft account team (ATU: EMEA Retail). ECIF not yet requested. Account team engaged and supportive.
- **C4 — Software Assurance / Azure Hybrid Benefit.** Active SA on **180 Windows Server** core-licence packs (2-core) and **8 SQL Server Enterprise** (4-core) + **12 SQL Server Standard** (2-core). All eligible for AHB. Oracle: 4 processor licences, ULA expired — bring-your-own to Azure permitted.
- **C5 — RI / Savings Plan appetite.** Willing to commit **1-year** reservations for steady-state production compute after the 30-day right-size review; **3-year** only for the ~40 VMs confirmed long-lived. Savings Plan for compute preferred for flexibility.
- **C6 — Managed run service.** **Separate RFP.** This response covers build + migrate + hypercare only.

---

## 4 · Compute & virtualisation

- **I1 — Hypervisor.** **VMware vSphere 7.0 U3** exclusively. 6 clusters (3 Ashburn, 2 Dallas, 1 Reno). No Hyper-V, Nutanix, or bare metal in scope.
- **I2 — VMs by environment / OS.** 250 VMs. Environment: **prod 173, non-prod 47, dev 27, DR 3**. OS family: **Windows 150, Linux 100**. Detail: Windows Server 2012 R2 ×32, 2016 ×46, 2019 ×51, 2022 ×21; RHEL 7.9 ×24, RHEL 8.8 ×21, RHEL 9.3 ×9, Ubuntu 18.04 ×11, 20.04 ×17, 22.04 ×12, SLES 15 SP4 ×6. (Authoritative counts in `servers.csv`.)
- **I3 — Unsupported / EOL OS.** **84 VMs past OS end-of-support**: 32× Windows Server 2012 R2, 24× RHEL 7.9, 17× Ubuntu 20.04, 11× Ubuntu 18.04. Plan: migrate as-is to IaaS, then in-place upgrade or apply ESU post-move; Ubuntu covered by Ubuntu Pro on Azure. No 2008/RHEL 6.
- **I4 — Non-virtualisable physical.** None. Two legacy tape-library controllers are being retired with the DC (not in migration scope).
- **I5 — Specialised compute.** No GPU/HPC. **4 large-memory hosts** (256 GB) — the ERP (SAP ECC) database tier and the BI tier; map to Azure E-series / M-series as sized.
- **I6 — Appliances / non-x86.** None. Legacy billing runs on Windows VMs (already offloaded from a retired mainframe). Two hardware load-balancer appliances (F5) — replaced by Azure Application Gateway + WAF, not migrated.
- **I7 — Utilisation profile.** Heavily **over-provisioned** — median prod CPU average ~12%, peak ~35%. ~15 VMs identified by owners as idle/zombie candidates (mostly the 17 powered-off VMs plus ~5 powered-on with no traffic). Right-size down expected on ~60% of the estate.
- **I8 — Build standard / patching.** Windows: MDT golden images + WSUS. Linux: Ansible + Red Hat Satellite (RHEL), unattended-upgrades (Ubuntu). Target: Azure Update Manager.

---

## 5 · Storage & backup

- **S1 — Capacity.** Block: **~186 TB provisioned / ~106 TB used** across VM disks (see `storage.csv`). File: ~38 TB on 5 CIFS/NFS shares (finance, marketing assets, engineering, user home, archive). Object: none on-prem. DB volumes: ~11 TB.
- **S2 — Arrays / shared LUNs.** Two Pure Storage FlashArrays (Ashburn, Dallas) presenting VMFS datastores; no raw-device mappings. **5 shared file shares** back multiple apps — these are called out in `storage.csv` (`type='file'`) and must move as move-groups.
- **S3 — Performance-sensitive volumes.** ERP DB, Order Management DB, Payment Gateway DB and Fraud Detection stores need **≥ 7,500 IOPS** and low latency — target Premium SSD v2 / Ultra Disk or the relevant PaaS tier (see `target_service` in `storage.csv`).
- **S4 — Backup.** **Veeam Backup & Replication 12**. Nightly incrementals (20:00–04:00 window), weekly synthetic full, 35-day retention on-site + 90-day immutable copy to a Wasabi object bucket. Target: **Azure Backup** (VM + SQL/Oracle where IaaS) with immutable vault; ANF snapshots for file.
- **S5 — Archive / WORM.** ~9 TB of finance records under 7-year regulatory retention (SOX) on the archive share — target Azure Blob cool/archive with a legal-hold policy.
- **S6 — Data seeding.** ExpressRoute (see N2) provides sufficient bandwidth to seed over ~4–5 weeks with replication throttling. **No Data Box** planned; hold as a fallback if the circuit slips.

---

## 6 · Databases & middleware

- **D1 — Engines / counts.** SQL Server 2016 (5 instances), SQL Server 2019 (4), Oracle 19c (5), PostgreSQL 13 (5), MySQL 5.7 (2), MongoDB 4.4 (3). ~39 databases total (see `storage.csv` `type='db'`, `applications.csv` `db_engine`).
- **D2 — Largest / strict RPO-RTO.** ERP (SAP ECC) Oracle DB ~3.2 TB, RPO 15 min / RTO 2 h. Ecommerce PostgreSQL ~1.1 TB and Payment Gateway MySQL ~400 GB, RPO ~0 / RTO < 30 min, 24×7. Order Management SQL Server ~900 GB, RPO 15 min.
- **D3 — HA/DR today.** SQL Server: Always On AGs for Order Management, BI, Document Management. Oracle: Data Guard (physical standby) for ERP. PostgreSQL: streaming replication. MySQL: primary/replica. MongoDB: 3-node replica sets.
- **D4 — PaaS openness.** **Open to PaaS** where it's a config-only move: PostgreSQL/MySQL → Azure Database for PostgreSQL/MySQL Flexible Server; the 4 smaller SQL Server DBs → Azure SQL Managed Instance. ERP Oracle and the two AG-clustered SQL workloads stay **IaaS** this programme.
- **D5 — Oracle licensing.** 4 processor licences, BYOL to Azure (ULA lapsed). No contractual bar on Azure. Oracle Database@Azure considered for ERP if sizing warrants (noted in `storage.csv` targets).
- **D6 — Middleware / integration.** RabbitMQ (3 nodes, shared bus), HAProxy (edge for Linux apps), Apache Tomcat / Spring Boot app servers, a Windows batch scheduler (Control-M agent) on the Legacy Billing tier. MFT via a small OpenText instance (part of Document Management).
- **D7 — Embedded config.** Known hardcoded IPs in: Payment Gateway (acquirer allow-lists), Fraud Detection (partner feeds), Legacy Billing (bank host). ~40 service accounts with SPNs. Certificate inventory maintained in the internal CA (see ID/SC).

---

## 7 · Application portfolio

- **A1 — App count / completeness.** **31** (30 business applications + "Core IT Infrastructure Services"). CMDB actively maintained; owners re-confirmed all entries Aug 2026. Confidence high.
- **A2 — Criticality / users / peak.** Per `applications.csv`: **13 apps at criticality 1**, 8 at C2, 6 at C3, 4 at C4. Combined user base ~628k (dominated by Corporate Website ~300k and Ecommerce Storefront ~210k external users). Peak load tracks retail seasonality (Nov–Dec) for customer-facing apps; internal apps peak at month-end.
- **A3 — Retire / SaaS-bound.** **Print & Output Management** — retire (moving to a SaaS provider Q1 2027, out of migration scope). **Analytics Sandbox** — retire (superseded by the Data Lake). **Learning Management** — retain on-prem short-term then repurchase (SaaS LMS selected, cutover mid-2027).
- **A4 — COTS vendor support.** SAP ECC — supported on Azure (SAP note 1928533). Dynamics CRM (on-prem) — supported. OpenText, Control-M, Veeam — all Azure-supported. No COTS app blocks migration.
- **A5 — Custom apps.** ~11 in-house apps (Ecommerce, Customer Portal, Partner API, Field Service backend, Fraud Detection, Inventory Forecasting, others). Active dev teams for 8; Azure DevOps pipelines exist for 6. Source available for all.
- **A6 — Internet-facing.** **13 internet-facing apps** (`internet_facing=1` in `applications.csv`): Ecommerce, Payment Gateway, Customer Portal, HR Self-Service, Corporate Website, Email Security Gateway, Identity Provider (ADFS), VPN, Marketing Automation, Partner API, Field Service backend, Learning Management, API Gateway. Today behind F5 LTM/ASM + Akamai CDN for the two highest-traffic. Target: Application Gateway v2 + WAF, Front Door + CDN for Ecommerce and Corporate Website.
- **A7 — Hardware dependencies.** None (no dongles/fax/telephony/SCADA/lab). Contact Centre Platform integrates with a cloud CCaaS via SIP — no on-prem hardware.
- **A8 — Change freeze / audit.** ERP under a rolling SOX audit — cutover must be scheduled with Finance and evidenced. Payment estate under annual PCI assessment (QSA visit each March) — no cutovers in March for PCI-scoped apps.
- **A9 — UAT authorisation.** Each app has a named business owner (see `business_owner` in `applications.csv`) who authorises UAT. Test execution by the app teams with MRG QA coordination; capacity is the main risk (see RK-05 / effort model).

---

## 8 · Dependencies & integration

- **X1 — Dependency map maintained?** Partially. A firewall-rule + netflow analysis (vRealize Network Insight, 90 days) plus SME workshops produced `dependencies.csv` (467 edges, confidence-graded). Not a live CMDB relationship set — validate per wave.
- **X2 — Chatty pairs that move together.** Web→app→DB tiers of each 3-tier app (Ecommerce, Customer Portal, Order Management, ERP, Contact Centre, Partner API, Document Management, CRM). Fraud Detection ↔ Payment Gateway (sub-10ms). BI ↔ ERP DB (nightly ETL, high volume). These are the move-group anchors.
- **X3 — External / third-party.** Payment acquirer (IP allow-listed, TLS mutual auth), 3 logistics partners (SFTP + REST), a tax-calculation SaaS, government e-invoicing endpoint (EU), Akamai, a marketing ESP. All require the new Azure egress IPs to be allow-listed — client-owned action, ~2–4 weeks lead each.
- **X4 — Shared services.** Active Directory (6 DCs), DNS/DHCP (4 servers), SMTP relay (2), the 5 file shares, print, Zabbix/Grafana monitoring, ELK logging, WSUS, internal CA. Modelled as the "Core IT Infrastructure Services" app; every server has AD + DNS edges in `dependencies.csv`.
- **X5 — Latency-sensitive during transition.** Fraud Detection ↔ Payment Gateway, and app↔DB tiers of Ecommerce and ERP. These move as whole waves; no split across a hybrid hop.

---

## 9 · Network & connectivity

- **N1 — WAN.** Dual MPLS (primary carrier 1 Gbps Ashburn, 500 Mbps Dallas) + SD-WAN overlay to branches. ~40% spare on the Ashburn circuit off-peak — usable for replication seeding with QoS.
- **N2 — Azure connectivity.** **ExpressRoute** — a **1 Gbps** circuit (standard, metered) to be ordered by MRG in month 1 via the incumbent MSP; **backup S2S VPN** at go-live for resilience and as an interim if the circuit slips. Single hub in Sweden Central.
- **N3 — IP plan.** On-prem uses `10.20.0.0/14` (Ashburn `10.20–21`, Dallas `10.22–23`, Reno `10.23.240/20`). No known overlap with the proposed Azure `10.100.0.0/14`. Partner VPNs use documented `172.16` ranges.
- **N4 — Re-IP tolerance.** **Most apps tolerate re-IP** (DNS-based). Exceptions requiring IP preservation or careful cutover: Payment Gateway, Fraud Detection, Legacy Billing, Identity Provider (ADFS), and the 5 file shares (referenced by UNC + hardcoded mounts). ~15 servers total.
- **N5 — DNS.** Microsoft AD-integrated DNS, split-horizon (`meridianretail.com` external via a hosted provider, `corp.meridianretail.com` internal). Managed by the infra team. Target: Azure Private DNS + resolver, conditional forwarders during coexistence.
- **N6 — Perimeter.** F5 (LTM + ASM) for load-balancing/WAF, Palo Alto firewalls at each DC edge, Zscaler for user web egress, no on-prem IDS beyond Palo Alto threat prevention. Replicate in Azure with Azure Firewall Premium + Application Gateway WAF; user egress stays on Zscaler.
- **N7 — Egress / breakout.** Centralised breakout today via Palo Alto + Zscaler. Azure: forced-tunnel server egress through Azure Firewall in the hub, with inspection; no direct internet from spokes.
- **N8 — Existing Azure footprint.** A small dev/test subscription (~15 resources, unmanaged) and Microsoft 365 / Entra ID already in place. The dev/test subscription will be brought under the new ALZ management group or retired.

---

## 10 · Identity & directory

- **ID1 — Active Directory.** Single forest `corp.meridianretail.com`, single domain, functional level 2016. 6 DCs (4 Ashburn, 2 Dallas). ~6,500 user objects, ~4,000 computer objects, ~40 service accounts with SPNs.
- **ID2 — Entra ID / federation.** Entra ID in use for Microsoft 365. **Entra Connect** (password hash sync + SSPR) plus **ADFS** for ~6 legacy SAML apps. Licence: **Entra ID P1** estate-wide, **P2** for ~200 privileged/finance users.
- **ID3 — AD in Azure.** **Extend AD** — deploy 2 replica DCs into the Azure hub (new AD site), keep the forest. No greenfield identity this programme. Retire ADFS opportunistically by moving those apps to Entra SAML/OIDC (tracked separately).
- **ID4 — Privileged access.** Tiered admin model (T0/T1/T2), PAWs for T0. No dedicated PAM product — using Entra PIM for cloud roles and a break-glass account per tier. Target: Entra PIM + Azure Bastion, no standing RDP.
- **ID5 — Service accounts / Kerberos.** ~40 SPN-bound service accounts; ~12 use gMSA. Kerberos constrained delegation on 3 apps (Document Management, CRM, BI). Migration must preserve SPNs and keep the apps domain-joined.

---

## 11 · Security & compliance

- **SC1 — Regimes in scope.** **PCI-DSS** (Ecommerce, Payment Gateway, Contact Centre, Fraud Detection — `compliance_scope='PCI-DSS'`, 4 apps), **SOX** (7 finance/ERP apps), **GDPR** (4 apps handling EU customer PII), **HIPAA** (1 — HR Self-Service, occupational-health data). ISO 27001 certified organisation-wide.
- **SC2 — Data classification / residency.** 4-tier scheme (Public / Internal / Confidential / Restricted). EU customer PII and cardholder data are Restricted and must stay in EU regions (Sweden Central / West Europe) with **customer-managed keys** (Key Vault / Managed HSM) for storage and DB TDE.
- **SC3 — Mandated baselines.** Internal standard aligned to **CIS Azure Foundations v2** and NIST 800-53 moderate for the PCI segment. Landing zone must ship with Azure Policy enforcing these.
- **SC4 — SIEM / SOC.** Splunk Enterprise on-prem, 24×7 SOC (co-managed with the incumbent MSP). Plan: forward Azure activity + Defender + NSG flow logs to Splunk via an event hub; **Microsoft Sentinel** evaluated as a fast-follow, not in this programme.
- **SC5 — Vuln mgmt / endpoint / CASB.** Tenable Nessus (vuln), CrowdStrike Falcon (endpoint, carries forward to Azure VMs), Netskope (CASB, unchanged). Add Microsoft Defender for Cloud (servers + SQL + containers) in the landing zone.
- **SC6 — Sign-off gates.** Internal security review + a QSA-witnessed test for PCI-scoped waves before go-live. Annual external pen test (next: Feb 2027) must cover the migrated PCI segment.
- **SC7 — Data-handling approval.** Approved. MRG Legal + CISO signed a data-processing addendum on 2026-08-20 authorising placement of the inventory (no cardholder data, no PII) in the assessment Data Lake under the existing MNDA. No redaction required for the fields provided.

---

## 12 · Operations & ITSM

- **O1 — ITSM.** ServiceNow (ITSM + CMDB + Change). CAB weekly (Wed), emergency CAB on demand. Migration changes raised as a programme change series with pre-approved standard templates per wave.
- **O2 — Monitoring.** Zabbix + Grafana (infra), SolarWinds NPM (network), Splunk (logs/security), app-level New Relic on 6 custom apps. Target: **Azure Monitor + Managed Grafana + AMBA alert baseline**; New Relic retained for the custom apps.
- **O3 — Maintenance windows.** Non-prod: any time with 24 h notice. Prod: **Tue/Thu 22:00–02:00** for routine; **cutover windows Sat 20:00 – Sun 12:00**, ~3 per month available outside blackout periods. Payroll and finance apps: Sunday only.
- **O4 — Automation maturity.** Medium. Terraform for the existing Azure dev/test; Ansible for Linux config; limited Windows DSC. IaC pipeline for the landing zone is in programme scope.
- **O5 — Post-migration operator.** **Undecided — separate RFP.** Assume MRG operates during hypercare with our support; transition-to-run is out of scope here.
- **O6 — Tagging / naming / cost allocation.** ServiceNow-driven CMDB is the source of truth. Required Azure tags: `CostCentre`, `Application`, `Environment`, `DataClassification`, `Owner`. Chargeback by cost centre monthly.

---

## 13 · Resilience & DR

- **R1 — RPO / RTO by tier.** Tier 1 (criticality 1, ~13 apps): RPO ≤ 15 min, RTO ≤ 2 h. Tier 2: RPO ≤ 1 h, RTO ≤ 8 h. Tier 3: RPO ≤ 24 h, RTO ≤ 48 h. Tier 4: best-effort, RTO ≤ 5 days.
- **R2 — Current DR.** Cold/warm second site at Reno (3 VMs — DNS, a domain controller, and a Veeam replica target). **Last full DR test: 2024** (partial, failed to meet RTO on ERP). Effectively unproven — a key driver for the move.
- **R3 — Target Azure resilience.** **Sweden Central with Availability Zones** for production; **region pair West Europe** for DR of Tier 1 + Tier 2 via Azure Site Recovery / native DB replication. No active/active required. No single app needs multi-region active.
- **R4 — Backup retention / restore tests.** 35-day operational + 7-year SOX archive (finance). Quarterly restore tests are a control requirement — must be reproducible in Azure Backup.
- **R5 — Migration as DR event / rollback.** **Fallback to on-prem required per wave** until the wave's hypercare exit (typically 5 business days), then the source VMs are powered off and the fallback removed. Ashburn source infrastructure is fully decommissioned only after all Ashburn waves pass hypercare.

---

## 14 · Non-functional & constraints

- **F1 — Performance SLAs.** Ecommerce page render < 2 s p95; Order Management order commit < 3 s; nightly ERP batch must finish by 05:30. These must be held or improved post-migration.
- **F2 — Availability SLAs.** Ecommerce and Payment Gateway: 99.9% contractual to the business (revenue-linked). Corporate Website: 99.5%. Others: internal targets only.
- **F3 — Sustainability.** MRG has a public net-zero-by-2035 commitment; the programme should report the estimated carbon reduction from DC exit (Azure emissions dashboard) — reporting only, not a design constraint.
- **F4 — Team constraints.** Background checks required for anyone with production or cardholder-data access (BS7858 equivalent). No nationality restriction. On-site presence needed only for the two DC decommissioning events. Working hours: cutovers in client timezone (CET).
- **F5 — Tooling constraints.** **Confirmed:** no discovery tooling ran on the estate, but **Azure-side replication tooling is permitted** — ASR agent installed on VMs at migration time is acceptable, as is Azure Database Migration Service. This keeps waves **online / near-zero-downtime** rather than offline. (This resolves the biggest open risk from the questionnaire.)
- **F6 — Documentation / handover.** English. Runbooks in Markdown in the MRG Azure DevOps wiki; HLD/LLD as PDF; a recorded KT session per workstream.

---

## 15 · Migration preferences

- **M1 — Wave sizing.** By **application affinity / move-group**, sequenced low-risk-first, then by criticality. Aim ~4–6 apps and ~35–45 servers per wave.
- **M2 — Wave-zero pilot.** **Learning Management** and **Analytics Sandbox** (both criticality 4, non-prod-like, few dependencies) plus **Print & Output Management** (retire rehearsal). Proves the landing zone, ASR runbook, and cutover process.
- **M3 — Cutover windows.** Saturday 20:00 – Sunday 12:00, ~3 per month outside the Nov–Jan blackout and the March PCI window.
- **M4 — Coexistence period.** Up to **6 weeks** per wave for hybrid operation; target 2 weeks. Full estate coexistence not to exceed the Ashburn lease runway.
- **M5 — Hard stop.** **Ashburn decommission by 2027-08-31** (lease ends 2027-09-30). Dallas by 2028-Q1 (softer).
- **M6 — Client resources committed.** Named and committed: 1 infra lead, 2 Windows + 1 Linux engineers (part-time), 1 lead DBA + 1 DBA, 1 network engineer, 6 app owners for UAT coordination, 1 ServiceNow/change coordinator. Test execution capacity is the constraint — see effort model RK-05.

---

## 16 · Working assumptions register — client position

| ID | Assumption | MRG response |
|---|---|---|
| AS-01 | Inventory ≥ 90% complete, < 6 months old | **Holds.** vCenter + CMDB extracts from Aug 2026; owners re-validated. |
| AS-02 | ≥ 30 days performance data for prod | **Partially.** 184/250 VMs have it; 66 do not (recent builds/moves). Carry conservative sizing for those 66. |
| AS-03 | Azure-side replication tooling permitted | **Confirmed permitted** (see F5). Online waves. |
| AS-04 | Disposition ≈ 70% rehost / 18% replatform | **Broadly holds** — see effort-inputs.md for the actual mix. |
| AS-05 | Single region + one DR region, one hub | **Holds** — Sweden Central + West Europe, one hub. |
| AS-06 | Standard corporate compliance only | **Does NOT hold** — PCI-DSS, SOX, GDPR, HIPAA all in scope. Regulated spoke + controls required; re-price per RK-07. |
| AS-07 | ExpressRoute ordered month 1 | **Holds** — MRG action, via incumbent MSP. |
| AS-08 | Client provides named owners/DBAs/testers | **Holds** for infra/DBA/network; **test execution capacity is thin** — see RK-05. |
| AS-09 | Apps tolerate re-IP | **Mostly** — ~15 servers need IP preservation / careful cutover (N4). |
| AS-10 | No refactoring | **Holds.** |
| AS-11 | Client runs UAT | **Holds** — we support and triage. |
| AS-12 | Data-handling approved under MNDA | **Holds** — DPA signed 2026-08-20 (SC7). |
| AS-13 | No mainframe / midrange / non-x86 | **Holds.** |
| AS-14 | Managed run out of scope | **Holds** — separate RFP (C6). |

**Net effect:** AS-06 is the material change — PCI/SOX/GDPR/HIPAA scope adds landing-zone
controls, a regulated spoke, and security sign-off gates (+15–30 PD, per the effort model).

## 17 · Risk register — client-informed notes

| ID | Client-side note |
|---|---|
| RK-01 | Inventory quality is good; residual risk is the 66 VMs without perf data and ~15 idle candidates. |
| RK-02 | Right-size review at day 30 accepted; RI/Savings Plan purchase deferred to month 3 (C5). |
| RK-03 | Move-groups defined from `dependencies.csv` + SME workshops; per-wave dress rehearsal agreed. |
| RK-04 | ExpressRoute is the top schedule risk — MSP lead time historically 6–8 weeks; VPN interim designed in. |
| RK-05 | **Elevated.** MRG test execution capacity is 6 part-time app owners; automate smoke tests, stagger UAT, sponsor escalation path agreed. |
| RK-06 | Replatform candidates are all small single-DB or container-ready; design spike per app before commit. |
| RK-07 | **Now certain, not a risk** — PCI/SOX/GDPR/HIPAA confirmed in scope (SC1). Priced in, not contingent. |
| RK-08 | **Retired** — Azure-side replication tooling permitted (F5). Online migrations. |
| RK-09 | Retired — DPA signed (SC7). |
| RK-10 | 84 EOL VMs; ESU/upgrade effort per server added; sequenced later in the wave plan. |
| RK-11 | T&M ceiling with the assumptions schedule attached; every agent output watermarked DRAFT. |
| RK-12 | 1 Gbps ExpressRoute + off-peak throttled seeding is sufficient; Data Box held as fallback (S6). |
