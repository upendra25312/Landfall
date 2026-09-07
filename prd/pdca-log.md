# Landfall 5/5 — PDCA delivery log

Operating model: [`landfall-5x5-prd.md` §7](landfall-5x5-prd.md). Tracker:
[`tracker.md`](tracker.md). Newest cycle first.

---

## Cycle 6 — estimate_run_rate_extras (run-rate + one-time migration cost)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.4 (done).

### Plan

**Objective.** The lines beyond compute + storage that still land on the monthly Azure
bill — **backup** (vault storage + protected-instance fees), **internet egress** (from
`net_out_gb_30d`), **monitoring** (Log Analytics ingestion + Defender for Servers),
**support plan** — plus the **one-time** cost of the migration (Azure Migrate/ASR
tooling after its free window, replication egress, dual-running on-prem + Azure during
cutover). Deterministic; all rates from `estimation_config.json ["extras"]`, nothing
fetched. `monthly_infra_cost` (compute + storage) drives the dual-run line.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | Powered-off servers excluded from every per-server line | unit test |
| C2 | Backup = protected-data·factor·$/GB + instances·$/instance | unit test |
| C3 | Egress applies the internet fraction and the free tier | unit test |
| C4 | Monitoring = LA ingestion + Defender; Defender toggle works | unit test |
| C5 | Support is the configured flat plan rate (0 for `none`) | unit test |
| C6 | Tooling one-time = 0 while avg migration months < free window; > 0 after | unit test |
| C7 | Dual-run one-time scales linearly with `monthly_infra_cost` | unit test |
| C8 | `total_monthly` reconciles; `first_year_extras = run_rate·12 + one_time` | unit test |
| C9 | Deterministic over the full sample `servers.csv` | unit test |

**Design.** `cost/run_rate.py` — one pure function, no network. `cost/functions.py` —
`POST /api/estimate_run_rate_extras`. New `extras` block in `config.py` DEFAULTS +
`estimation_config.json`. OpenAPI spec + agent tool #6 + prompt line.

**Deferred.** ExpressRoute/VPN and landing-zone fixed services stay separate proposal
lines (E3 / commercial). Commitment-tier LA discounts are a config edit, not modelled.

### Do

- `src/api/cost/run_rate.py` — new. `functions.py` — 4th route. `config.py` — `extras`
  block. `__init__.py` exports `estimate_run_rate_extras`.
- `src/api/openapi/estimate_run_rate_extras.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 6) + `SYSTEM_PROMPT` run-rate line.
- `tests/test_run_rate.py` — 9 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **58 passed**. C1–C9 pass (see test names).

Full sample estate (233 powered-on servers), Sweden Central, infra bill $102.9k/mo:
```
backup          $  4,163 /mo   (vault storage + 233 protected instances)
internet egress $    491 /mo   (30% of 33 TB net_out, less 100 GB free, @ $0.05/GB)
monitoring      $ 11,534 /mo   (Log Analytics $8,039 @ 0.5 GB/server/day + Defender $3,495)
support         $    100 /mo   (Standard, flat)
RUN-RATE EXTRAS $ 16,287 /mo   ($195,445 /yr)

one-time: dual-run $77,170 (1.5 mo x 50% of infra) ; tooling $0 (within 180-day free window)
first-year extras  $272,615
```

### Act

- **E2.4 done.** Full Azure run-rate for the sample estate: compute+disk ~$86k +
  storage ~$16.5k + extras ~$16.3k ≈ **~$119k/mo (~$1.43M/yr)**, plus ~$77k one-time.
- **Watch:** monitoring is the largest extra and the most assumption-sensitive
  (LA GB/server/day). Default is deliberately conservative (0.5 GB — syslog + counters,
  not verbose VM insights); a real engagement sets it from the client's logging policy.
- **E2.1–E2.4 done** — right-size, compute BoM, storage BoM, run-rate extras. Every
  result already carries a low/expected/high range; **E2.5** (an explicit top-3
  cost-driver / sensitivity block on each result) is still open, small, and can fold
  into the E5 deliverable cycle. **Next — Cycle 7:** E3.1/E3.2 — `design_landing_zone`
  (ALZ topology, spoke count, regulated-spoke flag from the portfolio + compliance
  scope), using the `azure-enterprise-infra-planner` skill.

---

## Cycle 5 — estimate_storage_cost (file / DB / object BoM)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.3 (done) ·
**Closes audit** FIN-3 remainder (compute BoM landed in Cycle 4; storage was deferred).

### Plan

**Objective.** Cost the `dbo.storage` table — file shares (Files Premium / NetApp),
managed/PaaS DB volumes (SQL MI, Hyperscale, PostgreSQL/MySQL Flexible, Oracle), object
(Blob). Line-item bill + by-type totals + low/expected/high, deterministic on injected
rates. **Disjoint** from `estimate_compute_cost`: that tool prices one managed disk per
VM (`type='block'`), so block volumes are excluded here and only reported — unless
`storage.price_block_from_storage_table` is set (then the caller suppresses disk in the
compute tool).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | `classify()` maps type + target_service → the right rate category | unit test |
| C2 | Block volumes excluded by default, counted in `excluded`; switch includes them | unit test |
| C3 | Files-premium / ANF min-provision floor billed even when the share is smaller | unit test |
| C4 | DB lines get the growth-headroom % and carry the "storage only" caveat | unit test |
| C5 | Injected rate overrides the config rate; `range.low ≤ expected ≤ high`; totals reconcile | unit test |
| C6 | Missing / zero size flagged in `not_costed`, never fatal | unit test |
| C7 | Deterministic over the full sample `storage.csv` | unit test |
| C8 | Live retail rates parse and are sanity-clamped to the config baseline | live fetch spot-check |

**Design.** `cost/storage_cost.py` — pure rate math on a `{category: usd_gb_month}`
book. `cost/pricing.py` gains `fetch_storagebook(region)` (best-effort per-service
queries, `_cheapest_stored` after a backup/redundancy exclude list, `_sane()` clamp to
0.4×–2.5× of the documented baseline so a mis-matched meter can't silently replace a
defensible rate). `cost/functions.py` — `POST /api/estimate_storage_cost` (6 h rate
cache). New `storage` block in `config.py` DEFAULTS + `estimation_config.json`. New
OpenAPI spec + agent tool #5 + prompt line.

**Deferred.** E2.4 — run-rate extras (backup, egress, monitoring, support) + one-time
migration cost. Object-tier lifecycle rules. Per-DB compute sizing (that's a replatform
concern, E4).

### Do

- `src/api/cost/storage_cost.py` — new. `pricing.py` — `fetch_storagebook` + helpers.
  `functions.py` — 3rd route + `_storage_rates` cache. `config.py` — `storage` block.
  `__init__.py` exports `estimate_storage_cost`, `classify`.
- `src/api/openapi/estimate_storage_cost.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 5) + `SYSTEM_PROMPT` storage line.
- `tests/test_storage_cost.py` — 10 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md` updated.

### Check

`pytest tests -q` → **49 passed**. C1–C7 pass (see test names).

C8 — live fetch (`swedencentral`, price_date `2026-09-01`): kept
`anf_standard 0.147`, `anf_premium 0.294`, `db_sql_mi 0.137` (GP LRS),
`db_sql_hyperscale 0.119`, `db_flex_postgresql 0.115`, `blob_hot 0.017`. Rejected by the
sanity clamp and fell back to config: `files_premium` (live 0.06 vs baseline 0.164 — a
Provisioned-v2 PAYG meter), `anf_ultra` (no match), `db_oracle` (no public meter).

Full sample estate (566 storage rows), Sweden Central:
```
file shares (5, 30 TB)     $  8,235 /mo
PaaS-DB volumes (39, 53 TB) $  8,301 /mo   (storage only — DB compute is a replatform line)
object                     $      0 /mo
TOTAL                       $ 16,536 /mo   ($198,430 /yr)
range                       $ 12,402 .. $ 20,670 /mo
excluded: 522 block volumes (~161 TB) — in the compute BoM's per-VM managed disk
```

### Act

- **E2.3 done.** Compute + storage now give a full infra run-rate: ~$86k/mo compute +
  disk, ~$16.5k/mo file/DB/object → **~$103k/mo (~$1.24M/yr)** for the sample estate,
  before dev/test pricing and E2.4 extras.
- **Watch:** the live storage-rate fetcher is heuristic (meter names vary by
  service). The `_sane()` clamp is the safety net; anything it rejects uses the
  documented `estimation_config.json` rate. Oracle DB@Azure has no retail meter — config
  rate only.
- **Next — Cycle 6:** E2.4 (`estimate_run_rate_extras` — backup GB, egress from
  `net_out_gb_30d`, monitoring, support tier + one-time migration/egress cost), then E3
  landing-zone deliverable (`azure-enterprise-infra-planner`).

---

## Cycle 4 — estimate_compute_cost (compute BoM)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.2 (done), E6.1 (advances) ·
**Closes audit** FIN-3 (nothing aggregated the SKU mix into a costed bill).

### Plan

**Objective.** Turn the right-size output into a monthly Azure compute cost — a
line-item bill of materials with PAYG / reserved / AHB, per-environment scaling, and a
low/expected/high range — deterministic for a given price date.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | AHB prices a Windows server at the Linux (no-licence) rate; flagged per line | unit test (injected prices) |
| C2 | Reserved blend = coverage·RI + (1−coverage)·PAYG at the configured term | unit test |
| C3 | Per-environment factor scales dr / non-prod compute | unit test |
| C4 | A SKU with no price is flagged in `missing_prices`, never fatal; line falls back to disk-only | unit test |
| C5 | `range.low ≤ expected ≤ high`; totals reconcile; `annual == monthly·12` | unit test |
| C6 | Deterministic | unit test |
| C7 | Real retail prices parse correctly (RI = amortised term total, Windows vs Linux) | live fetch spot-check |

**Design.** `cost/compute_cost.py` — pure math on an injected **PriceBook**
(`{sku: {linux|windows: {payg, ri1y, ri3y}}}`) + **DiskBook** (`{tier: monthly}`).
`cost/pricing.py` — builds those from prices.azure.com (VM + Premium SSD meters, chunked
OData, paging). `cost/functions.py` — `POST /api/estimate_compute_cost` (right-size →
collect SKUs → fetch prices, 6 h cache → cost). New OpenAPI spec + agent tool + prompt
("pass env + os_name too; never cost servers yourself"). Config `uplift` block reworked
to `nonprod_of_prod_pct` / `dr_of_prod_pct` / `dev_test_discount_pct`.

**Deferred.** Storage-table cost (file shares / DB / object) = E2.3. Run-rate extras
(backup, egress, monitoring, support) + one-time migration cost = E2.4. `ESTIMATION_CONFIG`
now supports an inline-JSON app setting; a package-baked default file is still TODO.

### Do

- `src/api/cost/{compute_cost,pricing}.py` — new. `functions.py` — 2nd route + price cache.
  `__init__.py` exports. `config.py` — `uplift` rework + inline-JSON `ESTIMATION_CONFIG`.
- `src/api/openapi/estimate_compute_cost.json` — new. `scripts/create_agent.py` — tool +
  prompt.
- `tests/test_compute_cost.py` — 8 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md` updated.

### Check

`pytest tests -q` → **40 passed**. C1–C6 pass (see test names).

C7 — live fetch (`swedencentral`, price_date `2026-06-01`):
`Standard_D4s_v5` linux `{payg 0.204, ri1y 0.12591, ri3y 0.08059}`, windows payg `0.388`
(the ~$0.184/hr delta is the Windows licence). First fetch returned RI as a **term lump
sum** (1103.0 / 2118.0) — fixed: reservations are always amortised `price/(years·8760)`.

Full 250-server estate, 1yr RI @ 80%, AHB on Windows:
```
compute PAYG        $ 81,106 /mo
compute RI          $ 50,315 /mo
compute effective   $ 56,473 /mo
managed disk        $ 29,884 /mo
TOTAL               $ 86,358 /mo   ($1,036,292 /yr)
range               $ 69,915 .. $138,840 /mo
missing_prices []   by_env prod 173 / nonprod 47 / dr 3 / dev 27
```
All 250 SKUs priced. Higher than `effort-inputs.md`'s old hand estimate (~$28–38k/mo) —
that assumed a 40% right-sizing cut and omitted managed-disk cost; the doc note is
updated. Every line is now traceable and ranged.

### Act

- E2.2 → `in-review` (unit + live-fetch verified; end-to-end via the agent with E1.6).
- **Next — Cycle 5:** E2.3 `estimate_storage_cost` over the `storage` table (file shares
  → Files/ANF, DB volumes → PaaS tiers, object), keeping it disjoint from the per-VM
  managed disk in `estimate_compute_cost`.

---

## Cycle 3 — deterministic right-sizer + firm config

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.1 (done), E6.1 (partial) ·
**Closes audit** FIN-1 (`vcpu/2` haircut), FIN-2 (RAM never sized).

### Plan

**Objective.** Replace the crude `vm_rightsize` heuristic with a deterministic,
RAM-aware right-sizer driven by the firm's config.

**Acceptance criteria this cycle**

| # | Criterion | Check |
|---|---|---|
| B1 | Sizes vCPU and RAM independently; a 128 GB box never maps to a 32 GB SKU; output says which bound it | unit test |
| B2 | No perf data → allocation kept as-is (no blind haircut), confidence "low" | unit test |
| B3 | With utilisation data → sizes to p95 (not raw peak) at the configured target; confidence "high" | unit test + full-estate rollup |
| B4 | Disk tier respects IOPS, not just size | unit test (100 GiB / 4000 IOPS → P30) |
| B5 | `estimation_config.json` changes the output | unit test with `config` override |
| B6 | Deterministic — same input, same output | unit test |
| B7 | Full `sample-estate/` (250) → every server gets a SKU; over-provisioned fleet shrinks on vCPU | integration test |

**Design.** New `src/api/cost/` package: `config.py` (DEFAULTS + `estimation_config.json`
deep-merge loader), `skus.py` (v5 F/D/E families **incl. constrained-vCPU E-SKUs** for
RAM-heavy boxes + Premium SSD tiers), `rightsize.py` (pure logic), `functions.py`
(`POST /api/vm_rightsize` blueprint). `vm_rightsize` route moves out of `tools.py`.
New root `estimation_config.json`. OpenAPI spec + `create_agent.py` prompt updated so the
agent passes utilisation columns and never sizes servers itself.

**Deferred.** `ESTIMATION_CONFIG` app setting in Bicep; the pricing / effort blocks of the
config aren't consumed yet (E2.2 / E6.2). `azure_retail_prices` still returns raw meters —
the cost roll-up is E2.2 (next cycle).

### Do

- `src/api/cost/{__init__,config,skus,rightsize,functions}.py` — new.
- `estimation_config.json` — new (root).
- `src/api/tools.py` — `vm_rightsize` + `_SKU_TABLE` + `_HEURISTIC` removed.
- `src/api/function_app.py` — register `cost_bp`.
- `src/api/openapi/vm_rightsize.json` — v2 schema (utilisation inputs, range, bound_by).
- `scripts/create_agent.py` — tool description + `SYSTEM_PROMPT` ("pass ALL utilisation
  columns; never size servers yourself").
- **Data:** `sample-estate/generate_estate.py` now rolls up `cpu_p95_pct` / `ram_p95_pct`
  (p95 of daily averages — the right-sizing signal). `schema.sql`, `ingest/core.py`,
  `ingest/loader.py`, `load_estate.py`, `tools.py` `SCHEMA_HINT` extended. CSVs regenerated.
- `tests/test_rightsize.py` (9 cases) + smoke-import checks.
- `README.md` — `estimation_config.json` section + repo-layout rows.

### Check

`pytest tests -q` → **31 passed**.

Full `sample-estate/` right-size rollup:
```
servers 250 · downsized 72 · at_ceiling 0 · low_confidence 66
current_vcpu 1940 → recommended_vcpu 1604   (-17% fleet vCPU)
```
Spot check srv-0014 (64 vCPU / 256 GB, p95 CPU 33% / RAM 87%): → `E48s_v5`, bound_by
`ram`, confidence high, basis *"sized to p95 utilisation … at 65/80% targets"*, range
`E32s_v5`…`E48s_v5`. Unmonitored srv-0004: kept at 100%, confidence low, basis names it.

| # | Result |
|---|---|
| B1 | pass — `{vcpu:4, ram_gb:128}` → E-family, `ram_gb ≥ 128`, `bound_by=="ram"` |
| B2 | pass — no perf → `vcpu` not reduced, confidence low, "no blind reduction" in basis |
| B3 | pass — p95 path downsizes 16→8 vCPU, confidence high; full estate -17% vCPU, only monitored servers move |
| B4 | pass — 100 GiB / 4000 IOPS → P30 (P10 caps at 500 IOPS) |
| B5 | pass — `no_perf_data.cpu_scale_pct=60` → `need.vcpu == 6.0` |
| B6 | pass — `rightsize_one(s) == rightsize_one(s)` |
| B7 | pass — 250/250 get a `Standard_*` SKU; fleet vCPU shrinks |

Bug found + fixed during Check: sizing fell back to raw 30-day **peak** when p95 was
absent, which upsized the whole over-provisioned estate (2472 vs 1940 vCPU). Fixed:
added real `cpu_p95_pct` / `ram_p95_pct` rollups to the data; right-sizer p95-chain is now
`[p95, avg, peak×0.75]` — never sizes to a raw maximum.

### Act

- E2.1 → `in-review` (unit-verified; live check with E1.6). E6.1 → `in-review` (file +
  loader done; pricing/effort blocks unused until E2.2 / E6.2).
- **Next — Cycle 4:** E2.2 `estimate_compute_cost` — take the right-size output, price it
  via `azure_retail_prices`, compute monthly PAYG + 1yr/3yr RI + AHB, storage from the
  `storage` table, return a line-item BoM with region + term + price date and a
  low/expected/high range.

---

## Cycle 2 — deploy wiring + docs for the ingestion pipeline (E1.6, partial)

**Date:** 2026-09-07 · **Owner:** SRE + Writer · **Tracker:** E1.6, D1.

**Plan.** Make the ingestion pipeline reachable through `azd` and documented.

**Done.**
- `scripts/eventgrid.{sh,ps1}` already add the `landfall-inventory` subscription (cycle 1);
  reviewed — webhook `functionName=Host.Functions.ingest_blob`, subject prefix
  `/blobServices/default/containers/raw/blobs/inventory/`.
- `DEPLOY.md` + `INSTALL.md`: postdeploy now documented as two subscriptions; §"Load
  client data" rewritten around `raw/inventory/` + the DQ report; troubleshooting rows for
  "files don't load" and "wrong table / dropped columns"; note that `schema.sql` is a
  destructive recreate.
- `D1` closed except the `estimation_config.json` doc claim (removed in E6.1).

**Check.** Docs only — no runnable check. Reviewed the eventgrid scripts against the
blueprint function name.

**Deferred (still E1.6).** The live end-to-end check — `azd provision` (to apply the
schema changes: dropped FKs, new columns, `performance` / `ingest_log` tables) + `azd
deploy api` + drop a file in `raw/inventory/` on `rg-landfall` + confirm SQL + DQ report.
Needs the user to run `azd` against the live subscription; the schema recreate wipes the
current synthetic data (re-loadable from `sample-estate/`).

**Act.** E1.6 stays `in-progress` pending the live check. Proceeding to the cost engine
(E2) since it is the next audit blocker and fully buildable/testable offline.

---

## Cycle 1a — sample-estate performance & flow data (user request, out-of-band)

**Date:** 2026-09-07 · **Owner:** SWE + PMO · **Tracker:** feeds E2 (cost engine inputs),
E4 (wave engine — flow-based move groups), E10.1 (back-test reference estate).

**Ask.** Add 30 days of performance data to `sample-estate/` — CPU, memory, disk IOPS,
network ingress/egress volume — plus observed dependency data.

**Done.**
- `sample-estate/generate_estate.py` — new `build_performance()` (deterministic per
  server): 30 daily samples over 2026-08-08→09-06 for the 173 monitored+powered-on
  servers. Per day: CPU avg/peak/p95 %, memory avg/peak/p95 %, disk IOPS
  (avg/peak/read/write) + throughput, network in/out GB + peak Mbps. Weekday/weekend
  shape, ~6% spike days. Rolls up into `servers.csv` (`cpu_*_pct`, `ram_avg_pct`,
  `disk_iops_avg/peak`, `net_in_gb_30d`, `net_out_gb_30d`). 66 servers (26%) stay
  unmonitored — preserves the low-confidence path and the `effort-inputs.md` number.
- Dependencies now carry `bytes_30d_gb`, `flows_30d`, `last_seen`; ~3% stale edges.
- New files: `sample-estate/performance.csv` (5,190 rows). Regenerated all 5 CSVs.
- Schema: `dbo.performance` table; `servers` +4 cols; `dependencies` +3 cols.
- Ingestion: `landfall_performance` profile + `_NATIVE_PERF` mapping (also recognises
  generic "cpu avg / iops avg / network out gb" headers); `_NATIVE_SERVERS` / `_NATIVE_DEPS`
  extended; `loader.TABLE_COLS` + `dq.CRITICAL` updated. `tools.py` `SCHEMA_HINT` updated.
- `sample-estate/load_estate.py` loads `performance.csv`.
- Tests: +3 cases (21 total, all green). Docs: `sample-estate/README.md`,
  `generate_estate.py` docstring.

**Check.** `pytest tests -q` → `21 passed`. Distribution spot-check: cpu_avg median 21%
(over-provisioned, matches narrative), net_out_gb_30d median 68 GB / max ~2.8 TB
(ecommerce tier), deps 484 with 16 stale. Generator is deterministic (seed 42 +
per-server `random.Random("perf::"+id)`).

**Act.** Real utilisation data is now in the reference estate — unblocks building
`estimate_compute_cost` / `rightsize` (E2) against something other than summary guesses,
and flow-weighted move groups (E4). No PRD scope change.

---

## Cycle 1 — Ingestion & data-quality core

**Date:** 2026-09-07 · **Owner:** SWE (with PMO on the DQ findings) ·
**Tracker:** E1.1–E1.5 (core), D1 (partial) · **Commit:** _see git log for this cycle_

### Plan

**Objective.** Close the #1 audit blocker: a client can drop an inventory export into the
data lake and it lands in Azure SQL with a data-quality report — no manual column mapping.

**Acceptance criteria targeted this cycle**

| # | Criterion | How checked this cycle |
|---|---|---|
| A1 | The 3 source formats (Landfall-native CSV, RVTools vInfo, generic CMDB) are detected and mapped correctly | unit tests on real `sample-estate/` files + RVTools fixture |
| A2 | Units are normalised (RVTools MiB→GiB, VMware OS strings → name/version) | unit test asserts `16384 MiB → 16.0`, `"…Server 2019…" → ("Windows Server","2019")` |
| A3 | An unrecognised file loads **nothing** and says why | unit test: `unknown.csv` → `table=None` + error issue |
| A4 | The DQ report names every defect in a known-bad dump and nothing spurious | unit test on `broken_servers.csv` (dupe key, blank required, unmapped column, no perf) |
| A5 | The DQ report gives an overall confidence and a "what's missing" list | integration check renders the report for the full sample estate |
| A6 | Idempotent re-ingest keyed by `source_file` | `loader._dedupe` unit test + `DELETE … WHERE source_file=?` in `load()`; **full DB round-trip deferred** |
| A7 | `function_app.py` still parses and registers the new blueprint | ast test |

**Design.** New package `src/api/ingest/`:
`core.py` (read csv/xlsx → detect profile → normalise rows, pure), `dq.py` (data-quality
report, pure), `loader.py` (SQL upsert + `ingest_log`, lazy Azure imports),
`functions.py` (Event Grid blob trigger on `raw/inventory/{name}` + `POST /api/ingest`
+ `GET /api/ingest_status`). Profiles are declarative (`Col(sources, transform, required)`)
so a 4th format is a config edit. `scripts/schema.sql` gains `source_file` / `ingested_at`
on the 4 tables and a new `ingest_log` table; the two soft FKs are dropped (files arrive
one table at a time and out of order — the DQ report is the integrity check).
`scripts/eventgrid.{sh,ps1}` gain a `landfall-inventory` subscription.

**Explicitly deferred**

- End-to-end test through a real Event Grid trigger + Azure SQL + Blob → **tracker E1.6**
  (runs at deploy time).
- Per-engagement column-mapping override file → **tracker E1.7**.
- Relaxing FKs on the **live** `rg-landfall` DB needs a one-time `azd provision` (or manual
  `ALTER TABLE … DROP CONSTRAINT`) — postprovision recreates the tables, live data is
  synthetic. Noted for the next deploy.

**Check method.** `pytest tests -q` (pure logic, no Azure) + one scripted integration
render of the DQ report for the full `sample-estate/`. DB/trigger checks are deferred as
above.

### Do

Implemented as designed. Files:

- `src/api/ingest/{__init__,core,dq,loader,functions}.py` — new.
- `src/api/function_app.py` — register `ingest_bp`.
- `src/api/tools.py` — `SCHEMA_HINT` notes the soft links + provenance columns.
- `scripts/schema.sql` — `source_file`/`ingested_at` + `ingest_log`; soft FKs dropped.
- `scripts/eventgrid.{sh,ps1}` — `landfall-inventory` subscription.
- `tests/` — `conftest.py`, `test_ingest_core.py`, `test_ingest_dq.py`,
  `test_ingest_loader.py`, `test_smoke_imports.py`, fixtures, dev requirements, README.
- Docs (D1 partial): `README.md` (architecture + repo layout), `docs/operating-sop.html`
  (Phase 1 rewritten to the drop-in path + DQ report step), `sample-estate/README.md`.

### Check

`e:\Landfall> .venv2/Scripts/python -m pytest tests -q`

```
..................                                                       [100%]
18 passed in 0.39s
```

Integration render — DQ report for the full `sample-estate/` (servers + applications +
dependencies + storage):

```
confidence: Medium
 - 66 of 250 servers (26%) have no CPU/RAM utilisation history — right-sizing LOW confidence …
 - 67 servers (27%) are not mapped to an application — wave planning by infra role only …
 - 1 dependency endpoint is not a known server (internet) — external / unmodelled node
servers   rows=250 dupes=0 orphan_app=0 orphan_srv=0
dependencies rows=490  storage rows=573  applications rows=31
```

| # | Result |
|---|---|
| A1 | **pass** — `landfall_servers/applications/dependencies/storage` and `rvtools_vinfo` all detected; CMDB profile present (fixture-tested via headers) |
| A2 | **pass** — `16384 MiB → 16.0 GiB`; `"Microsoft Windows Server 2019 (64-bit)" → ("Windows Server","2019")`; `"poweredOff"` normalised |
| A3 | **pass** — `unknown.csv` → `table=None`, error issue, 0 rows |
| A4 | **pass** — `broken_servers.csv`: duplicate `srv-0001`, unmapped `rack_location`, `vcpu`/`ram_gb` null-rate > 0, `no_perf_data == row count`, confidence Low/Medium |
| A5 | **pass** — full-sample report is `Medium` with a correct "what's missing" list (the 26% perf-gap matches `effort-inputs.md`) |
| A6 | **partial** — `_dedupe` (last-write-wins) unit-tested; `DELETE … WHERE source_file` in `load()`; **DB round-trip deferred to E1.6** |
| A7 | **pass** — `function_app.py` parses; `from ingest.functions import ingest_bp` + `register_functions` present; blob trigger uses `BlobSource.EVENT_GRID` |

One bug found and fixed during Check: `build_report` was dict-overwriting when two files
target the same table (e.g. native + RVTools servers), producing false orphan counts.
Fixed to group results per table; re-verified.

### Act

- **Outcome:** ingestion core is built and unit-verified. The pre-sales premise ("client
  dumps to the data lake, it works") is now true for the offline path; the deploy-time
  wiring (E1.6) is the remaining piece before it is true end-to-end.
- **Tracker:** E1.1–E1.3 → `in-review` (unit-verified, deploy check pending E1.6);
  E1.4–E1.5 → `in-review`; D1 → `in-progress` (DEPLOY.md / INSTALL.md still to update);
  E1.6, E1.7 stay `backlog`.
- **PRD:** no scope change. OQ2 (isolation model) unaffected.
- **Carry-over:** DB round-trip + Event Grid trigger check; DEPLOY.md/INSTALL.md updates;
  live-DB FK migration note for the next `azd provision`.

**Next cycle — Cycle 2:** E1.6 — wire ingestion into `azd` deploy and run the end-to-end
check (drop a file in `raw/inventory/` on the live `rg-landfall`, confirm SQL + DQ report),
then finish D1 (DEPLOY.md / INSTALL.md).
