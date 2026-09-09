# broken-dumps/ — E10.2

A corpus of deliberately damaged client inventory exports, and proof that the
ingestion pipeline handles each one per **E1.4** (graceful degradation — a broken
input is never a silent partial load; the data-quality report says why).

| File | What's wrong | Handled |
|---|---|---|
| `01_unrecognised_firewall_export.csv` | headers match no source profile | not loaded (`unrecognised`) |
| `02_empty.csv` | zero bytes | not loaded (`unrecognised`) |
| `03_servers_header_only.csv` | header, no data rows | loaded 0, report says "no data rows" |
| `04_performance_no_dates.csv` | required `sample_date` column absent | not loaded (`rejected`) |
| `05_servers_ragged_rows.csv` | inconsistent field counts | loaded, OS/app gaps named, Medium |
| `06_servers_garbage_numerics.csv` | `vcpu`/`ram_gb` not numeric | loaded, "vCPU unparseable on 100%", Low |
| `07_servers_duplicate_ids.csv` | one `server_id` on three rows | loaded, duplicate key named |
| `08_servers_utf16.csv` | UTF-16 encoding | not loaded (`unrecognised`) |
| `09_dependencies_orphan_endpoints.csv` | endpoints reference unknown servers | loaded, orphans named |

```
python evidence/broken-dumps/gen_dumps.py    # (re)write dumps/
python evidence/broken-dumps/check.py         # run the pipeline + rewrite RESULTS.md
```

`EXPECTED.json` is the contract (status / rows loaded / phrases the DQ report must
contain). `tests/test_broken_dumps.py` gates it; `evals.yml` fails on a stale
`RESULTS.md`. See [`RESULTS.md`](RESULTS.md) for the current run.
