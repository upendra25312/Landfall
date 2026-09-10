# tests/

Start with the [system test plan](SYSTEM-TEST-PLAN.md) for the complete component
matrix, acceptance criteria, automated runner, and live/manual prerequisites.
Run `scripts/validate_system.py --output evidence/cycles/<cycle>/local` with the
project Python to retain local regression, eval and browser evidence.

Unit tests for Landfall — pure logic that runs without Azure:
the ingestion pipeline (`src/api/ingest/`), the cost engine (`src/api/cost/` —
right-sizer, `estimate_compute_cost`, `estimate_storage_cost`,
`estimate_run_rate_extras`) with injected price/rate books, the landing-zone
designer (`src/api/lz/`), the wave engine (`src/api/waves/` —
`score_dispositions`, `plan_waves`), and the deliverable assembler
(`src/api/deliverable/` — `assemble_estimate`, `estimate_effort`, `export`),
including a full-pipeline test that runs every tool over the sample estate,
assembles it, and renders the Excel / Word / PowerPoint exports; the SQL
guard (`src/api/sqlguard.py`); and the assessment dashboard (`src/web` —
`publish_estimate` blob writes + the `/dashboard` routes via FastAPI TestClient).

```bash
.venv2/Scripts/python -m pip install -r tests/requirements-dev.txt
.venv2/Scripts/python -m pytest tests -q
```

`conftest.py` puts `src/api` on the path so `import ingest` works, and exposes
`fixture_bytes()` / `sample_bytes()` helpers. Fixtures in `tests/fixtures/`:

| File | Purpose |
|---|---|
| `rvtools_vinfo.csv` | RVTools vInfo-shaped export (MiB units, VMware OS strings) |
| `broken_servers.csv` | duplicate key, blank required values, an unmapped column, no perf data |
| `unknown.csv` | headers that match no source profile |

`test_evals.py` wraps `evals/runner.py` (32 golden text-to-SQL cases + 8
full-estimate scenarios + 26 fault-injection cases + the output guard) so a
regression fails `pytest`; run the harness directly with
`.venv2/Scripts/python evals/runner.py` for the full scorecard.
`.github/workflows/evals.yml` runs both on every push / PR.

Tests that need a live Azure SQL / Blob (the Event Grid trigger end-to-end) are
tracked as tracker item **E1.6** and run at deploy time, not here.
