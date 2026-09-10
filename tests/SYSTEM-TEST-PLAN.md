# Landfall system test plan — C53

This is the regression and release plan for the implemented product. A pass in
one layer does not imply a pass in another: mocked functional tests do not prove
Azure permissions, and HTTP 401 proves an auth boundary, not a working chat.
Roadmap-only E13/E15 features are not represented as implemented features.

**Latest execution:** [C54 results](../evidence/cycles/c54/REPORT.md) close the
LibreOffice, four-adapter, live agent/SQL, ingestion and calculator-queue checks.
Interactive Entra, public CI approval, scratch capacity/OIDC and independent
reviewers remain prerequisites. C54 adds `validate_agent_roundtrip.py`,
`validate_calculator_tail.py`, `validate_production_browser.py`,
`validate_queue_pipeline.py` and `validate_agent_queue.py` under `scripts/`.

## Execution and acceptance

1. **Plan:** inventory components, interfaces, fixtures, expected results, risks.
2. **Do:** run baseline and new negative/journey cases; retain failing evidence.
3. **Check:** fix reproduced defects; run the complete local regression, evals,
   browser suite, evidence drift checks and available live probes.
4. **Act:** record defects/results/limitations, deploy validated service changes,
   repeat smoke, update tracker/PRD/handoff and merge the cycle branch `--no-ff`.

The runner is `scripts/validate_system.py`; use the project's Python:

```powershell
.venv2\Scripts\python.exe scripts\validate_system.py --output evidence/cycles/c53/local
.venv2\Scripts\python.exe scripts\validate_system.py --live --output evidence/cycles/c53/live
.venv2\Scripts\python.exe scripts\validate_system.py --external --output evidence/cycles/c53/external
```

Local gates must exit zero: pytest, deterministic evals, backtest/broken-dump and
scorecard drift, browser journeys. Every command gets a log and a result record.
Unavailable optional integrations are **NOT RUN/BLOCKED**, never PASS. Runtime
timeouts and command failures fail their gate. Preserve the historical scorecards
unless a purposeful scoring/model change is reviewed separately.

## Component and feature matrix

| ID | Component/features | Automated proof and expected result | Additional live/manual proof |
|---|---|---|---|
| V01 | Ingestion: native/RVTools/CMDB, overrides, CSV/XLSX, bad encoding/data, idempotent load, bulk ingest | `test_ingest_*`, `test_run_engagement`, `test_broken_dumps`; exact normalized counts, defects named, no silent partial success | Isolated engagement upload → Event Grid → Function → SQL → DQ report |
| V02 | SQL query tool, allow-list, timeout, RLS context, engagement scope | `test_sqlguard`, `test_engagement_required`, `test_engagement`, `test_access_control`; hostile SQL/absent scope rejected | Two principals/engagements, real SQL RLS and managed-identity access |
| V03 | Rightsizing/pricing, compute/storage/extras, cost bands | `test_rightsize`, `test_compute_cost`, `test_storage_cost`, `test_run_rate`, backtest 3 estates × 3 methods; reproducible sourced figures | Dated retail-price lookup; independent FinOps review |
| V04 | 6R, dependency waves, durations, blackouts, critical path | `test_waves`, `test_wave_schedule`; dependencies, ordering and schedule constraints hold | Architect reviews representative estate |
| V05 | Effort, contingency, monthly loading, peak FTE | `test_deliverable`, `test_effort_loading`; sums reconcile, DQ affects contingency | PMO validates rate/throughput assumptions |
| V06 | Landing zone, resiliency, ALZ/AI-LZ conformance, diagrams | `test_landing_zone`, `test_lz_conformance`, `test_lz_diagram`, `test_lz_render`; data changes topology; deterministic SVG/drawio | Key-authenticated drawio SVG→PNG render |
| V07 | Assemble/export/publish, traceable figures, registers, history | `test_deliverable`, `test_export`, `test_dashboard`, `test_answer_xlsx`, `test_xlsx_recalc`; valid files and source IDs | Real office-app review; LibreOffice recalc (`RECALC=1`) |
| V08 | Calculator specification, adapters, queue worker/job, polling, poison/retries, export/reconciliation | `test_calculator_*`, `test_calc_*`, `test_build_calculator_estimate`; fixture export parses and job failures surface | `CALC_SMOKE=1` real calculator DOM; isolated queue job → actual calculator Excel |
| V09 | Foundry agent, citations, conversation chain, scoped calls, failures, telemetry | `test_engagement_memory`, `test_web_telemetry`, eval SQL 32/32, scenarios 8/8, faults 30/30, adversarial 74/74 | Authenticated model turn and tool round-trip; bounded tokens/time |
| V10 | Engagement create/list/picker, visibility/owner/group, uploads/delete/analysis | `test_access_control`, `test_upload`, `test_pipeline`, `test_system_boundaries`; no cross-engagement reads/writes | Two actual Entra principals; signed-in browser |
| V11 | ZIP export/import/overwrite, malformed archives, archive size/path limits | `test_engagement_memory`, `test_system_boundaries`; round-trip and unauthorized/malformed imports rejected before writes | Isolated export/re-import; never replace customer engagements |
| V12 | Chat UI, prompt cards, create/upload/analyze, reload/new chat, Excel button, mobile | `tests/browser/`; real JS/CSP/fetch, downloads verified, zero console errors | Same journeys behind production EasyAuth |
| V13 | Dashboard data/history/artifact URLs/POE and discovery questionnaire | `test_dashboard`, `test_discovery`, `test_system_boundaries`, browser journeys; correct file bytes/MIME and strict scope | Signed-in downloads of real produced artifacts |
| V14 | All HTTP routes, Function triggers and 17 OpenAPI tools | `test_service_contracts`, `test_web_routers`; registered interfaces match tools; dispatch is exercised separately | Azure Function registration, container revision health; per-tool authenticated calls |
| V15 | Security response headers, traversal, upload content, output claims | `test_web_csp`, `test_access_control`, adversarial suite, live `sec_probe.py`; fail-closed scope, DRAFT/traceability | External pentest; signed data-handling statement |
| V16 | Azure web/API/calc/drawio, SQL, storage, Search, Foundry, registry, telemetry | `scripts/smoke.py`, `scripts/validate_live.py`; correct subscription/RG/location, resource readiness and auth boundaries | Data-plane query/search/render/agent operations require relevant tokens/keys |
| V17 | Deployment hooks, free/prod parameter separation, budget, export/rehydrate, chaos, CI/Python 3.11 | `test_smoke`, `test_infra_tier`, `test_cost_guardrail`, `test_export_all`, `test_teardown_rehydrate`, `test_chaos`, `test_py311_compat`; safe defaults and mitigations | Scratch-environment clean-machine/teardown and induced chaos; OIDC prerequisites |
| V18 | Documentation and evidence | `test_docs`, `test_scorecard`, eval drift; links and examples valid | Usability/comprehension trials with humans |

## Required negative cases / defect acceptance

- Empty or missing artifacts in engagement B must never return default/A data.
- Unknown, malformed, unreadable or denied engagement manifests fail closed on
  every dashboard/questionnaire/attachment route, including the default estate.
- Static artifact routes must not be swallowed by a preceding parameter route.
- ZIP import cannot overwrite another owner's engagement or change an existing
  ACL. New imports bind ownership to the caller; reject malformed/duplicate/
  traversal/oversized expanded content before writing any member.
- A competing engagement creation must return a conflict before any archive
  artifact writes. A failed import may leave an owner-bound partial engagement;
  the response must report failure and completed writes rather than success.
- Blob read/delete failures must not become a confident successful action.
- Browser-created engagements must support upload → analysis state → chat and
  Excel/download actions with actual HTTP calls and zero console/page errors.

## Safe live execution and limits

Install live-probe dependencies from `scripts/requirements.txt` into the project
venv. `--live` includes `validate_data_plane.py`: an authenticated agent-definition
read, Search document count, and a tiny stateless diagram render. The renderer
key is loaded in memory and never written to evidence. These operations do not
prove model inference, SQL RLS, vector retrieval quality, or queue processing.

For a separately opted-in model/SQL check, run
`scripts/validate_tool_roundtrip.py --output <path>` with the project Python.
It attempts a delegated Function token and at most two inventory count queries
(populated default and empty synthetic scope), retaining no content or token.
Missing delegated authentication is BLOCKED; it never disables EasyAuth.

CI runs unit/evals/recalculation and the seven offline browser journeys in
`.github/workflows/evals.yml`. The C53 GitHub workflow itself has not been run
remotely; its browser command was exercised locally.

Pin subscription `f609eb5b-df3e-4fab-9a1b-9a8fea2f157f`, resource group
`rg-landfall`, region `swedencentral`. Record deployed revision and observation
time. Keep the $40–50/month/free-tier constraint. Read-only live probes are the
default. Synthetic mutating tests must use a uniquely named `validation-c53/…`
engagement and leave customer data untouched; record any retained test data.
Never run `azd provision`, `azd down`, SQL schema application, or fault injection
against this populated environment as part of the default suite.

Do not disable EasyAuth or add firewall access merely to make a check pass.
Missing authenticated sessions, unavailable LibreOffice, OIDC, external security
review, and human trials stay explicitly outstanding. A coverage matrix maps
responsibilities; it is not a claim of 100% line coverage or exhaustive testing.
