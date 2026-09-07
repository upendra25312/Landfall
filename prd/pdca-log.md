# Landfall 5/5 — PDCA delivery log

Operating model: [`landfall-5x5-prd.md` §7](landfall-5x5-prd.md). Tracker:
[`tracker.md`](tracker.md). Newest cycle first.

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
