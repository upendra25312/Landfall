# C58 Release and Live Acceptance Report

**Date:** 2026-09-10  
**Target:** Azure Subscription `f609eb5b-df3e-4fab-9a1b-9a8fea2f157f`, Resource Group `rg-landfall`, Region `swedencentral`.

---

## 1. Executive Summary

Cycle 58 executed live release acceptance against Azure `rg-landfall` for the deterministic assessment runtime (C56) and hardened web interface (C57). Key accomplishments:
* **Service Readiness & Smoke:** 8/8 live checks passed (`evidence/cycles/c58/smoke.json`); container apps healthy; EasyAuth enforcing Entra ID on unauthenticated endpoints.
* **Agent Tool Contract Refresh:** The Foundry prompt-agent was refreshed to version 16, adding the OpenAPI contract for `run_assessment` (`scripts/refresh_agent.ps1`).
* **Deterministic Full Assessment Live Pass:** The agent executed `run_assessment` across all 16 stages end-to-end (`evidence/cycles/c58/full-assessment-pass.json`), successfully generating baseline JSON, Excel, Word, and PPTX deliverables.
* **Direct Upload Governance:** Configured exact-origin CORS on Storage for the container app origin and an automated 1-day lifecycle deletion rule for abandoned uploads (`evidence/cycles/c58/direct-upload-controls.json`).
* **FinOps Cost Controls:** Configured monthly Azure Budget of 4,200 INR with 50/80/100% alert thresholds and Log Analytics daily ingestion quota of 0.5 GB (`evidence/cycles/c58/cost-controls.json`).
* **Calculator Job Live Scaling & Rollback Proof:** The event-driven ACA Job `ca-calc-tmglwfatwcsa2` was proven live (`ca-calc-tmglwfatwcsa2-2r5lb` triggered from 0 replicas on queue message). Token acquisition in the older container image failed on `DefaultAzureCredential` without explicit user-assigned client ID; the automated rollback in `scripts/activate_calc_job.py` safely reactivated the legacy revision with zero data loss, and the estimate completed in 29s. Source code in `src/calc/worker.py` and `src/calc/job.py` was updated with `managed_identity_client_id` and startup retry logic.
* **Local Test Suite:** **569 passed, 13 skipped, 0 failed** (100% green) after normalizing Windows CRLF checkout for `purify.min.js`.

---

## 2. Live Verification Results

| Verification Area | Method / Script | Outcome | Evidence File |
|---|---|---|---|
| Service Readiness | `scripts/smoke.py` | **PASS** (8/8 checks, 20 Azure resources) | `smoke.json` |
| Foundry Agent v16 | `scripts/validate_live.py` | **PASS** (invocation & conversation) | `agent-roundtrip-retry.json` |
| Full Assessment Pipeline | `scripts/validate_full_assessment.py` | **PASS** (all 16 stages completed, deliverables created) | `full-assessment-pass.json` |
| Direct Upload Controls | `scripts/configure_direct_uploads.py` | **PASS** (exact CORS origin + 1-day lifecycle rule) | `direct-upload-controls.json` |
| FinOps Cost Budget | `scripts/configure_cost_controls.py` | **PASS** (4,200 INR, 50/80/100% alerts, 0.5 GB Log Analytics cap) | `cost-controls.json` |
| Calculator Job Scaler | `scripts/activate_calc_job.py` | **PROVEN** (scale-from-0 trigger proven; safe rollback; legacy completed in 29s) | `calc-job` execution log |
| Local Regression Suite | `pytest` | **PASS** (569 passed, 13 skipped, 0 failed) | Pytest console output |

---

## 3. Findings & Code Improvements

1. **Windows Line-Ending Normalization:** `tests/test_web_csp.py` had an integrity check failure on `purify.min.js` due to Git's Windows CRLF checkout. Added LF normalization (`.replace(b'\r\n', b'\n')`) to maintain cross-platform test parity.
2. **Container Apps Job User-Assigned Identity:** In Azure Container Apps Jobs, `DefaultAzureCredential()` requires `managed_identity_client_id=os.environ.get("AZURE_CLIENT_ID")` to avoid empty identity endpoint responses. Updated `src/calc/worker.py` and added startup backoff retries in `src/calc/job.py`.
3. **Optional Storage in Assessment Pipeline:** Fixed `src/api/assessment.py` to record a valid zero-cost storage record when an engagement provides compute without separate storage exports, preserving stable deliverable generation schemas.

