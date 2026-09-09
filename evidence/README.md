# evidence/

Artefacts that back the "5/5" claims — each dimension's acceptance bar met and
**evidenced**, not asserted. Phase 2 of [`prd/landfall-5x5-prd.md`](../prd/landfall-5x5-prd.md).

| Dir | Tracker | What it shows |
|---|---|---|
| [`backtest/`](backtest/) | E10.1 | Three independent costing methods agree within ±15% on three differently-shaped synthetic estates — the headline run-rate is a property of the estate, not the SKU catalogue. `python evidence/backtest/backtest.py` regenerates [`backtest/RESULTS.md`](backtest/RESULTS.md); `tests/test_backtest.py` gates it. |

Planned: `broken-dumps/` (E10.2), `evals/` scorecard history (E10.3), `pentest/`
`trials/` `chaos/` (E10.4), `SCORECARD.md` (E10.6).
