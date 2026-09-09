# Landfall 5/5 — Work Tracker

Companion to [`prd/landfall-5x5-prd.md`](landfall-5x5-prd.md). Delivery log:
[`prd/pdca-log.md`](pdca-log.md).

**Status key:** `backlog` · `planned` (PDCA Plan written) · `in-progress` · `in-review` ·
`done` · `blocked` · `deferred`
**Owner** = working-group role (see PRD §Working group).

## Progress

| Phase | Items | Done | In review | In progress | Backlog |
|---|---|---|---|---|---|
| 1 — Engine | 37 | 8 | 28 | 1 | 0 |
| 2 — Evidence | 12 | 0 | 0 | 0 | 12 |
| 3 — Sustain | 3 | 0 | 0 | 0 | 3 |
| E11 — Engagement Workspaces | 26 | 25 | 0 | 0 | 1 (C26b, sponsor-gated) |

_Last updated: 2026-09-09 (PDCA cycles 1–29). Cycles 19–28 delivered Epic E11 (engagement workspaces) end-to-end — all live. Cycle 29 closed the Phase 1 tail (E4.3 wave duration model + critical path, E6.2-full resource-loading curve + peak FTE, E1.7 per-engagement `_mapping.json`). Phase 1 engine is now complete; remaining road to 5/5 is Phase 2 (Evidence). Earlier history: C15 = first live deploy to `rg-landfall`/swedencentral (E1.1 / E1.5 / E1.6 / E5.4 / E5.5 verified; 3 deploy bugs fixed). C16 = **E8.2** Function App EasyAuth on (anon `/api/*` → 401, agent via MSI, ingestion intact). C17 = **E5.4 `.pptx` rebuilt** as a 12-slide narrative assessment deck (native charts, MEG lifecycle, watermark every slide), deployed + published live. **C18 = Epic E11 engagement tenancy (E11.1–E11.3) live** — per-engagement ADLS layout, SQL Row-Level Security by `SESSION_CONTEXT('engagement_id')` (fail-closed), `engagement` arg on `query_inventory` / assemble / export / publish + agent prompt; sample estate re-loaded as `_default_/_default_`, agent tenant-isolation verified end-to-end. Phase 1 engine complete bar E1.7 / E4.3 / full E6.2. Generation model: `export.py` deterministic Python via `export_estimate`/`publish_estimate` — **the Foundry agent orchestrates, it does not author documents**; the 4 external skills are design references (docx/xlsx) or a Phase-2 side-car (presentation-skill/ppt-master). 150 pytest + 32 golden SQL + 8 scenarios + 30 fault cases green. Known gap: `schema.sql` drops+recreates tables every apply (wipes inventory) — needs additive-only migrations (C23)._

---

## Phase 1 — Engine

### E1 — Ingestion & Data Quality

| ID | Item | Pri | Status | Owner | Cycle | Acceptance (this item is done when…) |
|---|---|---|---|---|---|---|
| E1.1 | Event Grid Normalize function on `raw/inventory/{name}` — detect, map, normalise, upsert, log | P0 | done | SWE | 1,15 | A blob dropped in `raw/inventory/` populates SQL and writes an `ingest_log` row; no manual mapping. _Verified live: `raw/inventory/storage.csv` re-upload → Event Grid → `ingest_blob` → refreshed DQ report; 250/31/484/566/5190 rows in SQL._ |
| E1.2 | Source profiles: Landfall-native, RVTools vInfo, generic CMDB (config-driven) | P0 | in-review | SWE | 1 | Each of the 3 formats is detected and mapped correctly on a sample; adding a 4th is a config edit. _Done — 18 tests pass._ |
| E1.3 | `data_quality_report` — counts, null-rates, dupes, orphans, unmapped, confidence hint → `answers/` MD+JSON | P0 | in-review | SWE + PMO | 1 | For a dump with known defects the report names every defect and nothing spurious. _Done — `broken_servers.csv` + full-sample verified._ |
| E1.4 | Graceful degradation — missing perf → low confidence; unknown file → error, no partial load | P0 | in-review | SWE | 1 | Broken inputs never produce a silent partial load; the log says why. _Done — `unknown.csv` test._ |
| E1.5 | Idempotent re-ingest keyed by source file | P0 | done | SWE | 1,15 | Re-uploading a corrected file replaces only its rows; counts stay correct. _Verified live — `storage.csv` re-ingested (Event Grid + HTTP), row count held at 566; `servers.csv` held at 250._ |
| E1.6 | Wire ingestion into `azd` deploy + end-to-end check on live `rg-landfall` (SQL round-trip, DQ report, live-DB FK migration) | P0 | done | SRE | 2,15 | `azd up` on a fresh env → drop a file → SQL populated + DQ report, no manual hook run. _Verified on `rg-landfall`. Fixed: `apply_sql.py` needed `db_datawriter`; `eventgrid.sh` MSYS path-mangling of the subject filter. Note: `create_agent.py` should move to postdeploy (SERVICE_API_NAME unset at postprovision on first `azd up`)._ |
| E1.7 | Column-mapping override file per engagement (`raw/engagements/<c>/<p>/_mapping.json`) | P1 | in-review | SWE | 29 | An operator can correct a mis-mapped column without a redeploy. _Done — `core.match_mapping()` + `normalize(…, overrides)`; flat or per-file (exact then glob); pins a profile and/or aliases columns; `NormResult.mapping_notes` → `.dq.json` `mapping_applied`. `operating-sop.html` v1.2. 7 tests._ |

### E2 — Deterministic Cost Engine

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E2.1 | `vm_rightsize` — bind on both vcpu & ram; config-driven; p95 sizing; confidence band; low/expected/high range | P0 | in-review | FinOps + SWE | 3 | A 128 GB box never maps to a 32 GB SKU; binding dimension reported. _Done — `src/api/cost/`, 9 tests; -17% fleet vCPU on the sample. Live check with E1.6._ |
| E2.2 | `estimate_compute_cost` — BoM, PAYG + 1yr/3yr RI + AHB, per-env, region + term + price date, low/expected/high | P0 | in-review | FinOps + SWE | 4 | Re-running gives identical figures; independent hand-calc matches within band. _Done — `src/api/cost/compute_cost.py` + `pricing.py`, 8 tests; live retail prices parse; $86k/mo on the sample. Agent end-to-end with E1.6._ |
| E2.3 | Storage cost from the `storage` table (file/DB/object; disjoint from per-VM disk) | P0 | in-review | FinOps | 5 | Disk GB → tier → price; file/DB priced to the right service. _Done — `src/api/cost/storage_cost.py` + `fetch_storagebook`, 10 tests; live rates sanity-clamped; $16.5k/mo (file + PaaS-DB) on the sample, 522 block volumes excluded (in the compute BoM)._ |
| E2.4 | Run-rate extras + one-time migration cost modules | P1 | in-review | FinOps | 6 | Backup/monitoring/egress/support + replication egress/dual-run are line items. _Done — `src/api/cost/run_rate.py`, 9 tests; ~$16.3k/mo extras + ~$77k one-time on the sample. Full run-rate ~$119k/mo._ |
| E2.5 | low/expected/high + top-3 drivers on every cost result | P1 | in-review | FinOps | 9 | Every cost answer carries a range and a sensitivity. _Range ships on every cost tool; top-3 drivers surfaced in `assemble_estimate` (`_top_drivers`)._ |

### E3 — Landing-Zone Design Output

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E3.1 | `design_landing_zone` — ALZ from the portfolio + compliance scope | P0 | in-review | Architect | 7 | Platform engineer says "buildable from this"; PCI spoke + connectivity are data-derived. _Done — `src/api/lz/design.py`, 8 tests; MGs + subs + 9 spokes + IP plan + policy overlay + DR on the sample; feeds `azure-enterprise-infra-planner` for Bicep._ |
| E3.2 | Spoke count / regulated-spoke flag derived from data | P0 | in-review | Architect | 7 | Swapping the portfolio changes the topology. _Done — zone rules + per-scope regulated spoke; `test_swapping_portfolio_changes_topology`._ |
| E3.3 | Criticality → RTO/RPO resiliency tier mapping | P1 | in-review | Architect | 7 | Output carries a resiliency tier per app tier. _Done — `resiliency_tiers` config + per-app tier + DR rollup._ |

### E4 — Wave / Move-Group Engine

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E4.1 | `plan_waves` — dependency graph → move groups → risk-ordered waves | P0 | in-review | Architect + SWE | 8 | Waves reproducible, respect the graph, low-risk-first explained. _Done — `src/api/waves/plan.py`, 8 tests; platform/pilot/regulated waves, stale+commodity edge filter, blocking deps. Sample: 7 waves._ |
| E4.2 | Deterministic disposition scorer (6R + rationale) | P0 | in-review | Architect | 8 | Disposition is rule-derived; the agent explains, never invents. _Done — `src/api/waves/disposition.py`, 6 tests; Rehost 25 / Replatform 3 / Repurchase 2 / Retire 1 on the sample._ |
| E4.3 | Duration model → high-level plan + critical path | P1 | in-review | PMO | 29 | Plan has durations and a critical path, not just a wave list. _Done — `waves/schedule.py` (pure); `plan_waves` attaches a `schedule`: per-wave prep/exec/soak (servers ÷ throughput, floored), programme start/end/total_weeks, `parallel_waves` lanes, blackout-window shifts, ordered `critical_path`. New `schedule` config block + `start_date` param. 9 tests._ |

### E5 — Structured Deliverable & Traceability

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E5.1 | "Assemble estimate" → one structured package, 8 sections | P0 | in-review | PM + SWE | 9 | Package needs editing, not authoring (architect board sign-off). _Done — `src/api/deliverable/assemble.py`; 8 sections + markdown render; full-pipeline test._ |
| E5.2 | Stable IDs + calculation appendix on every figure | P0 | in-review | SWE | 9 | 10 random figures each traceable using only the delivered doc. _Done — `F*` ids + `calculation_appendix` (formula, inputs, assumptions_applied, confidence) per figure._ |
| E5.3 | Machine-tracked assumptions & exclusions register | P0 | in-review | PM | 9 | Register is generated across the run, not merged by hand. _Done — `_Reg`: collects every tool's caveats + standing exclusions, deduped + categorised (A/X/G ids). Sample: 28/6/8._ |
| E5.4 | Client-ready exports — the package as a formatted **Excel workbook, Word document, and PowerPoint deck** | P0 | in-review | SWE + Writer | 13,17 | An architect can send the .xlsx / .docx / .pptx to a client with light edits; every figure keeps its calculation-appendix reference. _Done — `src/api/deliverable/export.py` + `POST /api/export_estimate`; 8 tests. **Cycle 17: `.pptx` rebuilt** — 12-slide narrative "Azure Migration Assessment" (cover → exec summary → CAF/MEG approach → current state → landing zone → 6R → waves → cost → effort → risk register → next steps → traceability), native doughnut/bar charts, colour-coded wave table, hub-spoke diagram, DRAFT watermark + page number + speaker notes every slide. Deployed + published to the live dashboard. `.xlsx`/`.docx` polish is E5.4q._ |
| E5.5 | **Assessment dashboard web app** on the Container App — an Azure Migrate–style interactive dashboard of the estimate, with in-page export to Excel / Word / PPT | P0 | in-review | SWE | 14 | End user opens the engagement URL, sees the dashboard (inventory, cost, landing zone, waves, effort), and downloads any artifact. Professional, MS-assessment-tool visual quality. _Done — `src/web/dashboard.html` + `/dashboard*` routes + `POST /api/publish_estimate`; 7 tests; visual check passed. Verified live: `/dashboard` 200, `/dashboard/data` returns the published package, `/dashboard/download/{xlsx,docx,pptx}` stream with the right mime. Behind Container App EasyAuth (RedirectToLoginPage)._ |
| E5.4q | **Export-quality upgrade** — `.pptx` native objects **done (cycle 17)**; remaining: `.xlsx` derived cells as **formulas not literals** + a headless-LibreOffice recalc-clean CI gate; `.docx` US-Letter DXA + tracked-changes-ready + `accept_changes`. Rules from the Anthropic `docx`/`xlsx` skills, implemented in `export.py` (not run at runtime). Spec: `audits/path-to-5x5.md` §"Deliverable polish" | P1 | in-progress | SWE | 17 | A reviewer changes an input in the .xlsx and the model re-flows; recalc reports 0 errors; architect edits land as Word tracked changes. |
| E5.6 | **Studio-grade client deck** — `presentation-skill` (outline.json → pptxgenjs → `qa_gate.py`) + `ppt-master` (SVG → DrawingML) as a side-car (architect-local or a Node build container), invoked from the dashboard. Spec: PRD E5.6 | P1 | backlog | SWE + Writer | — | The deck a pre-sales lead shows a client is generated from `latest.json`, passes `qa_gate.py` + the E7.4 un-sourced-number guard, carries the DRAFT watermark, every headline number → an `F*` id. Phase 2. |

### E6 — Firm Config & Effort Model

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E6.1 | Implement `estimation_config.json` (rates, bands, uplifts, overheads) | P0 | in-review | PM + SWE | 3 | Changing the config visibly changes cost + effort output. _File + `cost/config.py` loader done + consumed by `vm_rightsize`; pricing/effort blocks wired in E2.2/E6.2; `ESTIMATION_CONFIG` app setting still to add._ |
| E6.2 | Parametric effort model as a deterministic step | P0 | in-review | PMO | 9,29 | Client counts + disposition mix → PD / PM / peak FTE / loading curve. _Done — `effort.py`: parametric PD (assessment + LZ + per-disposition execution + testing + cutover + hypercare + PM/gov/contingency → PD + services-cost range); **C29** adds `resource_loading` — the workstream PD spread across the E4.3 schedule into a month-by-month FTE curve with `peak_fte`/`peak_month`/`avg_fte` (execution weighted by servers/wave, PM/gov/contingency level-loaded). Figures + deck + dashboard sparkline. 5 tests._ |
| E6.3 | Contingency tied to the DQ score | P1 | in-review | PMO | 9 | Poorer data quality → higher contingency, automatically. _Done — `effort.contingency_by_confidence` {High 8, Medium 12, Low 20}; `estimate_effort` picks the rate from the DQ confidence when `contingency_pct` is null._ |

### E7 — Evaluation Harness (build)

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E7.1 | Golden text-to-SQL set (30+) + runner | P0 | in-review | Applied Sci | 10 | `≥95%` exact-match on the sample estate. _Done — `evals/golden_sql.json` (32 cases) + `evals/runner.py`; runs against a SQLite copy of the sample; 32/32. Live model-generation gate is CI._ |
| E7.2 | Full-estimate scenarios (8+) with expected ranges | P0 | in-review | Applied Sci + FinOps | 10 | Portfolio numbers within band; 0 un-sourced numbers; identical on re-run. _Done — `evals/scenarios.json` (8) + `evals/pipeline.py`; every figure in band + traceable + deterministic; 8/8. `evals/SCORECARD.md` committed._ |
| E7.3 | Fault-injection harness | P0 | in-review | Applied Sci | 11 | Each tool fails → agent reports, never invents (100%). _Done — `evals/faults.py`; 26 cases; every tool returns a clean 4xx/5xx error, `assemble_estimate` omits a failed section + records the gap._ |
| E7.4 | Output guard — reject un-sourced numeric claims | P0 | in-review | Applied Sci | 11 | A planted un-sourced number is blocked in test. _Done — `evals/output_guard.py` `check_message`; run against every scenario's `summary_markdown`; flags planted `$2.4M` / `1,200 PD` / bare `63%`._ |
| E7.5 | CI gate — version + scorecard on every `create_agent.py` change | P0 | in-review | SRE | 11 | A seeded regression fails the build. _Done — `.github/workflows/evals.yml`: `pytest` + `evals/runner.py` on every push/PR; stale `SCORECARD.md` fails. First live run pending a push._ |

### E8 — Security & Isolation (Phase 1 part)

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E8.1 | One deployment per engagement + reliable fast `azd up`/`down` | P0 | in-review | SRE | 12 | Two engagements never share a datastore; clean `azd up` in CI, no manual steps. _`resourceToken` makes every resource env-unique; DEPLOY.md isolation note added. Clean-machine CI is E9.2 (Phase 2)._ |
| E8.2 | Function App auth on by default | P0 | done | Security | 12,16 | Anonymous `curl` → 401; agent still works via managed identity. _**Verified live on `rg-landfall`.** App reg `landfall-func-tmglwfatwcsa2` (`920abc3e…`, audiences `<guid>` + `api://<guid>`); `authsettingsV2` requireAuthentication + Return401, `excludedPaths` = `/runtime/webhooks/blobs` + `/runtime/webhooks/durabletask` (EasyAuth prefix-matches — `/runtime` alone is NOT enough). All 12 OpenAPI tools switched to `OpenApiManagedAuthDetails`. Anon → 401 on every `/api/*`; agent calls `query_inventory` + `estimate_compute_cost` via MSI; Event Grid ingestion still works (250 rows). Principal allow-list (`functionAuthAllowedClientIds`) wired but not yet set — Stage 2._ |
| E8.3 | Allow-list SQL parse + statement timeout | P0 | in-review | Applied Sci + Security | 12 | `WAITFOR`, `sys.*`, cartesian joins rejected or bounded. _Done — `src/api/sqlguard.py` (single SELECT/WITH, 6-table allow-list, comment strip, keyword deny) + `QUERY_TIMEOUT_S` / `cur.timeout`; 20 tests._ |
| E8.4 | Keep client SQL text out of logs | P0 | in-review | Security | 12 | Logs contain a hash/template, never the question or SQL. _Done — `sqlguard.signature()` (sha256[:12] + tables + shape); every `query_inventory` log call scrubbed._ |

### E9 — Operability (Phase 1 part)

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E9.1 | Self-contained hooks — no `azd`-on-PATH, SQL grant via Python | P0 | in-review | SRE | 12 | `azd up` succeeds with `azd` absent from the hook shell. _Done — `scripts/apply_sql.py` (mssql-python + Entra token) replaces the `sqlcmd` block in `postprovision.{sh,ps1}`; `sqlcmd` dropped from prereqs._ |

## Phase 2 — Evidence

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E8.5 | Private-endpoint parameter set; drop all-Azure SQL firewall rule | P1 | backlog | Security | — | Hardened deploy has no public data-plane surface. |
| E8.6 | Bind chat threads to the authenticated principal | P1 | backlog | SWE | — | A leaked thread id cannot resume another user's conversation. |
| E8.7 | Signed data-handling statement | P0 | backlog | Security | — | Reviewed + signed by a security officer. |
| E9.2 | CI: `azd up → smoke → azd down` on Linux + Windows | P1 | backlog | SRE | — | Green on every PR, both OSes. |
| E9.3 | `--tier prod` parameter set + cost delta doc | P1 | backlog | SRE | — | One switch moves off Free tiers; delta documented. |
| E9.4 | Answer-quality observability (traces + dashboard + alerts) | P1 | backlog | SRE | — | An operator can see a bad answer; tool error rate alerts. |
| E9.5 | Export-before-teardown step | P2 | backlog | SRE | — | Close-out dumps tables + docs to a retained location first. |
| E10.1 | `evidence/backtest/` — 3 estates × 3 methods + variance analysis | P0 | backlog | FinOps + Architect | — | Portfolio totals within ±15% across methods; variances explained. |
| E10.2 | `evidence/broken-dumps/` corpus + expected DQ reports | P0 | backlog | SWE | — | 6+ damaged inputs; each handled per E1.4. |
| E10.3 | `evidence/evals/` scorecard + history | P0 | backlog | Applied Sci | — | Latest scorecard published; history retained. |
| E10.4 | `evidence/{pentest,trials,chaos}/` reports | P0/P1 | backlog | Security + SRE + Writer | — | Pen test passes; usability + comprehension trials meet bars; chaos drill logged. |
| E10.6 | `evidence/SCORECARD.md` | P0 | backlog | PM | — | Rubric + current score + link to every artifact. |

## Epic E11 — Engagement Workspaces (multi-client, dashboard-driven)

Full plan: [`engagement-workspaces-prd.md`](engagement-workspaces-prd.md). One deployment,
many engagements, isolated by an `<customer>/<project>` key. The Foundry agent orchestrates;
`export.py` (deterministic Python) authors the files.

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E11.1 | Engagement model + provisioning (slug rules, `_engagement.json`, `POST/GET /api/engagements`) | P0 | done | App+Data | 18 | Creating "Contoso / DC-Exit" makes the folder skeleton + returns the id; duplicate → `-2`. _`src/api/engagement.py` + `engagements.py` blueprint; 22 tests; live on `func-tmglwfatwcsa2`._ |
| E11.2 | Per-engagement ADLS layout (`raw/engagements/<c>/<p>/…`, `answers/engagements/…`); Event Grid subject filter + blob-trigger path | P0 | done | Data Eng | 18 | A file under one engagement never triggers ingestion for another. _Blob trigger `raw/engagements/{customer}/{project}/inventory/{name}`; `eventgrid.{sh,ps1}` subject → `/blobs/engagements/`; DQ reports under `answers/engagements/<c>/<p>/_ingest/`. `landfall-inventory` subscription recreated live 2026-09-08._ |
| E11.3 | SQL tenancy — `engagement_id` on all 6 tables + **Row-Level Security** (filter predicate + `SECURITY POLICY`, `sp_set_session_context`), composite PKs, loader keying | P0 | done | Data Eng | 18 | Live: no context → 0 rows; `acme/other` → 0; `_default_/_default_` → 250 servers; agent isolation verified end-to-end. _`schema.sql` + `engagement_sql.py`; `loader.load(table, rows, engagement)`._ |
| E11.4 | Ingestion scoped by engagement — `/api/ingest` takes `engagement`; blob trigger derives it from the path; a `run_engagement` Function ingests a whole folder | P0 | partial | Data Eng | 18,19 | `/api/ingest` done (C18); `run_engagement` (bulk) = C19 |
| E11.5 | `engagement` arg on the data/deliverable OpenAPI tools + agent system prompt; `query_inventory` sets the RLS context | P0 | partial | Data & AI | 18,19 | `query_inventory` / `assemble_estimate` / `export_estimate` / `publish_estimate` + prompt done (C18, `_default_` fallback); tighten to required + audit in C19 |
| E11.6 | Dashboard — engagements home, "New engagement" form, upload panel, "Start analysis" / "Produce estimate" | P0 | planned | App Eng | 20 | A no-CLI pre-sales user creates an engagement, uploads RVTools + CMDB, runs analysis, sees a DQ summary — one session |
| E11.7 | Dashboard — engagement-scoped embedded chat + configurable prompt cards (`prompt_cards.json`) | P0 | planned | App Eng | 21 | "Full estimate" card produces + publishes for the open engagement only |
| E11.8 | `publish_estimate` + dashboard use the engagement path; `history/<ts>/` snapshots + a version picker | P1 | planned | SWE | 21 | Re-publish keeps the prior version; dashboard shows any snapshot |
| E11.9 | Studio-deck container (`ca-deckgen`) — `presentation-skill` + `ppt-master` as an OpenAPI tool; "Studio deck" card | P1 | planned | App+AI | 22 | The agent calls it; a `qa_gate`-passing `studio.pptx` lands in the engagement folder |
| E11.10 | Access control — `visibility` on `_engagement.json`, list filtering, run/publish audit trail | P1 | planned | Security | 23 | A user sees only their own + group-shared engagements; every run attributable |
| E11.11 | Migration + back-compat — current single-tenant layout → `_default_/_default_`; one-release shim | P1 | planned | Data Eng | 23 | Existing deploy keeps working through the transition |
| E11.12 | E5.4q — `.xlsx` formulas-not-literals + LibreOffice-recalc **CI gate**; `.docx` US-Letter DXA + tracked-changes-ready + `accept_changes` | P1 | in-progress | SWE | 17,22 | Change a workbook input → model re-flows; recalc 0 errors; architect edits are tracked changes |
| E11.13 | Evals — per-engagement isolation tests (two synthetic estates, assert no bleed) + a `run_engagement` scenario | P0 | planned | SRE | 19 | A row-leak regression fails CI |
| E11.14 | **Ask & export to Excel** — `POST /api/answer_to_xlsx` + a "Download as Excel" button on chat answers with tabular tool output | P0 | planned | SWE + App Eng | 21 | Architect asks a question, gets the answer, downloads a workbook with the rows + the SQL + engagement + DRAFT note |

## Phase 3 — Sustain

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| S1 | Full eval + back-test suite in CI per agent version | P1 | backlog | SRE | — | Every agent change re-runs the suite; regressions block. |
| S2 | Quarterly price / SKU / CAF re-benchmark | P1 | backlog | FinOps | — | A recurring job + a dated report. |
| S3 | Reference estates refreshed yearly; broken-dump corpus grows with real dumps | P2 | backlog | PM | — | Corpus and estates carry a "last reviewed" date. |

## Docs & method (not scored, but required)

| ID | Item | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|
| D1 | Fix SOP / README / DEPLOY / INSTALL to match what is built | done | Writer | 1–2 | README, operating-sop, DEPLOY.md, INSTALL.md all describe the real ingestion flow + `landfall-inventory` subscription. `estimation_config.json` claim still to remove (do in E6.1). |
| D2 | "How Landfall actually works" page + worked example | backlog | Writer | — | 3 new consultants pass the 60-minute comprehension test. |

## PDCA cycle index

| Cycle | Scope | Log |
|---|---|---|
| 1 | E1.1–E1.5 — ingestion & data-quality core (normalize + profiles + DQ + loader + tests); D1 partial | [pdca-log.md](pdca-log.md) · **done** |
| 1a | sample-estate 30-day performance + flow data (user request) — `performance.csv`, servers/deps rollups, `landfall_performance` profile, schema `dbo.performance` | [pdca-log.md](pdca-log.md) · **done** |
| 2 | E1.6 — deploy wiring + DEPLOY/INSTALL docs (D1 done); live end-to-end check still deferred | [pdca-log.md](pdca-log.md) · superseded by 15 |
| 3 | E2.1 deterministic `vm_rightsize` + E6.1 `estimation_config.json` (partial); closes audit FIN-1/FIN-2 | [pdca-log.md](pdca-log.md) · **done** |
| 4 | E2.2 `estimate_compute_cost` (compute BoM + PAYG/RI/AHB + per-VM disk, low/expected/high); closes audit FIN-3 | [pdca-log.md](pdca-log.md) · **done** |
| 5 | E2.3 — `estimate_storage_cost` over the `storage` table (file / DB / object); block volumes stay in the compute BoM | [pdca-log.md](pdca-log.md) · **done** |
| 6 | E2.4 — run-rate extras (backup / egress / monitoring / support) + one-time migration cost | [pdca-log.md](pdca-log.md) · **done** |
| 7 | E3.1 / E3.2 / E3.3 — `design_landing_zone` (CAF ALZ topology, spoke count, regulated-spoke flag, resiliency tiers — all portfolio-derived) | [pdca-log.md](pdca-log.md) · **done** |
| 8 | E4.1 / E4.2 — `plan_waves` (dependency graph → move-groups → risk-ordered waves) + deterministic 6R disposition scorer | [pdca-log.md](pdca-log.md) · **done** |
| 9 | E5.1 / E5.2 / E5.3 — `assemble_estimate`: one structured deliverable + calculation appendix + assumptions/exclusions register (E2.5 + E6.2-basic folded in) | [pdca-log.md](pdca-log.md) · **done** |
| 10 | E7.1 / E7.2 — eval harness: 32 golden text-to-SQL cases + 8 full-estimate scenarios + `SCORECARD.md` | [pdca-log.md](pdca-log.md) · **done** |
| 11 | E7.3 / E7.4 / E7.5 — fault-injection harness + un-sourced-number output guard + CI scorecard gate | [pdca-log.md](pdca-log.md) · **done** |
| 12 | E8.3 / E8.4 / E9.1 done + E8.1 / E8.2 in-review — SQL allow-list guard + timeout, no SQL in logs, Python schema/grant (no sqlcmd), EasyAuth Bicep param, isolation note | [pdca-log.md](pdca-log.md) · **done** |
| 13 | E5.4 — client-ready exports: assembled package → Excel / Word / PowerPoint | [pdca-log.md](pdca-log.md) · **done** |
| 14 | E5.5 — assessment dashboard web app on the Container App (Azure Migrate–style) with in-page export | [pdca-log.md](pdca-log.md) · **done** |
| 15 | First live deploy to `rg-landfall` (cycles 5–14) + verification pass — E1.1 / E1.5 / E1.6 / E5.4 / E5.5 verified live; fixed `apply_sql.py` (db_datawriter), `eventgrid.sh` (MSYS path mangling), text-to-SQL enum hints; agent v4 (12 OpenAPI tools) | [pdca-log.md](pdca-log.md) · **done** |
| 16 | E8.2 — Function App EasyAuth on live: app reg + `authsettingsV2` (Return401, `excludedPaths` blobs/durabletask), all 12 OpenAPI tools → managed-identity auth, `functionAuthClientId`/`functionAuthAllowedClientIds` Bicep params, DEPLOY.md recipe rewritten. Verified: anon → 401, agent works via MSI, ingestion intact | [pdca-log.md](pdca-log.md) · **done** |
| — | Scope add (sponsor): E5.4q export-quality bar (`docx`/`xlsx` skills, implemented in `export.py`) → `audits/path-to-5x5.md` §"Deliverable polish"; E5.6 studio deck (`presentation-skill` + `ppt-master`, side-car) → PRD E5.6; `Azure/migration` MEG as the deck narrative reference. Foundry agent is NOT in the generation path. | doc-only | — |
| 17 | E5.4 `.pptx` rebuilt as a 12-slide narrative "Azure Migration Assessment" deck — native doughnut/bar charts, colour-coded wave table, hub-spoke diagram, CAF/MEG lifecycle, DRAFT watermark + page number + speaker notes every slide. Deployed + published to the live dashboard | [pdca-log.md](pdca-log.md) · **done** |
| 18 | **E11 C18** — engagement tenancy foundation: `engagement.py` + `engagement_sql.py`, `schema.sql` `engagement_id` + Row-Level Security on all 6 tables, `loader.load(…, engagement)`, blob trigger `raw/engagements/{c}/{p}/inventory/`, `engagements.py` blueprint (create/list), `engagement` arg on `query_inventory`/`assemble`/`export`/`publish` + agent prompt, dashboard `?e=`. 150 pytest. **Not deployed yet** | [pdca-log.md](pdca-log.md) · **done (code)** |
| 19–28 | **Epic E11 — Engagement Workspaces** (C19 run_engagement · C20/20b analysis + discovery questionnaire · C21 history/answer-xlsx · C22 xlsx-model recalc gate · C23 access control + migration · C25/25b upload panel + calc-adapter accuracy · C26 conversation memory + zip export · C27/27b landing-zone diagram (.drawio/.svg + ca-drawio PNG) · C28 ALZ/AI-LZ checklist conformance). All deployed + live-verified. C26b (chat redesign) sponsor-gated. | [pdca-log.md](pdca-log.md) · **done** |
| 29 | **Phase 1 tail** — E4.3 wave duration model (`schedule.py` → dated waves + critical path), E6.2-full resource loading (month-by-month FTE curve + peak FTE), E1.7 per-engagement `_mapping.json` column override. 356 pytest, evals green. | [pdca-log.md](pdca-log.md) · **done** |
