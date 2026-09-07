# Landfall 5/5 — PDCA delivery log

Operating model: [`landfall-5x5-prd.md` §7](landfall-5x5-prd.md). Tracker:
[`tracker.md`](tracker.md). Newest cycle first.

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
