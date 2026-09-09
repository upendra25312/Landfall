# Trials — usability + comprehension (PRD E10.4, scorecard Usability / Understandability)

Two human trials stand between "built" and 5/5 on the Usability and
Understandability dimensions. This folder is the **turnkey kit** to run them —
protocol, tasks, answer key, scoring sheet — plus a self-administered dry run
that validated the apparatus.

| File | What it is |
|---|---|
| `protocol.md` | Both trial designs: recruitment, setup, tasks, timing, acceptance bars, scoring |
| `comprehension-answer-key.md` | The 3 comprehension tasks + model answers + the pass line for each |
| `results-template.md` | Blank per-participant result form — copy one per person |
| `dry-run-2026-09-09.md` | Self-administered validation of the comprehension tasks (apparatus check, **not** a substitute for the cohort) |

## Status

| Trial | Bar | State |
|---|---|---|
| **Comprehension** (Understandability) | 3 people new to Landfall, 60 min with the docs, all 3 complete the task set unaided | **kit ready + dry-run validated** — needs 3 participants |
| **Usability** (Usability) | 3 pre-sales, 3 fresh estates, no engineer, all produce an architect-accepted package, median < 1 day | **kit ready** — needs 3 participants + an architect reviewer + 3 estates |

Run results land here as `comprehension-2026-MM-DD.md` / `usability-2026-MM-DD.md`,
and `evidence/scorecard.py` picks up the scores by hand-edit once they exist.

## Estates for the usability trial

The back-test estates (`evidence/backtest/estate_gen.py` — small / midmarket /
enterprise) are three ready, distinct synthetic estates. For a stronger result,
use estates the participants have not seen; the sample estate is off-limits (it
is in the docs).
