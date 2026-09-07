# tests/

Unit tests for Landfall. Cycle 1 covers the ingestion pipeline
(`src/api/ingest/`) — pure logic that runs without Azure.

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

Tests that need a live Azure SQL / Blob (the Event Grid trigger end-to-end) are
tracked as tracker item **E1.6** and run at deploy time, not here.
