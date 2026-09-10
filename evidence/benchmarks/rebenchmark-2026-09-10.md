# Azure Pricing, SKU & CAF Quarterly Re-benchmark Report (2026-09-10)

- **Audit Date:** 2026-09-10
- **Target Region:** `swedencentral`
- **Data Source:** Offline deterministic fixture (zero network)
- **Catalog Version Pinned:** `2026-09`
- **Drift Threshold:** `±5.0%`
- **Overall Audit Status:** **APPROVED**

## 1. Executive Summary

| Audit Dimension | Metric / Scope | Result | Status |
|---|---|---|---|
| VM SKU Coverage | 35 SKUs across F/D/E families | 0 drifts >= 5.0% | ✓ PASS |
| Managed Disk Coverage | 11 tiers (P4–P80) | 0 drifts >= 5.0% | ✓ PASS |
| CAF Alignment | Cloud Adoption Framework baselines | 5/5 criteria met | ✓ PASS |
| Generation Freshness | v5 General Purpose & Memory | All families current | ✓ PASS |

## 2. VM SKU Family Generation Audit

| Family | Series | Curated Count | Status | Recommendation |
|---|---|---|---|---|
| **F** (Standard_F2s_v2) | `v2` | 8 SKUs | Mature generation | Retain v2 (Fsv2 / FX) |
| **D** (Standard_D2s_v5) | `v5` | 8 SKUs | Current standard | Retain v5 (v6 (in preview/rollout)) |
| **E** (Standard_E2s_v5) | `v5` | 19 SKUs | Current standard | Retain v5 (v6 (in preview/rollout)) |

## 3. Microsoft Cloud Adoption Framework (CAF) Conformance

| Criterion | Standard / Requirement | Status | Verification Detail |
|---|---|---|---|
| **General-Purpose RAM/vCPU Ratio** | >= 4.0 GiB per vCPU for general-purpose workloads (D-series) | **PASSED** | D-series SKUs maintain exactly 4.0 GiB/vCPU (e.g. Standard_D4s_v5: 4 vCPU, 16 GiB). |
| **Memory-Optimized DB Ratio** | >= 8.0 GiB per vCPU or constrained-vCPU for database workloads | **PASSED** | E-series includes constrained-core SKUs (e.g. Standard_E8-4s_v5) for SQL licensing optimization. |
| **Storage Tier Foundation** | Managed Premium SSD v1 as production baseline with burst IOPS | **PASSED** | P4 through P80 provisioned IOPS tiers match Azure storage architecture baseline. |
| **Regional Availability Zones** | 3 Availability Zones active in primary deployment region | **PASSED** | Region 'swedencentral' provides native Availability Zones for zone-redundant landing zone architecture. |
| **Reserved Instance Optimization** | 1-Year and 3-Year Reserved Instances modeled alongside PAYG | **PASSED** | Landfall models 1Y and 3Y reservations with deterministic ~38% and ~58% savings rates. |

## 4. Price Drift Analysis

✓ **No VM SKU price drift detected.** All rates match pinned baselines within tolerance.

✓ **No Managed Disk price drift detected.** All tiers match pinned baselines within tolerance.

## 5. Audit Conclusion & Next Scheduled Review

- **Audit Status:** APPROVED
- **Re-benchmark Interval:** Quarterly (S2 requirement)
- **Next Review Due:** 2026-12-09
- **Sign-off:** Automated Landfall FinOps & Cloud Architecture Subsystem
