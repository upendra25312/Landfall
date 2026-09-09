# Chaos drill — results

**Last run:** 2026-09-09 · against live `rg-landfall` (swedencentral) + code at `main`.
Design + induce procedures: `scenarios.md`. Non-destructive probe: `probe.py`.

## Summary

| # | Failure | Method | Outcome |
|---|---|---|---|
| C1 | SQL auto-paused | **induced + observed** | PASS — retried through the ~40 s resume, no data loss |
| C2 | `ca-drawio` at zero replicas | **partially induced** (container is at 0) + prior incident | PASS — cold-start retry in place; the `.png` degrades to best-effort, `.drawio`/`.svg` unaffected |
| C3 | `ca-calc` down / queue stalled | verified by inspection | PASS — async-by-design, 202 + `status: building`, no 5xx |
| C4 | Retail Prices API unreachable | verified by inspection | PASS — falls back to the estimation rate book, assumption noted |
| C5 | `AGENT_ID` unset | verified by inspection | PASS — clean `503`, deterministic tools + dashboard unaffected |
| C6 | Model 429 / throttled | verified by inspection + seen this session | PASS — error surfaced, transcript + response-id pointer not advanced |

`probe.py` → 7/7 mitigations in place (`probe-result.json`).

## Detail

### C1 — Azure SQL auto-paused (induced + observed)

The Free-offer serverless DB auto-pauses after 1 h idle. During this session:

- `scripts/smoke.py` reported `sql_database  status='Paused'`.
- `scripts/export_all.py --sql` opened a connection and got
  `Database 'sqldb-landfall' ... is not currently available. Please retry the
  connection later.`
- Its retry loop (`_sql_connect`, 5 × 20 s) caught the transient, the DB resumed
  in ~40 s, and the run completed — **6,498 rows** dumped across the six tables,
  no partial result.

The same retry is in the request path: `src/api/tools.py` logs
`sql connect retry N/M (database resuming)` and re-tries before `query_inventory`.
**A paused DB is a slow first answer, not a failed one.**

### C2 — ca-drawio scaled to zero (partially induced)

`az containerapp show` confirms `minReplicas: 0` and `az containerapp replica
list` shows **0 running** — the cold-start path is the *normal* state, not an
edge case.

Mitigation (C27b): `src/api/lz/render.py` gives the first call a 45 s timeout and
one retry with a 3 s pause; if the container still isn't up it logs
`ca-drawio rasterise skipped` and returns `None`. `publish_estimate` /
`build_landing_zone_diagram` then ship `landing_zone.{drawio,svg}` without the
`.png`; `to_pptx` / `to_docx` fall back to the hand-drawn slide.

This scenario was a **real incident** — the original 20 s timeout silently
dropped the PNG on the first build after scale-to-zero; `e86c43e` fixed it. Not
re-induced end-to-end this cycle.

### C3–C6 — verified by inspection

Inducing these cleanly needs a throwaway env (they would disrupt the shared
`rg-landfall`). The induce procedure for each is in `scenarios.md`; `probe.py`
confirms the code path exists:

- **C3** `src/api/lz/functions.py` — `build_calculator_estimate` stages the spec,
  drops the queue message, returns `202`; `landing_zone.json` carries
  `status: building` until `ca-calc` writes it. No synchronous call to fail.
- **C4** `src/api/cost/` — the cost tools take an injected rate book and only
  *enrich* it from the live API; an unreachable API leaves the estimation rates
  in place and the figure's assumption row names the source + date.
- **C5** `src/web/app.py::chat` — `if not AGENT_NAME: return 503 "AGENT_ID not
  set"`. The `/dashboard/*` routes and every deterministic tool are independent
  of the agent.
- **C6** `src/web/app.py::chat` — `chat_doc["current_response_id"]` and the
  transcript turns are written **only after** a non-empty successful response; an
  exception hits `logging.exception("chat failed")` → `500` with no state
  mutation, so a retry resumes from the last good pointer.

## Gaps / follow-ups

- C2–C6 not yet induced end-to-end — worth one pass on a scratch env
  (`azd env new chaos-drill`) to convert "verified" → "observed".
- No automated recurring chaos run; `probe.py` could join the weekly
  `calc-adapter-smoke` schedule.
