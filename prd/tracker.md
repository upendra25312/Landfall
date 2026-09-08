# Landfall 5/5 — Work Tracker

Companion to [`prd/landfall-5x5-prd.md`](landfall-5x5-prd.md). Delivery log:
[`prd/pdca-log.md`](pdca-log.md).

**Status key:** `backlog` · `planned` (PDCA Plan written) · `in-progress` · `in-review` ·
`done` · `blocked` · `deferred`
**Owner** = working-group role (see PRD §Working group).

## Progress

| Phase | Items | Done | In review | In progress | Backlog |
|---|---|---|---|---|---|
| 1 — Engine | 36 | 0 | 33 | 1 | 2 |
| 2 — Evidence | 11 | 0 | 0 | 0 | 11 |
| 3 — Sustain | 3 | 0 | 0 | 0 | 3 |

_Last updated: 2026-09-08 (PDCA cycles 1–14; D1 done; E2–E8 + E5.4 + E5.5 in review. Phase 1 engine complete bar E1.7 / E4.3 / full E6.2. Live checks pending: E1.6 ingestion, E8.2 EasyAuth, E5.5 dashboard). Full engine + eval harness + CI gate + security + Excel/Word/PPT exports + Azure Migrate–style assessment dashboard on the Container App. Sample: run-rate ~$119k/mo + ~$77k one-time; effort ~834 PD / ~$650k services. 127 pytest + 32 golden SQL + 8 scenarios + 26 fault cases green._

---

## Phase 1 — Engine

### E1 — Ingestion & Data Quality

| ID | Item | Pri | Status | Owner | Cycle | Acceptance (this item is done when…) |
|---|---|---|---|---|---|---|
| E1.1 | Event Grid Normalize function on `raw/inventory/{name}` — detect, map, normalise, upsert, log | P0 | in-review | SWE | 1 | A blob dropped in `raw/inventory/` populates SQL and writes an `ingest_log` row; no manual mapping. _Unit-verified; DB/trigger check pending E1.6._ |
| E1.2 | Source profiles: Landfall-native, RVTools vInfo, generic CMDB (config-driven) | P0 | in-review | SWE | 1 | Each of the 3 formats is detected and mapped correctly on a sample; adding a 4th is a config edit. _Done — 18 tests pass._ |
| E1.3 | `data_quality_report` — counts, null-rates, dupes, orphans, unmapped, confidence hint → `answers/` MD+JSON | P0 | in-review | SWE + PMO | 1 | For a dump with known defects the report names every defect and nothing spurious. _Done — `broken_servers.csv` + full-sample verified._ |
| E1.4 | Graceful degradation — missing perf → low confidence; unknown file → error, no partial load | P0 | in-review | SWE | 1 | Broken inputs never produce a silent partial load; the log says why. _Done — `unknown.csv` test._ |
| E1.5 | Idempotent re-ingest keyed by source file | P0 | in-review | SWE | 1 | Re-uploading a corrected file replaces only its rows; counts stay correct. _`_dedupe` + `DELETE WHERE source_file` done; DB round-trip pending E1.6._ |
| E1.6 | Wire ingestion into `azd` deploy + end-to-end check on live `rg-landfall` (SQL round-trip, DQ report, live-DB FK migration) | P0 | in-progress | SRE | 2 | `azd up` on a fresh env → drop a file → SQL populated + DQ report, no manual hook run. |
| E1.7 | Column-mapping override file per engagement (`raw/inventory/_mapping.json`) | P1 | backlog | SWE | — | An operator can correct a mis-mapped column without a redeploy. |

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
| E4.3 | Duration model → high-level plan + critical path | P1 | backlog | PMO | — | Plan has durations and a critical path, not just a wave list. |

### E5 — Structured Deliverable & Traceability

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E5.1 | "Assemble estimate" → one structured package, 8 sections | P0 | in-review | PM + SWE | 9 | Package needs editing, not authoring (architect board sign-off). _Done — `src/api/deliverable/assemble.py`; 8 sections + markdown render; full-pipeline test._ |
| E5.2 | Stable IDs + calculation appendix on every figure | P0 | in-review | SWE | 9 | 10 random figures each traceable using only the delivered doc. _Done — `F*` ids + `calculation_appendix` (formula, inputs, assumptions_applied, confidence) per figure._ |
| E5.3 | Machine-tracked assumptions & exclusions register | P0 | in-review | PM | 9 | Register is generated across the run, not merged by hand. _Done — `_Reg`: collects every tool's caveats + standing exclusions, deduped + categorised (A/X/G ids). Sample: 28/6/8._ |
| E5.4 | Client-ready exports — the package as a formatted **Excel workbook, Word document, and PowerPoint deck** | P0 | in-review | SWE + Writer | 13 | An architect can send the .xlsx / .docx / .pptx to a client with light edits; every figure keeps its calculation-appendix reference. _Done — `src/api/deliverable/export.py` + `POST /api/export_estimate`; 6 tests; sample renders 12-sheet xlsx / docx / 11-slide pptx, all re-open._ |
| E5.5 | **Assessment dashboard web app** on the Container App — an Azure Migrate–style interactive dashboard of the estimate, with in-page export to Excel / Word / PPT | P0 | in-review | SWE | 14 | End user opens the engagement URL, sees the dashboard (inventory, cost, landing zone, waves, effort), and downloads any artifact. Professional, MS-assessment-tool visual quality. _Done — `src/web/dashboard.html` + `/dashboard*` routes + `POST /api/publish_estimate`; 7 tests; visual check passed. Live `azd deploy web` pending._ |

### E6 — Firm Config & Effort Model

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E6.1 | Implement `estimation_config.json` (rates, bands, uplifts, overheads) | P0 | in-review | PM + SWE | 3 | Changing the config visibly changes cost + effort output. _File + `cost/config.py` loader done + consumed by `vm_rightsize`; pricing/effort blocks wired in E2.2/E6.2; `ESTIMATION_CONFIG` app setting still to add._ |
| E6.2 | Parametric effort model as a deterministic step | P0 | in-review | PMO | 9 | Client counts + disposition mix → PD / PM / peak FTE / loading curve. _Basic model done — `src/api/deliverable/effort.py` (assessment + LZ + per-disposition execution + testing + cutover + hypercare + PM/gov/contingency → PD + services cost range). Full wave-by-wave resource loading + peak FTE + loading curve still to do._ |
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
| E8.2 | `query_inventory` auth on by default | P0 | in-review | Security | 12 | Anonymous `curl` → 401; agent still works via managed identity. _Bicep `enableFunctionAuth` param + `authsettingsV2` (excludedPaths /runtime), `AGENT_TOOL_AUTH=managed` recipe in DEPLOY. Off by default; needs a live `azd provision` to verify the 401._ |
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
| 2 | E1.6 — deploy wiring + DEPLOY/INSTALL docs (D1 done); live end-to-end check still deferred | [pdca-log.md](pdca-log.md) · partial |
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
