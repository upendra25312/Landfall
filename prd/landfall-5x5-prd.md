# PRD — Landfall to 5/5

**Status:** active · **Owner:** Landfall Working Group · **Created:** 2026-09-07
**Basis:** [`audits/path-to-5x5.md`](../audits/path-to-5x5.md) ·
[`audits/2026-09-07-production-readiness-review.md`](../audits/2026-09-07-production-readiness-review.md)
**Tracker:** [`prd/tracker.md`](tracker.md) · **Delivery log:** [`prd/pdca-log.md`](pdca-log.md)

## Working group (virtual Microsoft expert team)

| Role | Remit in this PRD |
|---|---|
| **Principal PM — Azure Migrate & Modernization** | Owns the PRD, scope, and the pre-sales customer voice. Arbiter of "is this a real problem solver." |
| **Principal SWE — App Platform / Durable Functions** | Ingestion pipeline, tool functions, deployment reliability. |
| **Principal Architect — Cloud Adoption Framework / Landing Zones** | Landing-zone design output, wave/move-group methodology. |
| **Principal Applied Scientist — Foundry / Agents** | Agent design, tool orchestration, eval harness, determinism guardrails. |
| **Senior FinOps Specialist** | Cost engine correctness, RI/AHB/storage modelling, back-test method. |
| **Security & Compliance Architect** | Data-handling statement, tenant isolation, least privilege, audit. |
| **SRE — Reliability** | `azd` deploy in CI, observability, chaos drills, tiering. |
| **Delivery Lead / PMO** | Parametric effort model, resource loading, benchmark calibration. |
| **Staff Technical Writer** | Docs that match what is built; the one-hour comprehension bar. |

The group operates in **PDCA cycles** (see §7). Each cycle is one tracked slice of one
epic, with a written Plan, an implementation, a Check against acceptance criteria, and an
Act note that updates this PRD and the tracker.

---

## 1. Problem

Enterprises with a hard compliance or change-freeze position **cannot run discovery
tooling** — no Azure Migrate appliance, no third-party collectors (DR Migrate, Movere), no
discovery SaaS — inside their on-premises estate. They **can** export their own inventory
(RVTools, CMDB, application portfolio, architecture docs) into an Azure Data Lake that the
partner controls.

A partner pre-sales team needs to turn that paper inventory into a **defensible proposal**:
current-state analysis, target Azure **landing-zone design**, **migration approach** per
application, a **high-level migration plan**, the **Azure run-cost** estimate, the
**one-time migration effort and cost**, and the **evidence pack a Statement of Work can be
built on and defended** in commercial negotiation.

Landfall today (audit score ~1.8/5) is a prototype: the agent surface and pre-sales method
are sound, but the ingestion pipeline the premise depends on is unbuilt, the cost engine is
in-context LLM arithmetic, there is no landing-zone design output, and every result lands
as chat transcript that a human re-keys.

## 2. Goals / non-goals

### Goals
- **G1** — Ingest a real, messy client dump from the data lake with no manual mapping, and
  report data quality back to the pre-sales team.
- **G2** — Produce every proposal section (current state, cost, landing zone, disposition,
  waves, effort) **generated from the client's data**, not templated.
- **G3** — Every number is **deterministic and traceable**: raw rows → transformation →
  assumptions → result, exportable as a calculation appendix.
- **G4** — Usable by a pre-sales consultant with no engineer, in under a day, per
  engagement.
- **G5** — A client CISO can approve the data-handling posture; engagements are provably
  isolated.
- **G6** — The 5/5 claim is backed by an **evidence pack** (back-tests, broken-dump corpus,
  pen test, eval suite, trials) versioned with the agent.

### Non-goals
- Replacing discovery — Landfall output is explicitly a **±15% pre-discovery model**, not a
  bid.
- On-prem anything. No agents, collectors, or SaaS in the client estate.
- Running the migration. Landfall estimates and proposes; it does not execute.
- A multi-tenant SaaS. The delivery model is one deployment per engagement.

## 3. Success metric

**The rubric in `audits/path-to-5x5.md` reads 5/5 on every dimension, each backed by a
named artifact in the evidence pack.** Dimension acceptance bars (condensed):

| Dimension | 5/5 bar |
|---|---|
| Correctness | Portfolio totals agree with 2 independent methods within ±15%; variances explained; re-run identical |
| Defensibility | Any figure → source rows + transform + assumptions + confidence, in the delivered doc |
| Completeness | All 8 proposal sections present and data-driven; architect board signs "edit, not author" |
| Robustness | Broken-dump corpus (6+): each yields a valid estimate + a DQ report naming every defect |
| Usability | 3 pre-sales people, 3 estates, no engineer, median < 1 day, all accepted |
| Understandability | 3 new consultants, 60 min with docs, then succeed at a real task unaided |
| Operability | CI `azd up → smoke → azd down` on Linux + Windows every PR; chaos drill degrades cleanly |
| Security | External pen test passes; isolation test passes; data-handling statement signed |
| Reliability | Eval suite CI gate: ≥95% text-to-SQL, 0 un-sourced numbers, byte-identical re-runs, 100% fail-loud |

## 4. Users & jobs

| User | Job |
|---|---|
| **Pre-sales solution lead** | "Give me a defensible cost + effort + plan I can put in a SoW and hold in negotiation." |
| **Migration architect (reviewer)** | "Show me the assumptions and the working so I can own the numbers." |
| **Landfall operator** | "Stand up an instance per engagement, load the dump, hand over the URL, tear down." |
| **Client CISO** | "Tell me where my data goes and how it's deleted before I approve the upload." |

## 5. Requirements by epic

Priorities carry over from the audit (P0 = before any real engagement, P1 = before the
2nd, P2 = hardening). Full acceptance detail lives per-item in the tracker.

### E1 — Ingestion & Data Quality  *(P0 · audit P0-1, DE-1..6, OPS-5)*
- **E1.1** Event Grid–triggered Normalize function on `raw/inventory/{name}`: detect file
  type by header signature + filename, map columns to the schema, normalise units, upsert
  to SQL keyed by source file, write an ingest log.
- **E1.2** Source profiles for: Landfall-native CSVs, RVTools (vInfo), generic CMDB export.
  Adding a profile is config, not code surgery.
- **E1.3** `data_quality_report`: per-table row counts, null-rate on estimate-critical
  columns, duplicates, orphans, unmapped columns, and a plain-English "what's missing to
  firm up the estimate" section with an overall confidence hint. Written to `answers/` as
  Markdown + JSON.
- **E1.4** Graceful degradation: missing perf data → low-confidence path, not a failure;
  unrecognised file → clear error in the log, no partial load.
- **E1.5** Idempotent re-ingest: re-uploading a corrected file replaces its rows only.

### E2 — Deterministic Cost Engine  *(P0 · audit P0-2, FIN-1..7)*
- **E2.1** `rightsize` tool: size against `max(vcpu_need, ram_need)`; report which bound;
  no-perf-data haircut is a documented config value, not a constant; wide confidence band.
- **E2.2** `estimate_compute_cost` tool: rightsize output + retail prices → monthly PAYG,
  1yr/3yr RI, AHB variants; line-item BoM with region + term + price date.
- **E2.3** Storage cost from the `storage` table → managed-disk tier / Files / ANF / PaaS.
- **E2.4** Run-rate extras (backup, monitoring, egress, support) and one-time migration
  cost (replication egress, dual-run overlap, tooling) as parametric modules.
- **E2.5** Every cost result returns low / expected / high and the top 3 drivers.

### E3 — Landing-Zone Design Output  *(P0 · audit P0-3, LZ-1..3)*
- **E3.1** `design_landing_zone` tool (or wired `azure-enterprise-infra-planner`): emits a
  client-specific ALZ — MG hierarchy, subscription topology, hub-spoke + IP plan, policy
  set, identity, connectivity, DR region, regulated spoke — parameterised by the app
  portfolio and `compliance_scope`.
- **E3.2** Spoke count and regulated-spoke flag derived from the data, not a template.
- **E3.3** Criticality → resiliency-tier (RTO/RPO) mapping in the output.

### E4 — Wave / Move-Group Engine  *(P0 · audit P0-4, MA-1..5)*
- **E4.1** `plan_waves` tool: full dependency graph → affinity/move groups → risk-ordered
  waves with entry/exit criteria and blocking dependencies.
- **E4.2** Deterministic disposition scorer: inputs (OS EOL, stack, criticality,
  internet-facing, db engine) → candidate 6R + rationale; the agent explains, never invents.
- **E4.3** Duration model: servers/wave ÷ throughput → a high-level plan with a critical
  path.

### E5 — Structured Deliverable & Traceability  *(P0 · audit P0-5, PS-2..4)*
- **E5.1** "Assemble estimate" flow: one structured package (JSON + rendered) with all 8
  sections.
- **E5.2** Stable ID + calculation appendix on every figure: source tool, query/filter,
  input row count, assumptions applied, formula, result, confidence.
- **E5.3** Machine-tracked assumptions & exclusions register across the whole run.
- **E5.4** Client-ready exports: the assembled package rendered as a formatted **Excel
  workbook** (a sheet per section + a BoM + the calculation appendix + the register),
  a **Word document** (the proposal-ready narrative), and a **PowerPoint deck** (the
  executive readout). Every figure keeps its `F*` reference so the appendix still ties
  out. `DRAFT — architect review` watermark on all three.
- **E5.5** **Assessment dashboard web app** on the existing Container App: an
  interactive, Azure Migrate–style dashboard of the estimate (current-state summary,
  right-sizing + cost, landing zone, disposition + waves, effort), with in-page
  **download** of the E5.4 artifacts. Visual quality on par with Microsoft's own
  assessment-tool pages; one engagement = one URL; respects the same auth as the chat UI.

### E6 — Firm Config & Effort Model  *(P0 · audit P0-6, PS-1/5, PM-1..4)*
- **E6.1** `estimation_config.json` implemented: rates, S/M/L/XL bands, RI term, non-prod /
  DR uplift %, PM / testing / cutover overhead %. Loaded by the cost + effort tools.
- **E6.2** Parametric effort model as a tool: client counts + disposition mix → PD +
  person-months + peak FTE + resource-loading curve. Authoritative over the agent's prose.
- **E6.3** Contingency tied to the E1.3 data-quality score, not a fixed %.

### E7 — Evaluation Harness  *(P0 · audit P0-7, AI-1..8)*
- **E7.1** Golden text-to-SQL set (30+) with known results; ≥95% exact-match gate.
- **E7.2** Full-estimate scenarios (8+) with expected ranges; portfolio numbers within
  band; 0 un-sourced numbers; identical on re-run.
- **E7.3** Fault-injection: each tool fails in turn → agent reports, never invents (100%).
- **E7.4** Output guard: reject any agent message with a numeric claim lacking a tool
  citation.
- **E7.5** CI: every `create_agent.py` change records version + full scorecard; regression
  fails the build.

### E8 — Security & Isolation  *(P0/P1 · audit SEC-1..8, P0-8/9)*
- **E8.1** One deployment per engagement; `azd up`/`down` reliable and fast.
- **E8.2** `query_inventory` auth on by default (EasyAuth + managed identity).
- **E8.3** Allow-list SQL parse (single SELECT, known tables only) + statement timeout.
- **E8.4** Client SQL text kept out of logs (hash/template).
- **E8.5** Private-endpoint parameter set; drop the all-Azure SQL firewall rule.
- **E8.6** Chat threads bound to the authenticated principal.
- **E8.7** Published, signable data-handling statement (residency, encryption, retention,
  deletion + evidence, sub-processors).

### E9 — Operability  *(P1 · audit OPS-1..6)*
- **E9.1** Self-contained hooks; no `azd`-on-PATH dependency; SQL grant via Python.
- **E9.2** CI: clean-machine `azd up → smoke → azd down --purge` on Linux + Windows.
- **E9.3** `--tier prod` parameter set (SQL capacity, Container App min-replica 1, Search
  Basic) with a documented cost delta.
- **E9.4** Answer-quality observability: structured per-tool-call traces + dashboard +
  error alerts.
- **E9.5** Export-before-teardown step.

### E10 — Evidence Pack  *(P0/P2 · audit "evidence pack")*
- **E10.1** `evidence/backtest/` — 3 reference estates × 3 independent estimates + variance
  analysis + tolerance statement.
- **E10.2** `evidence/broken-dumps/` — the damaged-input corpus + expected DQ reports.
- **E10.3** `evidence/evals/` — golden sets + latest scorecard + history.
- **E10.4** `evidence/pentest/`, `evidence/trials/`, `evidence/chaos/` — reports.
- **E10.5** `evidence/data-handling-statement.md` — signed.
- **E10.6** `evidence/SCORECARD.md` — the rubric, current score, link to each artifact.

## 6. Release plan

| Phase | Epics | Exit |
|---|---|---|
| **Phase 1 — Engine** (~10–12 wk) | E1, E2, E3, E4, E5, E6, E7 (build), E8.1–8.4, E9.1 | A pre-sales lead produces a full data-driven package for a reference estate with architect oversight; eval suite gates agent changes. Score ~3.5–4. |
| **Phase 2 — Evidence** (~5–6 wk) | E7 (bar), E8.5–8.7, E9.2–9.5, E10 | Every dimension's acceptance bar met and evidenced. Score 5. |
| **Phase 3 — Sustain** (ongoing) | E10 refresh | Full suite in CI per agent version; quarterly price re-benchmark; corpus grows with every real dump. Score holds. |

## 7. PDCA operating model

Each cycle:

1. **Plan** — pick one tracker item (or a slice). Write: objective, the acceptance
   criteria being targeted this cycle, the design, what is explicitly deferred, and how it
   will be Checked (test that can run now vs. test that needs a deployment).
2. **Do** — implement. Code + tests + docs in one branch/commit set.
3. **Check** — run the runnable acceptance tests. Record results verbatim (pass/fail/
   deferred). A deferred check names the environment it needs and the tracker item that
   will close it.
4. **Act** — write the outcome to `pdca-log.md`; update `tracker.md` statuses; adjust this
   PRD if the cycle changed scope or revealed a new requirement; name the next cycle.

Cycles are small on purpose — one testable increment each. The log is the audit trail for
the eventual evidence pack.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Agent regains numeric autonomy via a prompt tweak → determinism lost | E7.4 output guard is load-bearing; eval gate on every agent version |
| Real client dumps vary more than the 3 profiles cover | Profiles are config; broken-dump corpus grows; DQ report makes gaps visible instead of silent |
| ±15% model mistaken for a bid | Every output states the tolerance and the DRAFT boundary; commercial sign-off required |
| Schema change breaks the live sample deployment | Migration noted per cycle; postprovision recreates tables; live env is synthetic data |
| Evidence pack ages (prices, SKUs, CAF) | Phase 3 quarterly re-benchmark is in scope, not optional |

## 9. Open questions

- **OQ1** — Landing zone: wire the `azure-enterprise-infra-planner` skill directly, or a
  purpose-built `design_landing_zone` tool that borrows its `infrastructure-plan.json`
  shape? (Leaning: tool, for determinism and traceability.)
- **OQ2** — Isolation: one deployment per engagement (simpler) confirmed as the model —
  any driver for shared-with-RLS instead?
- **OQ3** — Effort model: implement as an agent tool, or as a post-processing step outside
  the agent that consumes its structured output? (Leaning: outside, for determinism.)
- **OQ4** — Reference estates for the back-test: MRG (`sample-estate/`) + two more — what
  shapes? (Proposed: a 60-server greenfield SaaS-heavy estate; a 900-server regulated
  estate.)
