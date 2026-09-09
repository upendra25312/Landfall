# Chaos drill (PRD E9 — "known-good under pressure")

Does the system degrade *predictably* when a dependency is down?

| File | What |
|---|---|
| `scenarios.md` | 6 failure modes on the critical path — expected degradation, the code that provides it, how to induce each |
| `probe.py` | Non-destructive: reads current Azure state + code paths, confirms the mitigations are in place (induces nothing) |
| `RESULTS.md` | Last run — which scenarios were induced+observed vs verified by inspection |
| `probe-result.json` | `probe.py` output (point-in-time, not drift-gated) |

Run: `python evidence/chaos/probe.py --json evidence/chaos/probe-result.json`

The governing rule: **a dependency being down produces a slow or partial answer
with a clear reason — never a wrong answer, never a silent half-result** (the E1.4
rule, applied to infrastructure).

Open: induce C2–C6 end-to-end on `azd env new chaos-drill` to turn "verified" into
"observed"; wire `probe.py` into the weekly CI schedule.
