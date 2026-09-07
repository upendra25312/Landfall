# Landfall 5/5 — Work Tracker

Companion to [`prd/landfall-5x5-prd.md`](landfall-5x5-prd.md). Delivery log:
[`prd/pdca-log.md`](pdca-log.md).

**Status key:** `backlog` · `planned` (PDCA Plan written) · `in-progress` · `in-review` ·
`done` · `blocked` · `deferred`
**Owner** = working-group role (see PRD §Working group).

## Progress

| Phase | Items | Done | In review | In progress | Backlog |
|---|---|---|---|---|---|
| 1 — Engine | 24 | 0 | 5 | 1 | 18 |
| 2 — Evidence | 11 | 0 | 0 | 0 | 11 |
| 3 — Sustain | 3 | 0 | 0 | 0 | 3 |

_Last updated: 2026-09-07 (PDCA cycle 1 complete — E1.1–E1.5 in review, deploy check pending E1.6)._

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
| E2.1 | `rightsize` — bind on `max(vcpu, ram)`; config haircut; confidence band | P0 | backlog | FinOps + SWE | 3 | A 128 GB box never maps to a 32 GB SKU; the binding dimension is reported. |
| E2.2 | `estimate_compute_cost` — BoM, PAYG + 1yr/3yr RI + AHB, region + term + price date | P0 | backlog | FinOps + SWE | 4 | Re-running gives identical figures; independent hand-calc matches within band. |
| E2.3 | Storage cost from the `storage` table | P0 | backlog | FinOps | 5 | Disk GB → tier → price; file/DB priced to the right service. |
| E2.4 | Run-rate extras + one-time migration cost modules | P1 | backlog | FinOps | — | Backup/monitoring/egress/support + replication egress/dual-run are line items. |
| E2.5 | low/expected/high + top-3 drivers on every cost result | P1 | backlog | FinOps | — | Every cost answer carries a range and a sensitivity. |

### E3 — Landing-Zone Design Output

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E3.1 | `design_landing_zone` — ALZ from the portfolio + compliance scope | P0 | backlog | Architect | 6 | Platform engineer says "buildable from this"; PCI spoke + connectivity are data-derived. |
| E3.2 | Spoke count / regulated-spoke flag derived from data | P0 | backlog | Architect | 6 | Swapping the portfolio changes the topology. |
| E3.3 | Criticality → RTO/RPO resiliency tier mapping | P1 | backlog | Architect | — | Output carries a resiliency tier per app tier. |

### E4 — Wave / Move-Group Engine

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E4.1 | `plan_waves` — dependency graph → move groups → risk-ordered waves | P0 | backlog | Architect + SWE | 7 | Waves reproducible, respect the graph, low-risk-first explained. |
| E4.2 | Deterministic disposition scorer (6R + rationale) | P0 | backlog | Architect | 7 | Disposition is rule-derived; the agent explains, never invents. |
| E4.3 | Duration model → high-level plan + critical path | P1 | backlog | PMO | — | Plan has durations and a critical path, not just a wave list. |

### E5 — Structured Deliverable & Traceability

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E5.1 | "Assemble estimate" → one structured package, 8 sections | P0 | backlog | PM + SWE | 8 | Package needs editing, not authoring (architect board sign-off). |
| E5.2 | Stable IDs + calculation appendix on every figure | P0 | backlog | SWE | 8 | 10 random figures each traceable using only the delivered doc. |
| E5.3 | Machine-tracked assumptions & exclusions register | P0 | backlog | PM | 8 | Register is generated across the run, not merged by hand. |

### E6 — Firm Config & Effort Model

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E6.1 | Implement `estimation_config.json` (rates, bands, uplifts, overheads) | P0 | backlog | PM + SWE | 9 | Changing the config visibly changes cost + effort output. |
| E6.2 | Parametric effort model as a deterministic step | P0 | backlog | PMO | 9 | Client counts + disposition mix → PD / PM / peak FTE / loading curve. |
| E6.3 | Contingency tied to the DQ score | P1 | backlog | PMO | — | Poorer data quality → higher contingency, automatically. |

### E7 — Evaluation Harness (build)

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E7.1 | Golden text-to-SQL set (30+) + runner | P0 | backlog | Applied Sci | 10 | `≥95%` exact-match on the sample estate. |
| E7.2 | Full-estimate scenarios (8+) with expected ranges | P0 | backlog | Applied Sci + FinOps | 10 | Portfolio numbers within band; 0 un-sourced numbers; identical on re-run. |
| E7.3 | Fault-injection harness | P0 | backlog | Applied Sci | 11 | Each tool fails → agent reports, never invents (100%). |
| E7.4 | Output guard — reject un-sourced numeric claims | P0 | backlog | Applied Sci | 11 | A planted un-sourced number is blocked in test. |
| E7.5 | CI gate — version + scorecard on every `create_agent.py` change | P0 | backlog | SRE | 11 | A seeded regression fails the build. |

### E8 — Security & Isolation (Phase 1 part)

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E8.1 | One deployment per engagement + reliable fast `azd up`/`down` | P0 | backlog | SRE | 12 | Two engagements never share a datastore; clean `azd up` in CI, no manual steps. |
| E8.2 | `query_inventory` auth on by default | P0 | backlog | Security | 12 | Anonymous `curl` → 401; agent still works via managed identity. |
| E8.3 | Allow-list SQL parse + statement timeout | P0 | backlog | Applied Sci + Security | 12 | `WAITFOR`, `sys.*`, cartesian joins rejected or bounded. |
| E8.4 | Keep client SQL text out of logs | P0 | backlog | Security | 12 | Logs contain a hash/template, never the question or SQL. |

### E9 — Operability (Phase 1 part)

| ID | Item | Pri | Status | Owner | Cycle | Acceptance |
|---|---|---|---|---|---|---|
| E9.1 | Self-contained hooks — no `azd`-on-PATH, SQL grant via Python | P0 | backlog | SRE | 12 | `azd up` succeeds with `azd` absent from the hook shell. |

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
| 2 | E1.6 — wire ingestion into `azd` deploy, end-to-end check on live `rg-landfall`, finish D1 (DEPLOY/INSTALL) | planned |
