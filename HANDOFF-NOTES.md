# Landfall — Cycle 52 handoff

2026-09-10 · E13.6 · branch `cycle-52-web-routers` · baseline `main` at `6f3ef46`.

**DEPLOYED 2026-09-10 after the user's follow-up authorization.**
`azd deploy web --no-prompt` exited 0, including the C48 chat.js syntax fix.
Revision `ca-web-tmglwfatwcsa2--azd-1789026943` is healthy and receives 100% of
traffic. Live smoke: 8 passed, 0 failed, 0 skipped; evidence in
`evidence/cycles/c52/smoke-live.json`. E13.6 is done; Epic E13: 9 done, 8 backlog.
No provisioning or SQL schema changes were performed.

## Implementation

- `src/web/app.py`: 54 lines; telemetry setup, middleware, router registration.
- Eight routers under `src/web/routes/`: chat, engagements, uploads, analysis,
  transfers, questionnaire, dashboard, pages; each 68–185 lines.
- Shared modules: `web_runtime.py` (config, lazy Azure client, assets/MIME/time/log),
  `web_storage.py` (blob clients and reads), `web_access.py` (principal and
  engagement guards), `chat_state.py` (persisted conversation).
- Routers never import `app`; the Docker entrypoint stays `uvicorn app:app`.
  HTTP contracts, guards, telemetry, page assets, and Foundry tool contracts remain
  unchanged. No agent recreation, API/calc deploy, infrastructure, or tier change.
- Test seams now patch their owning modules. The chaos C5/C6 source probe and
  the learning-path chat reference point to `src/web/routes/chat.py`.
- `tests/fixtures/web_openapi_c51.json` captures the pre-extraction API schema;
  `tests/test_web_routers.py` checks exact parity, all 30 route/method combinations,
  module-size limits, and the router/entrypoint import boundary.
- Browser fixture now returns a canned table; the new browser journey proves
  chat → reload → saved answer → real Excel download with question/provenance.

## Validation

Final pytest: **494 passed, 7 skipped, 1 deprecation warning in 35.54s; exit 0**.
The five browser skips run separately; live calculator smoke and LibreOffice
recalculation remain opt-in.
Evals exit 0: SQL 32/32, faults 30/30, adversarial 74/74 (3 already-pending
categories), scenarios 8/8. No scorecard content drift; overall score stays ~4.06.
Playwright: 5/5 before and after, zero console/page errors. Desktop and mobile
screenshots in `evidence/cycles/c52/{before,after}/` have matching SHA-256 hashes.
No static JS changed; the existing JS syntax guard runs in the full suite.

The first full run caught an extraction error in `_save_chat` and the stale
chaos-probe path; both were fixed. A subsequent slow run exposed a header test
relying on entrypoint reload to reset storage state; it now explicitly stubs
storage to remain offline. The final full suite passed before commit/merge.

## Operator / next cycle

The web service is deployed. The public endpoint returns 401 (EasyAuth enforcing);
signed-in browser journeys were not exercised against production. Local browser
checks passed before deployment. A signed-in user can check chat, engagement
switching, upload/analysis, persisted chat, and Excel/dashboard downloads.
Do not provision the populated environment. E13.5 (centralized limits) and E13.9
(E12 tail) remain candidates for C53. No changes were made to external Claude
memory; fold this handoff into it after reviewing the cycle log.

The pre-existing untracked
`prd/landfall_master_implementation_prompt_revised_v2.md` was left untouched and
must not be swept into the C52 commit. No remote push is part of this cycle.
