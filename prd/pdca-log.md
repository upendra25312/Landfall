# Landfall 5/5 — PDCA delivery log

Operating model: [`landfall-5x5-prd.md` §7](landfall-5x5-prd.md). Tracker:
[`tracker.md`](tracker.md). Newest cycle first.

---

## Cycle 54 — Complete the validation tail

**Date:** 2026-09-10 · **Branch:** `cycle-54-validation-tail`

### Plan

Complete the remaining C53 checks: inspect and correct the four unverified
calculator adapters against live controls and exported values; run real workbook
recalculation; exercise authenticated production services using available approved
identity flows; run remote CI where repository authentication permits it. Preserve
customer data and the free-tier budget. Scratch lifecycle/chaos requires an
isolated environment; do not provision or induce faults in populated rg-landfall.
Independent security/human/architect/FinOps review must use actual reviewers;
prepare executable review material and record unavailable prerequisites honestly.

### Do / Check / Act

In progress. Retain evidence, fix reproduced defects, run regression, deploy only
changed services, update tracker/PRDs/handoff, commit and merge `--no-ff`.

---

## Cycle 53 — System validation plan, regression coverage, and fixes

**Date:** 2026-09-10 · **Branch:** `cycle-53-system-validation`
**Request:** test all project components/services/functions/features; implement
the plan, investigate failures, and fix them through PDCA.

### Plan

Publish `tests/SYSTEM-TEST-PLAN.md` with a component-to-check matrix, acceptance
criteria, execution commands, and explicit live/manual prerequisites. Build a
repeatable validation runner that retains results and does not label omitted
checks as passed. Inventory the web routes, Function triggers/OpenAPI tools,
sidecars, data/estimate pipeline, infrastructure, and operational controls.
Run existing pytest/evals/browser/evidence gates; add missing user journeys,
route dispatch and cross-engagement negative tests. Reproduce failures before
fixing them. Run live read-only health/auth/service checks in subscription
`f609eb5b-df3e-4fab-9a1b-9a8fea2f157f`, `rg-landfall`, Sweden Central.
No provision, teardown, paid tier, or changes to existing customer data.
Deploy validated code fixes to the affected service only, then repeat live checks.

### Do

Implemented the 18-group system test plan, evidence runner and live probes.
Added 25 boundary regressions, Function/tool registration and workbook-batch
tests, runner-failure tests, two browser journeys, and browser execution in CI.
Fixed cross-engagement artifact fallback, explicit/implicit default ACL bypass,
calculator download dispatch, ZIP owner/ACL/path/expansion validation and partial
failure reporting. Added bounded cold-host probe retries with attempt evidence.
The initial boundary run had 17 product failures plus two fixture errors; both
categories were resolved separately. An additional empty-scope test reproduced a
200 response exposing a private default artifact before the final guard fix.
Final review reproduced a concurrent engagement-create conflict after file writes;
new imports now reserve ownership with conditional create before touching files.
The final rollout exposed another probe defect: Azure listed the retiring revision
first. Smoke now selects the newest non-retiring active revision; healthy and
unhealthy replacement tests prevent a false failure or false pass.

### Check

Final pytest: **534 passed, 9 skipped, 1 dependency warning, 38.59s**. Browser:
**7 passed** (the seven browser skips are executed separately). Evals: SQL 32/32,
faults 30/30, adversarial 74/74 (3 existing pending categories), scenarios 8/8.
Backtest, broken-dump and scorecard-drift gates pass. Real calculator DOM: all
17 verified adapters pass; Bastion/Application Gateway remain unverified warnings.
The other two unverified adapters resolve controls but are not promoted.

`azd deploy web --no-prompt` exited 0; revision
`ca-web-tmglwfatwcsa2--azd-1789029091` ready, 100% traffic. Post-deploy smoke 8/8,
service-readiness checks 10/10 (27 registered Functions), security probes pass.
Authenticated Foundry definition read, Search count (27 docs), SVG→PNG render pass.
The first cold web timeout and missing local Search SDK are retained as before
evidence; retries and the existing pinned SDK resolve them. Delegated Function
token acquisition is blocked, so live model/SQL and signed-in web are not passed.
LibreOffice, remote CI, scratch lifecycle/chaos and human/external reviews remain
explicitly outstanding. [Full report](../evidence/cycles/c53/REPORT.md).

### Act

Tracker, both relevant PRDs, test documentation and HANDOFF-NOTES updated. Preserve
the existing scorecards and E13 9/17 status; validation is not roadmap completion.
Commit on `cycle-53-system-validation`, merge to `main` with `--no-ff`; no push.
Next: authenticated production journeys and the unverified calculator adapter tail.
No provision, SQL schema changes, new resources or paid-tier configuration.

---

## Cycle 52 — FastAPI router split (E13.6)

**Date:** 2026-09-10 · **Owner:** Python · **Tracker:** E13.6
**Branch:** `cycle-52-web-routers`

### Plan

Split the 1,159-line web entrypoint into focused APIRouters for chat,
engagements, uploads, analysis, transfers, questionnaire, dashboard, and pages.
Extract shared storage, identity, and runtime helpers without changing HTTP
contracts, access checks, conversation persistence, telemetry, or page assets.
Keep `app.py` below 150 lines and each route module below 300 lines.
Update test stubs to patch the owning modules, then prove route/OpenAPI parity,
run the full pytest suite, evals, and offline Playwright harness. Capture browser
evidence before and after the extraction. No Azure commands or live changes.

### Do

- Extracted all 30 route/method combinations into eight `src/web/routes/`
  modules: chat (185 lines), engagements (148), uploads (145), analysis (175),
  transfers (111), questionnaire (68), dashboard (97), and pages (68).
- `src/web/app.py` is now 54 lines: telemetry configuration, unchanged security
  middleware, and router registration. Shared dependencies live in
  `web_runtime.py`, `web_storage.py`, `web_access.py`, and `chat_state.py`.
  Azure clients remain lazy; routers never import `app`. No static asset or
  Foundry tool-contract changes.
- Repointed existing test stubs, the chaos C5/C6 source probe, and the
  learning-path chat reference to the owning modules. The security-header test
  explicitly stubs storage rather than relying on entrypoint reload to reset it.
- Added `tests/test_web_routers.py` and the pre-extraction C51 OpenAPI snapshot:
  exact HTTP schema parity, 30 unique route/method combinations, module-size
  limits, and no router → entrypoint imports.
- Added `tests/browser/test_router_journey.py`; the offline agent supplies a
  canned tabular tool result. A real browser sends a question, reloads the saved
  conversation, downloads Excel via its button, and verifies question/provenance.

### Check

```text
.venv2\Scripts\python.exe -m pytest -q -p no:cacheprovider
494 passed, 7 skipped, 1 warning in 35.54s; exit 0

.venv2\Scripts\python.exe evals\runner.py
Golden SQL 32/32; faults 30/30; adversarial 74/74 (3 previously pending);
full-estimate scenarios + output guard 8/8; exit 0

$env:BROWSER='1'; .venv2\Scripts\python.exe -m pytest tests\browser -q -p no:cacheprovider
Before: 5 passed in 7.81s; after: 5 passed in 7.85s; exit 0
```

The full suite includes Python 3.11 syntax compatibility and the existing static
JavaScript parse guard. No JS changed. The seven skips are the five separately
run browser tests, opt-in live calculator smoke, and LibreOffice recalculation.
The warning is the
existing Starlette/AnyIO deprecation. `-p no:cacheprovider` avoids the inaccessible
local pytest cache; project Python execution required sandbox escalation.

First full run: 6 failures (one erroneous qualification of the `_save_chat`
parameter caused five conversation failures; the chaos probe still read the old
path). Corrected both. A subsequent run was interrupted while diagnosing a
storage wait in the header-only test; explicit offline stubbing resolved it.
The final full run above is green.

Both scorecards have **zero content drift**; no score regeneration or score
increase. OpenAPI matches the pre-extraction snapshot exactly. `git diff --check`
passes. No Azure command, infrastructure change, new resource, or prod-tier change.

Browser evidence (zero console/page errors):
- Desktop: [before](../evidence/cycles/c52/before/chat-desktop.png) /
  [after](../evidence/cycles/c52/after/chat-desktop.png).
- Mobile, 375 px: [before](../evidence/cycles/c52/before/chat-mobile.png) /
  [after](../evidence/cycles/c52/after/chat-mobile.png).
- Each before/after pair has an identical SHA-256 hash; mobile was visually
  inspected. Layout and rendered content are unchanged.

### Act

Tracker and PRD §5b/§6 updated; handoff in `HANDOFF-NOTES.md` for the operator to
fold into Claude memory. E13.6 is **in-review (code complete)** until deployment
and live acceptance; Epic E13 remains 8 done, with 1 in review and 8 backlog.
Self-check replaces the Claude-only judge: tests/evals/browser green, scorecards
unchanged, bookkeeping complete, cycle branch used, no new resources, no Azure
commands, and no agent-contract change. Commit on `cycle-52-web-routers`, merge
with `--no-ff`; do not include the pre-existing untracked master-prompt document.

**NEEDS azd deploy web** by the operator, bundled with the pending C48 fix.
After deployment verify authenticated engagement switching, upload/analysis,
chat persistence, and exports. No provision or agent recreation is required.

---

### C52 deployment follow-up — 2026-09-10

After the implementation/merge report, the user authorized deployment ("do it"),
superseding the earlier operator-only restriction for this action.
`azd deploy web --no-prompt` exited 0; no provision, schema, or tier change.
Deployed image: `crtmglwfatwcsa2.azurecr.io/landfall/web-landfall:azd-deploy-1789026849`.
Ready revision: `ca-web-tmglwfatwcsa2--azd-1789026943`; healthy, running, 100% traffic.
This also delivers the pending C48 chat.js fix.

The first smoke attempt timed out on the scaled-to-zero web endpoint (7/8).
A subsequent direct probe returned 401 in 1.88s; the repeated full smoke passed
**8/8, exit 0**, with EasyAuth enforcing on web and Function endpoints, SQL paused,
and expected resources/blob containers present. Evidence:
[`smoke-live.json`](../evidence/cycles/c52/smoke-live.json).
Signed-in production browser journeys were not exercised; the five local browser
checks remain the functional browser evidence. E13.6 is now done, Epic E13 9/17.
Deployment evidence is recorded on `cycle-52-deploy-evidence` and merged `--no-ff`.

---

## Cycle 51 — `docs/learning-path.md` (E13.12)

**Date:** 2026-09-10 · **Owner:** Writer + Architect · **Tracker:** E13.12
(folds in brief E14.6 + the §18 lab→enterprise matrix).

### Plan

The sponsor's stated reason for building Landfall is to learn three things by
doing: **Azure AI Foundry**, **Azure Container Apps**, **enterprise-scale
design**. The codebase already demonstrates all three but nothing points a reader
at *where*. E13.12 is a single `docs/` page that maps each goal to the files and
PRD sections that embody it, so a new engineer reads the code, not a tutorial.

Chosen this cycle over the other sustain items (E13.5 agent ceiling, E13.6 split
`app.py`, E13.9 E12 tail) because **all three touch production code and need an
`azd deploy`, and the C48 `azd deploy web` is still outstanding** — piling more
undeployed production change on top of that is the wrong order. This cycle is
docs + tests only: zero deploy risk, and it moves Understandability (3.0, a low
dimension).

Acceptance: the doc exists, is linked from `docs/index.html`, points at real
files/sections for each goal, and `tests/test_docs.py` proves every reference
resolves.

### Do

- **`docs/learning-path.md`** (new) — Markdown (precedent: `docs/observability.md`;
  GitHub Pages renders `.md`). Structure:
  - **1 · Azure AI Foundry** — the agent-orchestrates-never-calculates pattern: a
    table of `scripts/create_agent.py` (`AGENT_NAME` / `SYSTEM_PROMPT` / `main()`),
    the Responses API `agent_reference` call in `src/web/app.py::chat()`,
    `src/api/tools.py` + `src/api/openapi/` (17 specs), `evals/runner.py`,
    `evals/adversarial.py`, `evals/output_guard.py` — each with a "why".
  - **2 · Azure Container Apps** — `infra/resources.bicep` (`containerEnv`,
    `containerApp`, `calcApp`, `drawioApp`, `uami`), scale-to-zero, the
    queue-decouple pattern (§4.6 / decision 10, `src/api/lz/functions.py`
    `stage_calc_run` → `src/calc/worker.py`), ACA **Jobs** (`calcJob` +
    `src/calc/job.py` `run_once()`, E13.13), KEDA queue trigger with managed
    identity, Easy Auth (`webAuthConfig` / `functionAuth`), `scripts/smoke.py
    --cold`, the planned $0 hostname (E12.11).
  - **3 · Enterprise-scale design** — per-engagement isolation
    (`src/api/engagement.py` / `engagement_sql.py`), fail-closed RLS
    (`scripts/schema.sql`), `src/api/sqlguard.py`, ADLS-as-record / SQL-as-projection
    (**brief E14.6**), `evidence/scorecard.py` + PDCA, the adversarial + fault CI
    gate, `.claude/agents/landfall-judge.md`, param-gated tiers
    (`infra/main.bicep` `deploymentTier`), cost guardrails
    (`Microsoft.Consumption/budgets` + `scripts/spend.py`), the ephemeral
    operating model (`scripts/teardown.sh` / `rehydrate.sh`), `tests/browser/`,
    `docs/observability.md`.
  - **Deployment profiles** — a lab → customer engagement → enterprise matrix
    (tier / tenancy / auth / network / cost / data lifecycle); only *lab* is
    exercised; private endpoints noted as descoped on cost (§4.14).
  - **Suggested reading order** — 7 steps ending at `prd/pdca-log.md`.
- **`docs/index.html`** — a "Learning Path" card (`href="learning-path.md"`),
  labelled *for builders*.
- **`tests/test_docs.py`** (+3):
  - `test_learning_path_exists_and_is_linked`
  - `test_learning_path_covers_the_three_goals_and_the_profiles_matrix`
  - `test_learning_path_repo_references_resolve` — every `` `backticked` `` token
    that starts with a known top-level dir, and every `](../…)` link, must resolve
    on disk (ignores `<placeholder>` / glob tokens). This is the anti-rot gate.

Two accuracy fixes made while writing (verified against `infra/resources.bicep`):
the web app's symbolic name is `containerApp` not `webApp`; Easy Auth is
`webAuthConfig` (web) + `functionAuth` = `authsettingsV2` (Function).

### Check

- **Full suite: 491 passed, 6 skipped** (`./.venv2/Scripts/python.exe -m pytest
  tests/ -q`) — +3 over C50's 488.
- **`tests/test_docs.py`: 10 passed** — the reference-resolution test confirms all
  ~30 cited paths exist.
- **`evals/runner.py` exit 0** — golden 32/32, scenarios 8/8, faults 30/30,
  adversarial 74/74. No `evals/SCORECARD.md` / `evidence/SCORECARD.md` content
  drift (CRLF-only phantom discarded).
- No `src/`, `infra/`, or OpenAPI change → **no `azd deploy`, no `azd provision`.**
  GitHub Pages serves `docs/` and auto-publishes on push to `main`.
- Scores unchanged this cycle — Understandability 3.0 → 5.0 needs the D2/E10.4
  three-consultant comprehension trial (people), which this page supports but does
  not itself close.

### Act

- Branch `c51-learning-path` → commit → merge `--no-ff` to `main` → push. No deploy.
- Tracker: E13.12 done (C51), progress table E13 **8/17**, cycle-51 row, `D4` row
  in Docs & method.
- Memory: `MEMORY.md` + `landfall-5x5-execution.md` (item 2w).

**Next by leverage:** the remaining sustain items all need a deploy —
**E13.5** (agent-run ceiling + centralized `MAX_*`), **E13.6** (split
`src/web/app.py` into `APIRouter` modules), **E13.9** (E12 tail: tool-call
milestones, direct-to-blob SAS, trust surface). **`azd deploy web` (the C48
`chat.js` fix) is still the top operator action** — do it before or with the next
web-touching cycle.

---

## Cycle 50 — `ca-calc` always-on → event-driven Container Apps Job (E13.13)

**Date:** 2026-09-10 · **Owner:** Azure Container Apps architect + SRE ·
**Tracker:** E13.13 (= brief E14.2). §21 Definition-of-Done: "No always-on
2-vCPU/4-GiB calculator worker remains." Also the best hands-on **Container Apps
Jobs** exercise in the repo (a stated learning goal).

### Decide

- **Problem:** `ca-calc` runs `minReplicas: 1` at 2 vCPU / 4 GiB — the only
  always-on container — to poll `calc-jobs`. It processes a few messages per
  engagement. C25b tried KEDA scale-to-zero on the *Container App* and it never
  scaled the replica up on a queued message (the MI-auth scaler shape wasn't
  wired through in that CA/KEDA version).
- **Choice:** a **Container Apps Job** with `triggerType: 'Event'` — KEDA starts
  one *execution* per `calc-jobs` batch, the container drains the queue once and
  exits, `minExecutions: 0`. The Jobs event trigger with managed-identity auth on
  the `azure-queue` scaler is the *documented* path (distinct from the CA replica
  scaler that failed in C25b). The dollar saving is ~nil (the ACA free grant
  already absorbs `ca-calc` idle — §4.15) but it clears the DoD and is real
  learning.
- **Cost:** $0 change (dormant). **Security:** unchanged — MI for queue + blob,
  no keys; the poison-message drop is kept.
- Ships **dormant** (`USE_CALC_JOB=false`) — a normal `azd up` is byte-identical.
  The operator flips it on a provision and proves the scaler live.

### Plan

- `src/calc/worker.py` — `run_once(max_jobs=8)`: receive → process → delete, loop
  until the queue is empty or the cap is hit, return the count. Keeps the
  `dequeue_count > _MAX_DEQUEUE` poison drop.
- `src/calc/job.py` — the Job entrypoint: `asyncio.run(run_once())`; **exit 0**
  even when the queue was empty by the time it ran (a benign KEDA race — a
  non-zero exit marks the execution Failed and retries it).
- `infra/resources.bicep` — `param useCalcJob bool = false`;
  `resource calcJob 'Microsoft.App/jobs@2024-10-02-preview' = if (useCalcJob)`
  (Event trigger, `replicaTimeout: 1800`, `replicaRetryLimit: 1`, KEDA
  `azure-queue` rule `{ accountName, queueName, queueLength: '1', identity: uami.id }`,
  `parallelism: 1`, `replicaCompletionCount: 1`, `command: ['python','job.py']`,
  2 vCPU / 4 GiB); `calcApp` → `if (!useCalcJob)`; outputs guarded.
- `infra/main.bicep` + `main.parameters.json` — thread `useCalcJob`
  (`USE_CALC_JOB=false`).
- `DEPLOY.md` cost lever #4; `tests/test_calc_job.py`.

### Do

- All of the above. The Function side (`build_calculator_estimate` staging a spec
  + dropping a queue message) is **unchanged** — the Job consumes the same queue.
- `calcJob` and `calcApp` share the `azd-service-name: 'calc'` tag and the
  `ca-calc-<token>` name; only one exists per `useCalcJob`. `azd deploy calc`
  targets whichever is tagged; if azd can't push to a job, `az containerapp job
  update --image` (documented).
- `drawioKey`-style deterministic defaults not needed here — the Job reads the
  same `STORAGE_*` / `CALC_QUEUE` env as the app.

### Check

| gate | result |
|---|---|
| new tests | `tests/test_calc_job.py` — **12 passed** (bicep structure, `az bicep build`, `run_once` drain/empty/poison, `job.main` exit codes) |
| calc suite | `test_calc_service.py` + `test_calc_adapters.py` green |
| bicep | `az bicep build --file infra/main.bicep` exit 0 |
| py311 | `test_py311_compat` green (job.py / worker.py parse on 3.11) |
| full suite | **488 passed, 6 skipped** (`pytest tests/ -q`) |
| evals | `evals/runner.py` exit 0 (untouched) |
| scope | `src/calc/` (a one-shot entrypoint + a helper fn) + **dormant** param-gated Bicep + docs + tests → **no `azd` deploy, no `azd provision`** |
| cost | $0 (dormant); when enabled, removes the always-on replica |

### Act

- `c50-calc-job` → merge `--no-ff` to `main`, push. No deploy.
- **Operator, on a future provision:** `azd env set USE_CALC_JOB true` → `azd up`
  (or `rehydrate.sh`) → confirm `ca-calc-<token>` is a `Microsoft.App/jobs` →
  ask the agent for a Calculator POE → confirm a Job *execution* starts, writes
  `landing_zone.*`, and completes; `az containerapp job execution list`.
- **Next:** the sustain items — E13.5 (agent-run ceiling + centralized `MAX_*`),
  E13.6 (split `src/web/app.py` into routers), E13.9 (E12 tail), or E13.12
  (`docs/learning-path.md` — now has the ACA Jobs pattern to document).

---

## Cycle 49 — safe teardown / rehydrate for the ephemeral operating model (E13.11)

**Date:** 2026-09-10 · **Owner:** SRE + FinOps ·
**Tracker:** E13.11 — the last P1 ephemeral guardrail. §7 decision 16: the sponsor
runs Landfall on a $40–50/mo budget, `azd up` on demand, `azd down --purge` after.

### Decide

- **Problem:** the teardown/rehydrate flow was a paragraph in §4.15, not runnable.
  `azd down --purge` is irreversible; a fumbled order loses every engagement. And
  a fresh `azd up` does **not** reproduce `ca-drawio` (`deployDrawio` was in
  `resources.bicep` but never threaded to `main.bicep` / `main.parameters.json`,
  so `azd` could not set it) — flagged as a blocker since C43.
- **Choice:** two guarded scripts (sh + ps1) + thread `deployDrawio` through so a
  *set-once* `azd env set DEPLOY_DRAWIO true` (persisted in `.azure/<env>/`) makes
  a rehydrated stack come back whole. The Bicep change ships **dormant**
  (`DEPLOY_DRAWIO=false`) — a normal `azd up` is byte-identical, so **no
  `azd provision`** this cycle.
- **Cost:** $0. **Security:** teardown is the *sanctioned* destructive path,
  gated on a verified export; rehydrate refuses to `azd up` a live RG (which would
  re-run `postprovision` → `schema.sql` DROP).
- I can't run `azd down` / `azd up` — the scripts are validated structurally; the
  operator runs the live round-trip once.

### Plan

- `scripts/teardown.{sh,ps1}`, `scripts/rehydrate.{sh,ps1}`.
- `infra/main.bicep` + `infra/main.parameters.json` — `deployDrawio` /
  `drawioImageName` / `drawioKey`.
- `scripts/smoke.py` — `--cold` / `--cold-budget`.
- `DEPLOY.md` — "Run a session / tear down after".
- `tests/test_teardown_rehydrate.py`.

### Do

- **`teardown.sh`** — load the azd env → if the RG is already gone, exit 0 →
  `export_all.py --out <backup> --sql` → assert `manifest.json` exists and
  `failed == 0` (else **abort before `azd down`**) → `sha256sum` the archive →
  `azd down --force --purge` → assert `az group show` fails (RG gone). Prints the
  `rehydrate.sh <backup>` command.
- **`rehydrate.sh <backup> [eid...]`** — **refuse if the RG still exists** (point
  the user at `azd deploy` for updates) → echo the `DEPLOY_DRAWIO` /
  `WEB_AUTH_CLIENT_ID` switch state → `azd up` → `create_agent.py` →
  `smoke.py --cold` → list the `*.landfall.zip` and tell the user to import them
  from the dashboard's **↑ import** (the import API is behind Easy Auth, so not a
  curl).
- **Bicep:** `main.bicep` gains the 3 params + passes them to `resources`;
  `drawioKey` defaults to `uniqueString(resourceToken, 'drawio-render')` when
  empty so a fresh RG regenerates a matching pair for the app secret and the
  Function's `DRAWIO_RENDER_KEY`. `main.parameters.json` +`DEPLOY_DRAWIO=false`,
  `SERVICE_DRAWIO_IMAGE_NAME`, `DRAWIO_KEY`. `resources.bicep` already gates every
  drawio resource on `if (deployDrawio)`. `az bicep build` clean.
- **`smoke.py --cold`** — `_timed_http()` wraps the probe; a `cold_start` check
  times `web /healthz` + `function /api/engagements` and FAILs past
  `--cold-budget` (default 120 s) or if nothing answers.
- **`tests/test_teardown_rehydrate.py` (11)** — export-before-destroy ordering,
  `$FAILED` gates `azd down`, the rehydrate RG-gone precondition, the PowerShell
  twins carry the same guards, the drawio params are threaded + dormant + a normal
  deploy is byte-identical, `az bicep build` compiles, `smoke.run_checks(cold=True)`
  adds `cold_start`, the CLI accepts `--cold` / `--cold-budget`.

### Check

| gate | result |
|---|---|
| new tests | `tests/test_teardown_rehydrate.py` — **11 passed** |
| smoke | `test_smoke.py` green; `smoke.py --from-env --cold` runs, `cold_start` SKIPs with no endpoint |
| bicep | `az bicep build --file infra/main.bicep` exit 0 |
| full suite | **479 passed, 6 skipped** (`pytest tests/ -q`) — +11 vs C48 |
| evals | `evals/runner.py` exit 0 (untouched) |
| scope | scripts + **dormant** param-gated Bicep + `smoke.py` + docs + tests → **no `azd` deploy, no `azd provision`** |
| cost | $0 |

### Act

- `c49-teardown-rehydrate` → merge `--no-ff` to `main`, push. No deploy.
- **Operator, one-time live proof:** `scripts/teardown.sh` (from a deployment with
  ≥1 engagement) → confirm the backup + RG gone → `scripts/rehydrate.sh <backup>`
  → confirm `smoke.py --cold` green → re-import an engagement → confirm its data.
  Set `DEPLOY_DRAWIO=true` + `WEB_AUTH_CLIENT_ID` first for a complete stack.
- **Next:** E13.13 (`ca-calc` always-on → event-driven ACA Job — the §21 DoD item
  + the best Container Apps Jobs learning exercise), or the sustain items
  (E13.5 agent-run ceiling, E13.6 split `app.py`, E13.9 E12 tail).

---

## Cycle 48 — Playwright browser-automation harness (E13.15) + the P0 it caught

**Date:** 2026-09-10 · **Owner:** QA + Full-stack ·
**Tracker:** E13.15. §4.17 (decision 18) made a browser check a per-cycle gate;
it needed a real harness or it was aspirational.

### Decide

- **Problem:** every UI cycle since C34 was verified with `TestClient` substring
  assertions — which check the response *body*, never that the page renders or the
  JS runs. §4.17 says drive a real browser; nothing did.
- **Choice:** a committed `pytest-playwright` harness under `tests/browser/`, run
  against a local `serve.py` (the real `src/web/app.py` with an **in-memory blob
  store** + a **canned agent** — no Azure, no model), gated on `BROWSER=1` so it
  stays out of the normal suite until E13.16 wires headless Chromium into CI.
  Chromium is already cached locally (calc work); only `pytest-playwright` +
  `uvicorn` are new dev deps.
- **Cost / security:** $0, no runtime change from the harness itself.

### Plan

- `tests/browser/serve.py` — offline app launcher (reusable by hand + the MCP).
- `tests/browser/conftest.py` — `BROWSER=1` gate + a session fixture that
  subprocesses `serve.py` on a free port and waits for `/healthz`.
- `tests/browser/test_chat_page.py` — the 6 §4.17 journeys (automate what's cheap).
- `tests/browser/README.md` — journeys + run + gotchas.
- `tests/requirements-dev.txt` += `pytest-playwright`, `uvicorn`.

### Do

- **The harness's first run caught a live P0.** `static/chat.js:294/303/304` had
  `client\'s` / `I\'ll` — **`\'` (a literal backslash then a `'`) inside a
  single-quoted JS string**, so the string ended early and the rest was a syntax
  error. `node --check`: `SyntaxError: missing ) after argument list`. C41 lifted
  the inline `<script>` out of a Python `"""…"""` (where `\'` meant `\'` and `\n`
  meant a newline) into `chat.js` **verbatim**, doubling every escape. **Result:
  `<script src="/static/chat.js">` never parsed → nothing ran → the engagement
  picker, the welcome, the prompt cards, the chat, the pipeline strip, the upload
  panel wiring were ALL dead — from C41 (2026-09-09) through C47, across four
  `azd deploy web` runs.** No test saw it: `test_dashboard.py` / `test_upload.py` /
  `test_pipeline.py` assert substrings in the *served text*, and the page under
  `TestClient` never executes JS.
- **Fix:** `\'` → `\'` (proper escaped quote) ×3; `'\n\nReplace it?'` and
  `/\n/g` (were `\n` literal) ×2 cosmetic. `node --check` clean.
- **Regression guards** (`tests/test_web_csp.py` +2): `node --check` on every
  `static/*.js` when Node is on the box (skip otherwise); a scan for the
  `\\['"nrt]` double-escape fingerprint in the static assets.
- **Harness:** `serve.py` `_Store` / `_BlobClient` (enough of the container + blob
  surface for the pages under test) + `_FakeOpenAI`, seeded with two engagements
  (`contoso-ltd/dc-exit` with inventory + DQ + estimate; `northwind/pilot` empty).
  4 journeys automated:
  - **(a)** `/` loads under the strict CSP, `chat.{js,css}` load, welcome + cards
    render, **0 console/page errors**.
  - **(b)** the engagement `<select>` is populated from `/api/engagements`; the
    choice persists across a reload.
  - **(d)** the pipeline strip shows 3/4 done for the seeded engagement, 0/4 for
    the empty one, with the right "Next:" hint.
  - **(f)** asking before analysis → a one-time, non-blocking hint **and** the
    agent answer still arrives; the hint fires at most once per engagement.
  - c (interactive upload) + e (prompt-card → Excel) stay MCP-driven (README).
- **Gotchas:** `page.wait_for_function("<string>")` violates `script-src 'self'`
  (`unsafe-eval`) — used `expect(locator)` assertions instead; `<option>` isn't
  "visible" — waited with `state="attached"`. `tests/browser/__init__.py` was
  needed so its `conftest.py` doesn't collide with `tests/conftest.py` in the
  module namespace (the recurring name-collision bug class: `sec_probe`,
  `telemetry`, `spend` — now `tests.browser.conftest`).

### Check

| gate | result |
|---|---|
| browser harness | `BROWSER=1 pytest tests/browser` — **4 passed**, 0 console/page errors; screenshot captured |
| `chat.js` | `node --check` clean |
| collection | 474 tests collected, no errors (the `__init__.py` fix) |
| full suite | **468 passed, 6 skipped** (`pytest tests/ -q`) — +2 vs C47 (the CSP guards); 4 skipped = the browser specs |
| evals | `evals/runner.py` exit 0 (unchanged — no eval touched) |
| scope | **`src/web/static/chat.js` changed → `azd deploy web` REQUIRED** (the live chat page is broken until then); everything else is tests/deps/docs |

### Act

- **`azd deploy web` is required** — hand-off to the operator (I can't run it). The
  live chat page has been non-functional since C41; this deploy fixes it.
- `c48-browser-harness` → merge `--no-ff` to `main`, push.
- **Next:** E13.11 (safe teardown / rehydrate — the last P1 ephemeral guardrail),
  then automate journeys c + e, then E13.16 (headless in CI).
- Ran the `landfall-judge` checklist inline (the subagent def loads next session).

---

## Cycle 47 — adversarial eval suite (E13.3) + `landfall-judge` cycle gate (E13.17)

**Date:** 2026-09-10 · **Owner:** Azure AI architect + DevSecOps + Method ·
**Tracker:** E13.3 (adversarial half) + E13.17. §4.16 flagged E13.3 as the only
self-contained Security lever left (Security 3.75; the external pen test needs a
person). Sponsor also asked for a "judge" agent that checks progress + quality and
coordinates a correct deploy.

### Decide

- **Problem:** `evals/faults.py` is *infra* fault injection only — there is no
  eval that throws hostile input at the guardrails (SQL injection → tool abuse,
  coerced cross-engagement read, path traversal, malicious upload, fabricated
  numbers). The threat model (`evidence/pentest/threat-model.md`) tells an external
  tester to try exactly these; nothing gates them on every commit.
- **Choice:** `evals/adversarial.py` — exercise the **deterministic** guardrails
  offline (no live model), wire it into `evals/runner.py` as a hard gate + into the
  SCORECARD. The live-model half of E13.3 (bump the Foundry agent to a current-gen
  model, re-run evals, record the delta) needs a deploy + token spend → **deferred
  to a sponsor-run cycle**.
- **Judge agent → Claude Code subagent, not Foundry** (§7 decision 19). It runs
  `pytest` / `evals` / `az bicep build` / `git` and reads the tracker + memory —
  none of which a Foundry runtime agent can do; and the Foundry agent is the
  customer-facing product, which must not carry dev-orchestration logic. Toolboxes
  stay deferred (only relevant to E15.1, and the brief says evaluate-not-adopt).
- **Cost:** $0 — offline evals + a subagent definition. **Security:** the gate
  turns a class of regressions (weakened injection resistance, a new route that
  skips the RLS binding, an upload filter hole) into a red build.

### Plan

- `evals/adversarial.py` (new) · wire into `evals/runner.py` (import, run, scorecard
  section, gate on it) · `tests/test_evals.py` +2 wrappers · regenerate
  `evals/SCORECARD.md`.
- `evals/output_guard.py` — add `FTE` to the claim-suffix regex (an adversarial
  case found "14 FTE" slipped through as a structural number).
- `evidence/scorecard.py` — Security 3.75 → 4.0 (basis + gap + evidence), thread
  `adversarial` through `_parse_eval_scorecard` + the Reliability basis + the
  evidence index; regenerate `evidence/SCORECARD.md`.
- `.claude/agents/landfall-judge.md` (new) — Gate A / B / C + verdict format.
- `.github/workflows/evals.yml`, `evals/README.md`, `evidence/pentest/README.md` —
  reference the suite. PRD §5b (E13.3, E13.17) + §6 + §7 decision 19; tracker;
  memory.

### Do

- **`evals/adversarial.py` — 74 cases / 6 categories:**
  - `sql-guard` — 18 hostile SELECTs rejected by `sqlguard.safe_select`
    (stacked `; DROP`, `UNION ... sys.tables`, `information_schema`, `xp_cmdshell`,
    `OR '1'='1'; SELECT 1`, unknown table, `INTO`, `WAITFOR`, `sp_configure`,
    `OPENROWSET`, `FOR JSON`, bare DML/DDL) + 3 legit queries still pass.
  - `engagement-isolation` — `set_engagement` binds a **read-only** session context
    to the *caller's* id; a malformed/traversal id is refused before any DB
    round-trip; `query_inventory` calls `_set_engagement` **before** `cur.execute`
    (source-order check, so a model SQL that hard-codes another `engagement_id` is
    still RLS-scoped); `schema.sql` policy is `STATE = ON` + `SESSION_CONTEXT`.
  - `path-traversal` — 13 malformed engagement ids rejected (`..`, backslashes,
    3-segment, uppercase, spaces, `;`, NUL, empty segment, over-long); crafted
    Event Grid blob subjects with `../` don't resolve to a valid (engagement, file)
    pair; derived blob prefixes carry no `..`.
  - `upload-content` — `uploads.classify` rejects `.xlsm` / `.exe` / `.js` / `.ps1`
    / `.7z`, a fake-`.xlsx` (HTML body), a binary-as-`.csv`; accepts real csv / pdf
    / png; `safe_name` strips `../` and separators.
  - `output-guard` — fabricated cost ($2.45M/yr), FTE (14), "Microsoft recommends
    ... $1,850/month", and person-days (5,200) are all flagged; two properly-cited
    numbers pass. (Added `FTE` to `_NUM` — "14 FTE" was under `_STRUCTURAL_MAX`.)
  - `system-prompt` — the 5 load-bearing instructions are present in
    `create_agent.SYSTEM_PROMPT` (no cross-engagement, reject-without-engagement,
    no invented slug, no unsourced number, no hand-designed topology).
  - **Pending** (in the SCORECARD, not gated — need E15.1 + a live agent):
    `mcp-injection`, `data-egress`, `live-jailbreak`.
- **`.claude/agents/landfall-judge.md`** — an `opus`, read-only (Read/Grep/Glob/
  Bash) subagent. Gate A: pytest + `evals/runner.py` exit 0 + no SCORECARD drift +
  `py311` + Playwright specs for UI changes. Gate B: diff → the right
  `azd deploy <service>`, **never `azd provision`** (schema.sql DROP), `create_agent.py`
  re-run when the tool contract changed, no new always-on resource, `prod`
  untouched. Gate C: tracker + pdca-log + memory updated + consistent cycle number,
  branch not `main`, commit trailer, `--no-ff` merge, LF phantom-diff check. Emits
  `VERDICT: GO | NO-GO` + blocking issues + a deploy plan.

### Check

| gate | result |
|---|---|
| unit | **466 pytest**, 2 skipped (+2 adversarial wrappers) |
| evals | `evals/runner.py` **exit 0** — golden 32/32, scenarios 8/8, faults 30/30, **adversarial 74/74** (3 pending) |
| scorecards | `evals/SCORECARD.md` + `evidence/SCORECARD.md` regenerated — **Security 3.75 → 4.0, overall 4.03 → 4.06** |
| drift | backtest / broken-dumps — untouched |
| bicep | n/a (no `infra/` change) |
| scope | evals + evidence + agent def + CI label + docs — **no `src/` runtime change → no deploy** |
| cost | $0 |

### Act

- `c47-adversarial` → merge `--no-ff` to `main`, push. **No `azd` deploy** (nothing
  under `src/` changed; `create_agent.py` unchanged).
- **Deferred:** the model-review half of E13.3 (needs a live agent version bump +
  token cost — a sponsor-run cycle).
- **Next by leverage:** E13.11 (safe teardown / rehydrate — the last P1 ephemeral
  guardrail) or E13.15 (the `tests/browser/` Playwright harness, so §4.17 has teeth).
- From here, run `landfall-judge` at the end of each cycle before commit/merge.

---

## Cycle 46 — master-prompt-v2 reconciliation + Playwright validation protocol

**Date:** 2026-09-10 · **Owner:** full panel (Azure AI architect · cloud-arch
director · FinOps · Python · Foundry · UI/UX · full-stack · DevSecOps) ·
**Tracker:** none — a planning pass the sponsor asked for after supplying
`prd/landfall_master_implementation_prompt_revised_v2.md` (a from-scratch strategic
brief proposing epics E14 + E15A–E15D). **Docs only — no code, no deploy.**

### Decide

- The brief overlaps the live repo heavily: **~60 % of its E14 P0/P1 asks are
  already done or already planned as Epic E13.** Adopting its E14/E15A–D numbering
  verbatim would fork the PRD — which the brief itself forbids ("preserve the
  existing repository structure; do not create duplicate PRD/tracker files").
- **Decision:** adopt the brief *in intent, not in numbering*. Map every item to
  done / covered-by-E13 / new-E13 / new-E15 / descoped (§4.16). Keep our numbers,
  keep `MONTHLY_BUDGET` in **INR** (not the brief's `MONTHLY_BUDGET_USD` — an INR
  sub would fire a `50` budget instantly).
- **`_v2` delta over the first file = §5A "External Reference Sources" only.** It
  pins the real Microsoft Learn MCP endpoint (`learn.microsoft.com/api/mcp`,
  public, no auth) → E15.1 is now concretely buildable; the MEG repo
  (`github.com/Azure/migration`) with an 8-step pin discipline; and two
  **proprietary** template URLs (AnalysisTabs, Smartsheet) — **not carried into any
  committed doc** (kept to the sponsor's private brief; the resource workbook is
  designed from the domain, not their layout).
- **Sponsor also asked (mid-pass):** validate every change with Playwright browser
  automation, tests driving the implementation → new **§4.17 protocol** + decision 18.

### Plan

- `engagement-workspaces-prd.md`: **§4.16** (reconciliation map — every E14/E15
  item → disposition), **§4.17** (Playwright validation protocol), **§5c** (Epic
  E15 work breakdown: E15.1–E15.4), extend **§5b** (E13.3 scope widened; E13.5 =
  centralized limits; new E13.13–E13.16), **§7** decisions 17 + 18, status line, §6
  cadence (C44–C47 rows + the per-cycle browser gate).
- `tracker.md`: progress table (E13 12→16; new E15 epic, 4 items), Epic E13 rows
  E13.13–E13.16, new Epic E15 section, cycle-46 delivery-log row.
- Memory: `landfall-5x5-execution.md` (item 2r + Key facts), `MEMORY.md`, and a
  note on the reconciliation + the Playwright gate.

### Do

- **§4.16** — 24-row disposition table. New E13 items: **E13.13** (`ca-calc`
  always-on → event-driven ACA **Job**, `minExecutions 0`, dormant param-gated —
  clears the §21 DoD + the best Container Apps Jobs learning exercise; ~$0 saving,
  the ACA free grant already covers `ca-calc` idle), **E13.14** (deterministic
  `run_assessment(engagement)` orchestrator — the LLM never drives the sequence;
  makes "same input → same estimate" trivial to assert). Auth-fail-closed (E14.3)
  folded into E13.11; ADLS-as-SoR + lab→enterprise matrix into E13.12; ruff/pyright
  is already E13.8; split-`app.py` is already E13.6.
- **E13.3 widened** to ~12 adversarial cases (incl. MCP-injection + customer-data-
  egress placeholders, wired live with E15.1) and confirmed **next by leverage** —
  the one remaining self-contained Security lever (Security 3.75; the external pen
  test needs a person).
- **§5c Epic E15** — E15.1 Learn MCP + governance (allow-list, per-turn call caps
  in the E13.5 config, graceful degradation, provenance, UX authority labels,
  same-cycle adversarial evals); E15.2 MEG (licensing spike *first* — output a
  go/no-go note, not code); E15.3 resource-demand model (demand deterministic,
  capacity user-supplied, never fabricate availability/rates/people, LLM never
  allocates FTE); E15.4 execution-readiness UX. **Principles locked now**, enforced
  by the E13.3 evals before the features exist.
- **§4.17** — per-change loop: local `uvicorn` + offline stubs → committed
  `tests/browser/<surface>` spec → `browser_navigate`/`snapshot`/`click`/`type`/
  `file_upload` → assert on snapshot text + **0 console errors** (a CSP violation
  shows here) + expected `/api/*` network calls → red→change→green with before/
  after screenshots in the PDCA Check step. 6 core regression journeys listed.
  Headless-in-CI is **E13.16** (needs E13.11 + OIDC); until then it's a mandatory
  manual gate evidenced by screenshots.

### Check

| gate | result |
|---|---|
| scope | docs + tracker + memory only — **no code, no deploy** |
| `tests/test_docs.py` | _run before commit_ |
| full `pytest` | _run before commit — expect 464 pass, unchanged_ |
| evals / SCORECARD | untouched — no drift expected |
| new cross-refs | §4.16 → E13/E15 items; §4.17 → E13.15/E13.16; decisions 17/18 |

### Act

- Next: **C47 = E13.3** (`evals/adversarial.py`, ~12 cases, CI gate) — the last
  buildable-solo Security item; then E13.11 (safe teardown / rehydrate).
- Epic E15 stays roadmap until the E13 architecture block is clear.
- From C47 on, every UI cycle carries a `tests/browser/` spec + screenshots.

---

## Cycle 45 — fix the red `evals` CI (Python 3.11 f-string) + a compat guard

**Date:** 2026-09-10 · **Owner:** SRE ·
**Tracker:** none — a CI break the user spotted. The `evals` workflow "Unit
tests" step (`pytest tests -q`) had been **failing at collection since C38**
(`33a5442`, 2026-09-09), which also skipped every eval gate after it (recalc,
harness, backtest, broken-dumps, scorecard drift). Not caught locally because
**`.venv2` is Python 3.13** and **CI + the Function App runtime are 3.11**.

### Plan

- Fix the syntax error; scan the whole tree for the same class; add a test that
  fails on 3.12-only syntax regardless of the local interpreter; confirm the
  now-unblocked eval gates are actually green.

### Do

- **`scripts/export_all.py:197`** — `f"…{f', {r['sql_rows']} sql rows' if … else ''}"`
  is a **nested same-quote f-string with a `'`-subscript inside** → `SyntaxError:
  f-string: unmatched '['` on Python < 3.12 (legal only under PEP 701). Lifted
  the conditional to a `sql_note` local.
- **`tests/test_py311_compat.py`** (NEW) — `ast.parse(src, feature_version=(3, 11))`
  over every `.py` in `scripts/ src/ tests/ evals/ evidence/` (130 files). Fails
  here, on any interpreter, if a file uses 3.12+ syntax.
- Verified the eval gates that hadn't run in CI since C38: `backtest/RESULTS.md`,
  `broken-dumps/`, `evidence/SCORECARD.md`, `evals/SCORECARD.md` — **all clean**
  (the CI was skipping them, not that they'd drifted).
- CI stays on **3.11** — that is correct: `infra/resources.bicep` sets the
  Function App runtime to `python 3.11`, so CI matches production. The gap was
  dev-side (`.venv2` = 3.13); the compat test bridges it.

### Check

| gate | result |
|---|---|
| unit | **464 pytest**, 2 skipped (+1 `test_py311_compat`) |
| 3.11 syntax | `ast.parse(feature_version=(3,11))` clean across 130 files |
| eval gates | backtest / broken-dumps / both SCORECARDs — no drift |
| scope | one-line script fix + a test → **no deploy** |

### Act

- `c45-ci` → merged to `main`, pushed. Watch the `evals` run go green.
- Recorded the **3.11 CI / 3.13 local** gap in memory so future cycles run the
  compat test (it is in the default suite now).

**Date:** 2026-09-09 · **Owner:** FinOps + SRE ·
**Tracker:** E13.4, promoted to P1 by §7 decision 16 (sponsor: **$40–50/month,
deployed on demand with `azd up` / `azd down --purge`, `free` tier only**; also a
learning vehicle for Foundry / ACA / enterprise design).

### Plan

- Put a real cost guardrail in the **default `azd up`** — a budget + alert, an
  ingestion cap, a `ca-calc` replica knob — so an ephemeral deploy is protected
  from minute one without a param dance.
- A `scripts/spend.py` so the sponsor can *see* month-to-date spend vs budget
  (also: hands-on Azure Cost Management, a stated learning goal).
- No `azd provision` (drops SQL) — ships dormant; the sponsor's next fresh
  `azd up` picks it up.

### Do

- **`infra/main.bicep` + `infra/resources.bicep`** — new params
  `monthlyBudget int = 50`, `budgetStartDate string = utcNow('yyyy-MM-01')`,
  `logAnalyticsDailyCapGb string = '0.5'`, `calcMinReplicas int = 1`, threaded
  through the module.
  - `resource costBudget 'Microsoft.Consumption/budgets@2023-11-01' = if (monthlyBudget > 0)`
    — RG-scoped, `timeGrain: Monthly`, three notifications: **actual ≥ 50 %**,
    **actual ≥ 80 %**, **forecast ≥ 100 %**; each notifies `contactEmails`
    (`alertEmail` if set) **and always `contactRoles: ['Owner']`** so it works out
    of the box.
  - Log Analytics `workspaceCapping.dailyQuotaGb = isProd ? -1 : json(logAnalyticsDailyCapGb)`.
  - `ca-calc` scale `minReplicas: calcMinReplicas` (was hard `1`). Default stays 1
    — C25b proved KEDA MI-auth doesn't scale the worker *up* on a queued job, so
    `0` risks an unprocessed POE run; documented as a knob, not defaulted.
- **`infra/main.parameters.json`** — `${MONTHLY_BUDGET=50}`,
  `${LOG_ANALYTICS_DAILY_CAP_GB=0.5}`, `${CALC_MIN_REPLICAS=1}`.
- **`scripts/spend.py`** (NEW — named `spend`, not `cost`, to dodge the
  `src/api/cost` package collision in the test namespace, cf. C40/C42). Stdlib +
  `az rest` against the **Cost Management query API** (no `costmanagement` CLI
  extension needed; one retry on HTTP 429). Month-to-date **actual** cost for the
  RG, % of budget now + projected (MTD ÷ day × days), a verdict (OK / WATCH /
  OVER), top cost by resource type, and a currency note.
- **`DEPLOY.md`** — "Cost guardrails (E13.4)" subsection: the table, the levers
  (never `prod` first; `azd down --purge`; VS spending limit), `scripts/spend.py`.
- **`tests/test_cost_guardrail.py`** (8) — params declared + threaded; budget
  default-on with 3 thresholds + Owner role; the LA cap + `ca-calc` knob;
  `az bicep build` compiles with `Microsoft.Consumption/budgets` + `Forecasted`
  + `workspaceCapping`; `spend.py` projection math + verdict boundaries + the
  no-RG exit path.

**Grounded the cost live** (`scripts/spend.py` against `rg-landfall`): the
subscription is **VS Enterprise, billed in INR**; month-to-date **~₹384 ≈
$4.5/mo projected** with the stack up ~9 days. The earlier "$35–65/mo always-on"
estimate was **wrong** — the ACA free grant absorbs `ca-calc` idle; real
always-on is **~$5–12/mo**. §4.15 + decision 16 + the memory corrected. So the
budget has huge headroom and the one real risk is `DEPLOYMENT_TIER=prod`. The
`MONTHLY_BUDGET` param + `--budget` are in the **billing currency** (INR here),
not USD — documented, and `spend.py` prints the currency.

### Check

| gate | result |
|---|---|
| unit | **463 pytest**, 2 skipped (+8 `test_cost_guardrail`; `spend.py` renamed from `cost.py` — collision) |
| bicep | `az bicep build infra/main.bicep` rc 0; ARM carries the budget (default 50), the forecast notification, the LA cap, `calcMinReplicas` (default 1) |
| live | `scripts/spend.py --rg rg-landfall` → currency INR, MTD ₹115 (day 9), projected ₹384 ≈ $4.5/mo |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` unchanged (a cost guardrail isn't a 5/5-rubric dimension) |
| scope | infra params + a script + docs → **no deploy, no `azd provision`**. Ships on the next `azd up`. |

### Act

- `c44-cost` → merged `--no-ff` to `main`, pushed. No `azd` anything.
- PRD §4.15 (cost table rewritten with the grounded numbers) + decision 16 +
  E13.4 row + tracker updated. The sponsor: `azd env set MONTHLY_BUDGET 4200`
  (INR) + `azd env set ALERT_EMAIL …` then `azd up`; and check the VS
  **spending limit** is on.
- Next: **E13.11** (one-command safe teardown / rehydrate — and it must first
  make `azd up` reproduce `ca-drawio` + web Easy Auth, which are param-gated
  off today); or E13.12 (`docs/learning-path.md`).

---

## Cycle 43 — expert-panel review (Epic E13) + guided pipeline state (E13.2 / E12.8)

**Date:** 2026-09-09 · **Owner:** panel (AI architect · cloud-arch director · FinOps ·
Python · Foundry · UI/UX · full-stack) ·
**Ask:** *"you are a team of experts — decide, plan, do, study, act; update
`prd/engagement-workspaces-prd.md`."*

### Plan (DECIDE)

Second full-panel review of the whole solution (engine complete, 4.03/5, E11 live,
E12 6/12). Question posed: *the highest-leverage buildable work left, every
discipline* — not another cosmetic pass. Ten findings → **Epic E13** (PRD §4.14
findings table + §5b work breakdown + §7 decision 15):

1. **`schema.sql` DROP+CREATEs the 6 tables on every `postprovision`** — `azd
   provision` wipes all engagement data, which blocks the *entire* provision-gated
   backlog (C39 workbook+alert, C42 web alert, E9.3 prod live, E11.22 infra,
   E12.11 hostname). **E13.1 — the keystone.**
2. **No guided pipeline state** (was E12.8) — chat is live before any inventory;
   nothing sequences Inventory → Analysis → Estimate → POE. **E13.2 — pulled
   forward, top user-facing item, C41 unblocked it.**
3. Agent still on `gpt-4o`; no current-gen model eval; no adversarial-prompt eval
   (fault injection = data faults, not prompt-injection → tool abuse). **E13.3.**
4. No budget/cost alert on Landfall's own spend; `ca-calc` 2vCPU/4GiB always-on
   (~$70-90/mo). **E13.4.**
5. No agent-run ceiling (runaway tool loop / unbounded response-id chain). **E13.5.**
6. `src/web/app.py` ~1060 lines, one module. **E13.6.**
7. `dashboard.html` + `questionnaire.html` still inline → relaxed CSP. **E13.7.**
8. No lint/type gate in CI. **E13.8.**
9. E12 tail: E12.9 / E12.10 / E12.12. **E13.9.**
10. Single-region / no-DR is unrecorded. **E13.10 — write the decision.**

**Sequencing:** E13.1 first (no deploy — sponsor runs the first safe provision);
E13.2 this cycle (shippable); E13.3-5 next (guardrails); E13.6-8 sustain.

### Do — E13.2 (guided pipeline state)

- **`app.py`** — `GET /api/engagements/{c}/{p}/pipeline`: aggregates the 4-step
  state (`uploads` from `_list_files`, `analysis` from `_analysis_summary`,
  `estimate` from `latest.json`, `poe` from `landing_zone.json` `status`), each
  step carrying `waiting_on`; returns `next` + `analysed`.
- **`chat.html`** — `<div id=pipeline class=pipe hidden>` above the log.
- **`chat.css`** — `.pipe` strip: done (✓, green) / next (▸, teal outline) /
  to-do (dimmed) chips + a `.hint` "Next: <action>" line.
- **`chat.js`** — `loadPipeline()` renders it; called from `showUpload()` (on
  select/create), after `startAnalysis()`, and after every chat turn. A one-time,
  **non-blocking** assistant note when `ask()` runs with `PIPE.analysed===false`
  ("no inventory analysed yet … I'll still answer general questions"). `HINTED`
  resets on engagement switch. All in the external asset — strict CSP holds.
- **`tests/test_pipeline.py`** (7) — empty = all to-do; inventory advances to
  analysis (waiting_on clears); a dq report with rows marks analysis done;
  published estimate + POE = all done; POE `building` ≠ done; 404 unknown;
  the chat page wires the strip + the nudge.

### Check

| gate | result |
|---|---|
| unit | **455 pytest**, 2 skipped (+7 `test_pipeline`) |
| local | `/pipeline` returns the right 4-step state across empty / uploaded / analysed / published / POE-building; `/` + assets keep the strict CSP; no inline style/script |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` unchanged (Usability 2.0 needs the trials — a strip doesn't move the number, it makes the eventual trial pass) |
| live | `azd deploy web` → SUCCESS (1m52s), revision Healthy; `scripts/smoke.py` **8/8**; `GET …/pipeline` returns `401` behind Easy Auth (routed, not a 404) |
| scope | PRD + **production web code** → `azd deploy web` (no infra, no agent change, no eval change) |

### Act

- `c43-pipeline` → merged `--no-ff` to `main` (`3164c0f`), pushed. **`azd deploy web`.**
- PRD updated: §4.14 (E13 review) + §5b (E13 breakdown) + §7 decision 15 + C43
  cadence row + status line. `tracker.md`: Epic E13 section, E12.8 → done,
  progress rows, cycle-43 index row.
- Next by leverage: **E13.1** (idempotent `schema.sql` — the keystone; no deploy,
  unblocks 5 items) or E13.3 (model + adversarial evals) or the human trials.

---

## Cycle 42 — web-tier log + request forwarding (E9.4)

**Date:** 2026-09-09 · **Owner:** SRE ·
**Tracker:** the E9.4 remaining gap. The API tier forwards structured telemetry
(C39); the web tier had the App Insights connection string as an env var but
forwarded nothing — a chat handler exception (`log.exception("chat failed")`, a
500 to the user) never left the container. Operability's lowest-hanging item and
the one part of "can an operator see a bad answer" still missing.

### Plan

- Wire `azure-monitor-opentelemetry` in the web container — auto-instrument
  FastAPI (`requests` per route, matching the Functions tier) + forward logs.
- Emit a structured `web_chat` event per `/api/chat` turn, mirroring
  `query_inventory`: status, latency, citation/table counts, hashed engagement.
- No-op without the connection string so local + tests are untouched; no infra
  change (the env var is already on `ca-web`).

### Do

- **`src/web/telemetry.py`** (NEW) — `configure_telemetry()` calls
  `configure_azure_monitor(logger_name="landfall")` only when
  `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, in a `try/except` (the SDK
  isn't in `.venv2`, and a telemetry misconfig must not stop the app).
  `event(name, **dims)` writes a flat `extra=` record (OTel maps it to
  `customDimensions`; the Functions `custom_dimensions` nesting doesn't apply
  here) with reserved-key guarding. `eng_hash()` as in `src/api/obs.py`.
  Named `telemetry` not `obs` — `import obs` would collide with `src/api/obs.py`
  in the test namespace (same class of bug as C40's `probe.py`).
- **`src/web/app.py`** — `import telemetry as _obs`; `_obs.configure_telemetry()`
  at import; all `logging.exception/​warning` → a `log = getLogger("landfall.web")`
  module logger (so `logger_name="landfall"` captures them). `chat()` emits
  `web_chat` on every exit: `agent_unconfigured` (503), `unknown_engagement`
  (404), `empty_agent_response` (502), `error` (500), `ok` — each with `ms`.
- **`src/web/requirements.txt`** — `azure-monitor-opentelemetry>=1.6,<2`.
- **`tests/test_web_telemetry.py`** (7) — no-op without the string; never raises
  when the SDK is absent; flat record + reserved-key guard; `eng_hash` stable +
  not the raw id; `event` swallows bad input; `chat()` emits `web_chat` on the
  unconfigured path; source has all five status strings.
- **`evidence/chaos/probe.py`** — C6 check `logging.exception(` → `.exception(`
  (the call moved to the module logger).
- **`docs/observability.md`** — `web_chat` in the traces list, two KQL queries
  (failed turns, chat p50/p95), the web-tier forwarding note; "Not yet" now =
  workbook row + web alert.
- **`evidence/scorecard.py`** — Operability **4.25 → 4.5**; basis + gap updated.

### Check

| gate | result |
|---|---|
| unit | **448 pytest**, 2 skipped (+7 `test_web_telemetry`, chaos C6 check fixed) |
| local | `import app` OK with `telemetry` no-op; `web_chat` record is flat, `None` dropped, reserved keys not shadowed |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated — **OVERALL 4.00 → 4.03** |
| live | `azd deploy web` → SUCCESS (1m50s), revision Healthy. `scripts/smoke.py` **8/8**. Container logs confirm `azure.monitor.opentelemetry.exporter` — *"Transmission succeeded: Items accepted: 8"* — telemetry is flowing to App Insights. |
| scope | **production web code** → `azd deploy web` (no infra — env var already present) |

### Act

- `c42-webobs` → merged `--no-ff` to `main` (`a0b6b4f`), pushed. **`azd deploy web`.**
- E9.4 gap now just: the workbook row + a web-tier alert (both need `azd
  provision`, which drops SQL — deferred with the C39 workbook/alert).
- Next by leverage: E12.8 guided pipeline state (Usability, unblocked by C41),
  or the human trials (need people), or fold the workbook/alert + `web_chat`
  into one `azd provision`-gated cycle.

---

## Cycle 41 — chat page → static shell + strict CSP (E12.7)

**Date:** 2026-09-09 · **Owner:** FS ·
**Tracker:** E12.7. The `index()` route returned a ~420-line triple-quoted HTML
string with an inline `<style>` and `<script>` — so `/` could carry no CSP, and
it blocks E12.8/E12.9 (guided pipeline / progress) which need real DOM code.
Also the one open self-assessment finding (T9 — no CSP / `nosniff`).

### Plan

- Externalise the chat page: `chat.html` shell + `/static/chat.{css,js}`, no
  inline script or style, so `/` can run `script-src 'self'; style-src 'self'`.
- Add a security-headers middleware (nosniff / frame / referrer on everything;
  strict CSP on the static surface, relaxed CSP where inline still exists).
- Keep behaviour byte-identical — pure extract + 4 `style=` attrs → classes.

### Do

- **`src/web/chat.html`** — the shell (`<link rel=stylesheet href=/static/chat.css>`
  + `<script src=/static/chat.js>`), 3 inline `style=` attrs → `.mini .full .link`,
  `.utabs .lbl`, `.utabs .grow`.
- **`src/web/static/chat.css`** — the `<style>` block verbatim + the 4 new rules
  (incl. `.intro p.sub.eng` replacing a JS-built `style="color:#7fd3dd"`).
- **`src/web/static/chat.js`** — the `<script>` verbatim, that one `style=` in a
  built `innerHTML` string → `class="sub eng"`. Every `el.onclick=` /
  `el.style.x=` is a DOM property, fine under CSP.
- **`src/web/app.py`** — `index()` now `read_text("chat.html")`; a whitelisted
  `GET /static/{name}` route (`.css`/`.js` only, single segment, must resolve
  inside `static/`, `max-age=300`); `_security_headers` HTTP middleware:
  `_CSP_STRICT` (no `unsafe-inline`) on `/` + `/healthz` + `/static/*`,
  `_CSP_RELAXED` (keeps `unsafe-inline`; still `frame-ancestors`/`base-uri`/
  `object-src 'none'`) elsewhere, plus `X-Content-Type-Options: nosniff` +
  `X-Frame-Options: DENY` + `Referrer-Policy`. `app.py` −357 lines.
- **`tests/test_web_csp.py`** (6) — `/` is the file on disk, no `<style>`/inline
  `<script>`/`style=` in the body; strict CSP on `/` + assets; headers on every
  response; the relaxed CSP still locks framing; the static route rejects `.py`
  + real-but-wrong-ext + traversal. `tests/test_dashboard.py` (2) +
  `tests/test_upload.py` (5) — assertions on the page's JS/CSS repointed to
  `/static/chat.{js,css}`.
- **`evidence/pentest/sec_probe.py`** — `_headers_hygiene` now also checks
  `X-Frame-Options` + a `unsafe-inline`-free CSP on `/`.
- Docs: `threat-model.md` T9, `RESULTS.md` T9, `scorecard.py` Security basis.

### Check

| gate | result |
|---|---|
| unit | **441 pytest**, 2 skipped (+6 new in `test_web_csp.py`, 7 repointed in `test_dashboard`/`test_upload`) |
| local | `TestClient`: `/` serves the file, strict CSP + nosniff + DENY; `/static/chat.css\|js` 200 with the right MIME + strict CSP; `/static/x.py` + `/static/prompt_cards.json` + traversal → 404; `/dashboard` keeps the relaxed CSP |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated (scores unchanged — Security stays 3.75, needs external validation) |
| live | `azd deploy web` → SUCCESS (1m37s). `scripts/smoke.py` **8/8** against `rg-landfall`. `sec_probe.py` **16/16** — the CSP/nosniff checks degrade to an info note (Easy Auth answers `401` before the app, so app headers aren't black-box visible; `test_web_csp.py` covers them). |
| scope | **production web code** → `azd deploy web` (no infra) |

### Act

- `c41-csp` → merged `--no-ff` to `main` (`c612e40`), pushed. **`azd deploy web`.**
  Follow-up evidence commit `aaaee9f` (live probe re-run + `_headers_hygiene`
  degradation note).
- E12.7 done; Epic E12 now 6/12. The T9 self-assessment finding is closed for
  the chat surface. Follow-up (logged on the E12.7 row): give `/dashboard` +
  `/questionnaire` the same treatment so they earn the strict CSP too.
- Next by leverage: the human trials (Usability 2.0 / Understandability 3.0,
  need participants), or E12.8 guided pipeline state (now unblocked), or
  web-tier log forwarding (Operability 4.25).

---

## Cycle 40 — security self-assessment + `ca-web` auth into Bicep (E8 / E10.4 pentest)

**Date:** 2026-09-09 · **Owner:** Security ·
**Tracker:** the `pentest/` third of E10.4 + the T5 gap it surfaces. Security is
the lowest "built" dimension (3.5); the trials and the external pen test need
people, but the threat model + a self-assessment baseline don't.

### Plan

- Write the threat model an external tester needs to scope fast.
- Run an automated non-destructive baseline against the live deployment.
- Fix what the baseline surfaces that I can — the imperative `ca-web` auth.

### Do

- **`evidence/pentest/threat-model.md`** — 5 assets, 6 trust boundaries
  (browser→web, web→agent, agent→Function, Function→SQL, Function→ADLS, the two
  side-car containers), 9 STRIDE-ish threats (T1 cross-engagement read … T9
  response hardening) each with the control + residual, and "start here"
  pointers (RLS bypass, prompt-injection→tool abuse, the web-auth gap).
- **`evidence/pentest/sec_probe.py`** — 16 non-destructive checks: unauth HTTP
  on `ca-web` `/`,`/dashboard`,`/api/*`,`/healthz`,`/questionnaire` + `func-*`
  three routes (**all 401 live**); HSTS / no version banner / nosniff; the SQL
  guard against 11 injection/write/DDL/stacked/`OPENROWSET`/`sys.` payloads
  (11/11 rejected) + comment-trick neutralisation (2/2) + a legit query still
  allowed; `normalize_engagement` against 8 traversal slugs (0 escaped);
  `git grep` for committed secrets (clean). **15/16 pass** — the one finding is
  no CSP / `X-Content-Type-Options` on app responses, which folds into E12.7.
  (Renamed from `probe.py` → `sec_probe.py` to not collide with
  `evidence/chaos/probe.py` in the test import namespace.)
- **`evidence/pentest/RESULTS.md`** + `README.md` — the run + the known open
  items table (T5 web-auth, T6 unpinned func audience, T8 SQL public network, T1
  group-claims untested).
- **infra — T5 fix.** `ca-web` EasyAuth was configured with `az containerapp
  auth` only, not in Bicep, so a fresh `azd up` brought the web app up with **no
  auth**. Added `webAuthClientId` + `webAuthClientSecret` (`@secure`) params →
  a `Microsoft.App/containerApps/authConfigs` resource (`RedirectToLoginPage`,
  tenant-restricted audience) + an app secret, all gated on
  `var hasWebAuth = !empty(webAuthClientId)`. Empty (default) = **no change** to
  today's deploy. `main.parameters.json` wires `${WEB_AUTH_CLIENT_ID=}` /
  `${WEB_AUTH_CLIENT_SECRET=}`. `DEPLOY.md` follow-up 1 rewritten with the IaC
  path (set the two env vars → `azd provision`) alongside the imperative one.
- **`tests/test_pentest.py`** (6) — the guard rejects every `_INJECTION`,
  slug + secret checks pass, `R.to_dict().ok` is severity-gated, the threat
  model covers the boundaries, the `authConfigs` is param-gated with the empty
  default unchanged.
- **`evidence/scorecard.py`** — Security 3.5 → **3.75**. **Overall 3.97 →
  4.00.** `.gitattributes` pins `evidence/pentest/*.json`.

### Check

| gate | result |
|---|---|
| unit | **435 pytest** (+6), 2 skipped |
| live probe | 16 checks, 15 pass; the 1 finding is a known E12.7 item; `probe-result.json` |
| bicep | `az bicep build infra/main.bicep` rc 0; `authConfigs` gated on `hasWebAuth`, empty default = no resource |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated |
| scope | evidence + docs + param-gated Bicep → **no deploy** (the web-auth Bicep needs `azd provision` + `WEB_AUTH_CLIENT_ID`, not run) |

### Act

- One commit on `c40-pentest`, merged `--no-ff` to `main` (`dee5ddb`), pushed.
  No `azd` anything.
- **Overall is 4.00/5.** The remaining ~1.0 is: Usability 2.0 + Understandability
  3.0 (need trial participants), Defensibility + Completeness 4.0 (architect
  review board), Operability 4.25 (E9.2 CI secrets + web-log forwarding + chaos
  induce), Security 3.75 (external pen test + CISO signature + E8.5).
- Next: **E8.5** private endpoints (the last thing I can build toward Security —
  large param-gated Bicep, no deploy), or the web-tier log forwarding
  (Operability), or hand back to the user that the rest is gated on people.

---

## Cycle 39 — answer-quality observability (E9.4)

**Date:** 2026-09-09 · **Owner:** SRE ·
**Tracker:** E9.4 — the last Phase-1 Engine backlog item. "An operator can see a
bad answer; tool error rate alerts."

### Plan

- Emit just enough structured telemetry that an operator can slice answer
  quality — without a new SDK or a risky rewrite. Lean on what Azure Functions
  already emits (`requests` per invocation) and add a thin structured-event layer
  for the two things `requests` can't show: `query_inventory` outcome detail and
  the confidence mix of published estimates.
- Ship the dashboard as an App Insights workbook + a KQL runbook + a
  param-gated failure-rate alert, all in Bicep.

### Do

- **`src/api/obs.py`** — `event(name, **dims)` → `logging` with
  `extra={"custom_dimensions": ...}` (the Functions App-Insights handler maps it
  to `customDimensions`; no dependency). `eng_hash()` = SHA-256 prefix so the raw
  customer/project never reaches telemetry. Every call best-effort.
- **`src/api/tools.py::query_inventory`** — times the call; emits a
  `query_inventory` event on each exit path (`ok` with rows/shape/tables,
  `rejected` with the reason, `text_to_sql_error`, `query_error`).
- **`src/api/deliverable/functions.py`** — `_obs_estimate()` on assemble +
  publish: `estimate_assembled` with `overall_confidence` and the
  `low`/`medium`/`high` figure counts, so Low-confidence deliverables are
  visible in aggregate.
- **`infra/workbook-answer-quality.json`** + `resources.bicep` — a
  `Microsoft.Insights/workbooks` (tool volume / failures / p95 from `requests`,
  `query_inventory` outcomes, the 7-day confidence-mix table, recent errors,
  failures by tool + code). ASCII-only (a `⚠` crashed `az bicep` on Windows
  cp1252). A param-gated (`alertEmail` / `ALERT_EMAIL`)
  `scheduledQueryRules` alert — Function failure rate > 5% over 15 min — + its
  action group; workbook always deploys, alert only when the email is set.
- **`docs/observability.md`** — the two signals, the workbook, a copy-paste KQL
  runbook for "is an answer bad?", the arming step, and the known gap (web-tier
  logs are not forwarded — needs `azure-monitor-opentelemetry`).
- **`tests/test_obs.py`** (7) — hash stable/opaque/case-folded, event shape +
  None-drop + stringify, never raises, the `query_inventory` wiring fires on a
  rejected query, the workbook JSON is valid + ASCII + queries the right tables,
  the observability Bicep is wired through main → module → params.
- **`evidence/scorecard.py`** — Operability 4.0 → **4.25**. **Overall 3.94 →
  3.97.** `.gitignore` gets `!infra/workbook-answer-quality.json` (the blanket
  `infra/*.json` ignore for the compiled output was hiding it).

### Check

| gate | result |
|---|---|
| unit | **429 pytest** (+7), 2 skipped |
| obs wiring | `query_inventory` emits without breaking the tool (400 still returned); event carries a hashed engagement, not the raw id |
| bicep | `az bicep build infra/main.bicep` rc 0; workbook always, alert + action group gated on `hasAlert` |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated |
| scope | `src/api` changed → `azd deploy api`; workbook/alert are Bicep-only (need `azd provision`, not run) |

### Act

- One commit on `c39-observability`, merged `--no-ff` to `main` (`8fe6e84`),
  pushed. `azd deploy api` (obs wiring — 3 additive best-effort call sites).
- **Phase 1 Engine backlog is now 0.** Operability is 4.25 → 5.0 needs: the
  E9.2 CI armed + green on both OSes (OIDC secrets, not doable here), the
  web-tier log forwarding, and C2–C6 induced end-to-end.
- Next by scorecard leverage: **E8.5** private endpoints (Security 3.5 — the
  lowest remaining "built" dimension), or the E10.4 human trials
  (Usability 2.0 / Understandability 3.0).

---

## Cycle 38 — close-out export + chaos drill (E9.5 + evidence/chaos/)

**Date:** 2026-09-09 · **Owner:** SRE ·
**Tracker:** E9.5 + the chaos-drill part of E10.4 — the last two Operability
gaps that don't need GitHub secrets (E9.2) or a new subsystem (E9.4).

### Plan

- E9.5: a script that retains every engagement before `azd down --purge`.
  E11.26 already exports one engagement over HTTP; E9.5 is "all of them, from an
  operator shell, including a SQL dump".
- Chaos drill: document + probe how the system degrades when each critical-path
  dependency is down. Induce what's safe on the shared env; inspect the rest.

### Do

- **`scripts/export_all.py`** — `list_engagements` (blobs matching
  `engagements/*/*/_engagement.json` in `raw`), then per engagement a
  `zipfile` of `raw/engagements/<eid>/**` + `answers/engagements/<eid>/**` +
  `export.json`, same format as the web export so it re-imports via
  `POST /api/engagements/import`. `--sql` adds `sql/<table>.csv` for the six
  tables — **binds `sp_set_session_context 'engagement_id'` first** (RLS fails
  closed, so a naive `WHERE engagement_id = ?` returns 0 rows). `_sql_connect`
  retries 5 × 20 s while a paused serverless DB resumes. A SQL failure is caught
  per engagement — `sql/_ERROR.txt` in the zip, blob export still written (raw/
  is the source of truth and re-ingests on import). `--dry-run` lists + sizes.
  **Live:** `_default_/_default_` → 532 KB, 1 raw + 12 answers + **6,498 SQL
  rows**, retried through the auto-pause → `evidence/ops/closeout-example.json`.
- **`DEPLOY.md`** — "Close-out — export before you tear down (E9.5)" under the
  per-engagement section.
- **`evidence/chaos/`** — `scenarios.md`: 6 failure modes (C1 SQL auto-pause,
  C2 ca-drawio at zero, C3 ca-calc down, C4 Retail Prices API unreachable,
  C5 `AGENT_ID` unset, C6 model 429) — expected degradation, the code path, the
  induce command. `probe.py` (non-destructive) reads Azure state + the code and
  confirms each mitigation → **7/7**. `RESULTS.md`: C1 **induced + observed**
  this session (smoke saw `Paused`; `export_all --sql` hit "not currently
  available", retried, resumed in ~40 s); C2 **partially induced** (ca-drawio
  live at `minReplicas 0`, cold-start retry in `render.py` was itself a real
  incident fix); C3–C6 **verified by inspection**. Governing rule stated: a down
  dependency → a slow/partial answer with a reason, never a wrong one.
- **`tests/test_export_all.py`** (6) — enumerate, zip raw+answers, skip empties,
  SQL-failure-keeps-blobs, dry-run writes nothing, one zip per engagement.
  **`tests/test_chaos.py`** (3) — probe reports all mitigations, docs exist, and
  a removed mitigation (drop the SQL retry) fails C1.
- **`evidence/scorecard.py`** — Operability 3.75 → **4.0**. Basis rewritten;
  E9.5 + chaos struck from the gap; evidence links updated. **Overall 3.92 →
  3.94.** `.gitattributes` pins `evidence/chaos/*.json`.

### Check

| gate | result |
|---|---|
| unit | **422 pytest** (+8), 2 skipped |
| close-out (live) | 6,498 rows + 13 blobs zipped for `_default_`; SQL retry resumed a paused DB |
| chaos probe | 7/7 mitigations in place; `test_chaos` proves a removed one is caught |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated |
| scope | operator script + evidence + docs → **no deploy**, no prod code, no infra |

### Act

- One commit on `c38-closeout-chaos`, merged `--no-ff` to `main` (`5b92081`),
  pushed. No `azd` anything.
- Operability is 4.0. To 5.0: arm + green the E9.2 CI on both OSes (needs the
  OIDC secrets — not doable here), **E9.4** answer-quality observability, and
  induce C2–C6 end-to-end on a scratch env.
- Next by scorecard leverage: **E9.4** (observability — traces + dashboard +
  alerts, the last Operability build item) or **E8.5** (private endpoints,
  Security 3.5) or the E10.4 human trials.

---

## Cycle 37 — `DEPLOYMENT_TIER` switch: one flag off the Free tiers (E9.3)

**Date:** 2026-09-09 · **Owner:** SRE ·
**Tracker:** E9.3 — "one switch moves off Free tiers; delta documented". The next
Operability gap after E9.2.

### Plan

- Add a Bicep param that flips every Free-tier / Free-offer resource to its paid
  equivalent, default unchanged, `free` branch byte-identical to today.
- Document the per-resource cost delta + the in-place-conversion gotchas.
- Do **not** run `azd provision` — its postprovision hook drops the SQL schema.

### Do

- **`infra/main.bicep`** — `param deploymentTier string = 'free'`
  (`@allowed(['free','prod'])`), passed to the `resources` module.
- **`infra/resources.bicep`** — `var isProd = deploymentTier == 'prod'`, then:
  AI Search `sku free → basic` + `replicaCount 1 → 2` (99.9 % SLA);
  SQL DB properties via `union({...}, isProd ? {} : {useFreeLimit, ...})` —
  `autoPauseDelay 60 → 1440`, `minCapacity 0.5 → 1`, `maxSizeBytes 32 → 100 GB`,
  free-limit dropped; ACR `Basic → Standard`; storage `Standard_LRS → ZRS`;
  web Container App `scale 0→2` → `1→4` (a replica stays warm); Log Analytics
  `retentionInDays 30 → 90`.
- **`infra/main.parameters.json`** — `"deploymentTier": { "value":
  "${DEPLOYMENT_TIER=free}" }`.
- **`DEPLOY.md`** — new "Deployment tiers (`DEPLOYMENT_TIER`)" section: the
  free-vs-prod table with a ~monthly delta per resource (**~+$300–450/mo**,
  dominated by Search `basic` and SQL leaving the Free offer), what `prod` does
  *not* touch (private networking / the SQL firewall = E8.5), and the
  conversion caveat — AI Search and the SQL free-limit are a resource
  **replace**, so a fresh `azd up` is clean but converting in place needs
  `setup_search.py` re-run and an engagement export first.
- **`tests/test_infra_tier.py`** (4) — param declared + threaded through
  main→module→params; each Free-tier resource gated with the free branch
  unchanged; DEPLOY.md documents the delta; `az bicep build` compiles and the
  ARM carries both branches (`skipif` no `az`).
- **`evidence/scorecard.py`** — Operability 3.5 → **3.75**; basis + evidence +
  gap updated (E9.3 struck). **Overall 3.89 → 3.92.**

### Check

| gate | result |
|---|---|
| unit | **414 pytest** (+4), 2 skipped |
| bicep | `az bicep build infra/main.bicep` exit 0, no warnings; ARM has the `deploymentTier` param (allowed free/prod, default free) + both SKU branches |
| free branch | every conditional's `free` value == today's literal (LRS, `free`, `Basic`, 60, 30, minReplicas 0) — no change to the current deploy |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated |
| scope | Bicep param-gated, `free` default → **no deploy**; `azd provision` deliberately not run |

### Act

- One commit on `c37-tier-prod`, merged `--no-ff` to `main` (`8e2afc4`), pushed.
  No `azd` anything — the live env stays on `free` and is untouched.
- E9.3 `in-review` (a live `prod` provision has not been exercised — it would be
  a new env, not the shared one). Operability's remaining gaps: arm the E9.2 CI,
  E9.4 observability, E9.5 export-before-teardown, a chaos drill.
- Next by scorecard leverage: **E9.4** (answer-quality observability — traces +
  dashboard + alerts, lifts Operability again) or **E8.5** (private endpoints,
  lifts Security), or run the E10.4 human trials.

---

## Cycle 36 — D2 "How Landfall works" walkthrough + comprehension trial kit (E10.4)

**Date:** 2026-09-09 · **Owner:** Writer + PM ·
**Tracker:** D2 + E10.4 — Understandability was 2.0 (docs existed, no "how it
works" page, no trial). The biggest single lever left to 5/5.

### Plan

- Write D2: the read-first orientation doc — pipeline, tools, answer contract,
  confidence model, DRAFT boundary, worked example over the sample estate.
- Build the trial apparatus so the two human trials (comprehension +
  usability) are turnkey; dry-run the comprehension task set to shake it out.
- Score the Build half honestly; the Proof half (3 people) still gates 5/5.

### Do

- **`docs/how-landfall-works.html`** (D2, reuses the SOP stylesheet) — 7
  sections: what Landfall is/isn't; the 5-stage pipeline + a note on tenancy;
  the 12 tools table; the answer contract (F-id + basis + confidence + band +
  top-3 drivers); the confidence model (High/Medium/Low triggers **+ the
  cost-figures-capped-at-Low-by-design rule** the dry run surfaced); the DRAFT
  boundary (a two-column "Landfall decides / the architect owns"); a
  step-by-step worked example over `sample-estate/` ending at the real
  **$113,911/mo** run-rate. Linked first from `docs/index.html`.
- **`evidence/trials/`** — `README.md` (status), `protocol.md` (Trial A
  comprehension + Trial B usability: recruitment, setup, tasks, timing,
  acceptance bars, what-to-log), `comprehension-answer-key.md` (3 tasks — explain
  the pipeline / run + trace a number / interpret Low confidence — with model
  answers + a scoring sheet), `results-template.md`, and
  `dry-run-2026-09-09.md`.
- **`dry-run-2026-09-09.md`** — self-administered the 3 comprehension tasks
  against the docs. All answerable + well-posed + scorable. **Caught a real
  bug:** the answer key said the sample cost figure is "Medium" confidence — it
  is **Low** (`assemble.py` caps pre-discovery cost at Low). Fixed the key +
  added a callout to the doc. Reconciled every worked-example number to
  `evals/pipeline.py`. Explicitly **not** a trial result.
- **`tests/test_docs.py`** (7) — the doc has every section + concept, is linked
  from the index, its worked-example numbers still match a fresh
  `pipeline.run()` (so a pricing change can't silently make the walkthrough
  wrong), the trial kit is complete, and the scorecard cites it.
- **`evidence/scorecard.py`** — Understandability 2.0 → **3.0** (Build done:
  docs match reality + D2 walkthrough + worked example + apparatus-validated
  task set; Proof: 3-person trial designed, ready, not run). Usability stays
  2.0 (kit ready, not run — noted in its gap). **Overall 3.78 → 3.89.**

### Check

| gate | result |
|---|---|
| unit | **410 pytest** (+7), 2 skipped |
| worked example | `test_docs.py::test_worked_example_numbers_match_the_pipeline` — $113,911/mo etc. reconcile to `pipeline.run()` |
| dry run | 3/3 comprehension tasks answerable from the docs; 1 apparatus bug found + fixed |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated |
| scope | docs (GitHub Pages) + evidence + scorecard only → **no deploy** |

### Act

- One commit on `c36-understandability`, merged `--no-ff` to `main`
  (`227ea08`), pushed. No `azd deploy`.
- D2 is `done`; E10.4 is `in-progress` (kit built, trials not run). Closing
  Understandability needs the 3-consultant comprehension trial; Usability needs
  the 3-pre-sales timed trial + an architect reviewer. Both are turnkey now.
- Next by scorecard leverage: run the trials (needs people), or the remaining
  Operability items (E9.3 `--tier prod`, E9.4 observability), or Security
  (E8.5 private endpoints).

---

## Cycle 35 — E9.2 clean-machine smoke test + dormant `azd up→down` CI

**Date:** 2026-09-09 · **Owner:** SRE ·
**Tracker:** E9.2 — the next scorecard lift on Operability (3.0, the lowest
"done"-ish dimension after Usability/Understandability which need human trials).

### Plan

- E9.2 wants `azd up → smoke → azd down` green on every PR, both OSes. The
  service-principal secrets to run `azd` in GitHub Actions can't be set from
  here, so the deliverable is: a real smoke script that runs **now** against the
  live deployment, + the CI workflow **written and dormant** until the secrets
  are added (one-time, documented).
- Mid-cycle the user reviewed the Epic E12 backlog: **no Front Door, no WAF, no
  IP allow-list, no paid domain**. E12.11 reframed to a $0 "nicer hostname"
  recipe (rename the app + a free DuckDNS subdomain + the free ACA managed cert).

### Do

- **`scripts/smoke.py`** (stdlib only — runs before any pip install). 8 checks:
  config completeness, every expected resource type in the RG, Function
  registered + host answers (401 = Easy Auth up, not 5xx), web revision
  Healthy/Provisioned/Running, web host answers, SQL Online/Paused/AutoClosed,
  `raw`+`answers` blob containers, and (`--deep`) the Foundry agent name
  resolves + (`SMOKE_API_TOKEN`) a live `query_inventory`. Non-zero exit on the
  first hard failure; `--json` writes the structured result; `--from-env` skips
  `azd`. **Ran green against `rg-landfall`: 8/8 (+ agent on `--deep`)** →
  `evidence/ops/smoke-live.json` (+ `evidence/ops/README.md`).
- **`.github/workflows/clean-machine.yml`** — matrix `[ubuntu-latest,
  windows-latest]` (the hooks are per-OS), OIDC `azure/login`, unique throwaway
  env per run, `azd up` → `python scripts/smoke.py --json` → **`azd down
  --force --purge` in `if: always()`**. `if: vars.CLEAN_MACHINE_CI == 'true'` so
  it's skipped until armed. `workflow_dispatch` + weekly `schedule` (a full
  up/down is ~20 min/OS + real spend — not per-PR yet). `MODEL_CAPACITY=10`.
- **`DEPLOY.md`** — "Post-deploy smoke test (E9.2)" section: run recipe, the CI
  arming steps (app registration → Contributor + RBAC Admin → federated
  credential → 4 secrets + `CLEAN_MACHINE_CI` variable), per-run cost (~$1–3),
  and the **known drift** the CI would surface — the live `web` Container App has
  Easy Auth enabled *imperatively*, not in `infra/resources.bicep`, so a fresh
  `azd up` brings the web app up with no auth (an E8.2 follow-up).
- **`tests/test_smoke.py`** (17) — host-up status classification, `Result`
  counts + exit code, `load_config` env parsing, `run_checks` green + degraded
  (missing resource type, dead host, empty config), `main --json`.
- **`evidence/scorecard.py`** — Operability 3.0 → **3.5** (smoke written +
  green-live + unit-tested; CI matrix written but not proven green in CI). Basis
  + 5 evidence links + gap rewritten. **Overall 3.72 → 3.78.**
- **`prd/engagement-workspaces-prd.md`** — §4.13 finding 11 + §5a E12.11 +
  the how-to block: no Front Door/WAF/IP-list/paid-domain; `landfall-web` rename
  + DuckDNS + free managed cert as the $0 path. `.gitattributes` pins
  `evidence/ops/*.json` LF.

### Check

| gate | result |
|---|---|
| unit | **403 pytest** (+17), 2 skipped |
| smoke (live) | 8/8 green against `rg-landfall`; `--deep` 9/9 (agent resolves) |
| workflow | `clean-machine.yml` parses; `azd down` is `if: always()`; job gated on `CLEAN_MACHINE_CI` |
| evals | 32/32 + 8/8 + 30/30; `evals/SCORECARD.md` no drift; `evidence/SCORECARD.md` regenerated (Operability + overall) |
| scope | no production code touched → **no deploy** (script + CI + docs + evidence + scorecard only) |

### Act

- One commit on `c35-clean-machine-ci`, merged `--no-ff` to `main` (`43b24fd`),
  pushed. No `azd deploy` — nothing in the deploy path changed.
- E9.2 is `in-review`, not `done`: closing it needs the OIDC secrets added + the
  CI proven green on both OSes (not doable from here). Next by scorecard
  leverage: the human trials (**E10.4** usability + comprehension, lifts two
  dimensions off 2.0) or **E9.3** `--tier prod`. Also worth folding the web
  Container App Easy Auth into Bicep (the drift the new CI would catch).

---

## Cycle 34 — front-end quick-wins on the chat page (Epic E12: E12.1–E12.4, E12.6)

**Date:** 2026-09-09 · **Owner:** UX + Full-stack ·
**Tracker:** E12.1–E12.4, E12.6 — the ship-now subset of a live front-end review
(engagement-workspaces-prd.md §4.13). Triggered by a user screenshot showing the
Upload panel rendered with its hint text and file list overlapping and illegible.

### Plan

- **Root cause** — `.uz` is a `<label>` (`display:inline` by default) styled as a
  block dropzone: `padding:16px` + three `<br>` lines + a dashed border on an
  inline box overlap; `#filerows` renders underneath.
- Ship the pure markup/CSS fixes in `app.py::index()` with no behaviour/API change:
  render fix (E12.1), intro-first collapsible panel (E12.2), dropzone type
  hierarchy (E12.3), button hierarchy (E12.4), responsive header (E12.6).
- Park the heavier items as Epic E12 backlog: file+CSP extraction (E12.7),
  guided pipeline state (E12.8), progress transparency (E12.9), direct-to-blob
  uploads (E12.10), edge/WAF + custom domain (E12.11), UI trust surface (E12.12).

### Do

- **`src/web/app.py::index()`**
  - `.uz{display:flex;flex-direction:column;gap:5px}` — the dropzone is now a
    clean card; copy split into `.uzt` (prompt, `--ink`, 13.5px) + two `.uzh`
    muted hint lines. Contrast re-computed: `--muted` on `--panel` is 6.6:1 —
    passes WCAG AA; the finding was density, not colour.
  - `#uploadpanel` `<div>` → `<details>` with `<summary>Inventory &amp;
    documents<span id=upcount></span></summary>`; `loadFiles()` sets
    `upanel.open=true` only when the engagement has no inventory, and fills
    `#upcount` with the file count. Returning users see the intro + prompt cards
    first; a fresh engagement still gets the upload prompt.
  - `button.send.secondary` (transparent + accent outline); `Start analysis` uses
    it — `Send` is the only filled primary in the default view.
  - `header{flex-wrap:wrap;gap:8px 12px}` + `@media(max-width:680px)` hides the
    spacer and full-widths the title so the 6-control header doesn't break narrow.
- **`tests/test_upload.py`** — +2: the panel is a `<details>` that doesn't lead
  (asserts `.uz{display:flex`, `class=uzt`/`uzh`, the auto-open rule), and
  `Start analysis` is the secondary button. Existing markup assertions
  (`"Drop files here"`, `"startanalysis"`, `"/analyze"`, `"showUpload"`) preserved.
- **`prd/engagement-workspaces-prd.md`** — §4.13 front-end defect review (12-row
  finding table), Epic E12 work breakdown (`## 5a`, E12.1–E12.12 with status), a
  C34 cadence row.

### Check

| gate | result |
|---|---|
| unit | **386 pytest** (+2), 2 skipped |
| render fix | `TestClient.get("/")` serves valid HTML; `.uz` is `display:flex`; panel is `<details>` |
| evals | 32/32 + 8/8 + 30/30, `evals/SCORECARD.md` + `evidence/SCORECARD.md` no drift |
| scope | only `src/web/app.py` production code changed → `azd deploy web` only; no api/agent/infra |

### Act

- One commit on `c34-frontend-quickwins`, merged `--no-ff` to `main`
  (`d25cbe3`), pushed. `azd deploy web` (`app.py` only).
- Epic E12 opened on the tracker: 5 done (C34), 7 backlog. Next by scorecard
  leverage is still **E9.2 clean-machine CI** (Operability 3→4); E12.7 (chat
  page → static file + CSP) is the next front-end cycle.

---

## Cycle 33 — security tail: thread-principal binding + data-handling statement (E8.6 / E8.7)

**Date:** 2026-09-09 · **Owner:** SWE + Security ·
**Tracker:** E8.6, E8.7 — the two items the scorecard flagged as the fastest lift
on the Security dimension.

### Plan

- **E8.6** — `POST /api/chat` takes `engagement` from the request body and never
  access-checks it, and honours a client-supplied `thread_id`. Close both: route
  the engagement through the visibility guard; make unscoped chat stateless.
- **E8.7** — write the data-handling statement a client CISO signs before an upload.

Deferred: the CISO signature itself; E8.5 private endpoints; the external pen test.

### Do

- **`src/web/app.py`** — `chat()` splits the body `engagement` and calls
  `_engagement(customer, project, req)` (the E11.10 `visibility` guard) → `404`
  if the caller can't see it; `prev_id` comes only from the engagement's stored
  `current_response_id` (never `body["thread_id"]`), so a leaked response id is
  inert and an unscoped chat is single-turn. Each saved turn + the chat doc record
  the `actor` (Easy Auth principal). `engagement_chat_new` stamps `last_actor`.
  Module docstring + comments updated.
- **`evidence/data-handling-statement.md`** — what Landfall ingests (and refuses);
  one deployment per engagement, single region, encryption; access model (Easy
  Auth, fail-closed RLS, `visibility`, audit trail, chat binding, SQL guard);
  sub-processors (all first-party Microsoft, same tenant + region; Azure OpenAI
  no-training); retention + `azd down` deletion; residency; known limitations; a
  sign-off block. Linked from the scorecard.
- **`evidence/scorecard.py`** — Security 3.0 → **3.5** (E8.6 closed + statement
  drafted); basis + evidence link + gap updated; index row for the statement →
  🟡 drafted. Overall **3.72 / 5**.
- **`tests/test_access_control.py`** — `_WContainer` gains `upload_blob`; +3:
  chat `404` for an engagement the caller can't see, a client `thread_id` is not
  passed to the model, a scoped turn records the actor.
- `operating-sop.html` v1.4 — access section + Phase 2 intro.

### Check

| gate | result |
|---|---|
| unit | **384 pytest** (+3), 2 skipped |
| chat binding | 404 for a non-visible engagement; `previous_response_id` never set from a client `thread_id`; `actor` on every saved turn |
| evals | 32/32 + 8/8 + 30/30, `evals/SCORECARD.md` + `evidence/SCORECARD.md` no drift |

### Act

- One commit on `c33-thread-binding`, merged to `main`, pushed. `azd deploy web`
  (`app.py` changed); no api/agent change.
- Security is now 3.5 — closing it needs the pen test (E10.4) + the signature +
  E8.5. Next by scorecard leverage: **E9.2 clean-machine CI** (Operability 3→4),
  then the usability + comprehension trials (E10.4).

---

## Cycle 32 — the 5/5 scorecard (E10.3 + E10.6, Phase 2 evidence)

**Date:** 2026-09-09 · **Owner:** PM ·
**Tracker:** E10.6 (`evidence/SCORECARD.md`) + E10.3 (`evidence/evals/` history).

### Plan

Build the file you hand someone who asks "is it production-ready?" — the nine
rubric dimensions from `audits/path-to-5x5.md` §3, the current honest score per
dimension, what's missing to reach 5/5, and a link to every evidence artefact.
The numbers behind the *done* dimensions come live from the other artefacts so a
regression there shows up here. Deferred: the trials / pentest / chaos artefacts
themselves (E10.4) — the scorecard lists them as ⬜ not started.

### Do

- **`evidence/scorecard.py`** — `rubric(live)` holds the 9 dimensions (5/5 bar,
  score, basis, evidence links, gap); `_live()` imports `backtest.run` +
  `broken-dumps/check.run` and parses `evals/SCORECARD.md` for the current numbers;
  Correctness / Robustness / Reliability score 5 **only while** their artefact
  passes. `_md()` renders the summary table (with score bars), per-dimension
  detail, the evidence-pack index, and residual risk. `main()` also snapshots
  `evals/SCORECARD.md` → `evidence/evals/history/<date>.md`.
- **`evidence/evals/README.md`** — points at the live scorecard + the history dir;
  notes that the git log of `evals/SCORECARD.md` is the full timeline.
- **`tests/test_scorecard.py`** (6) — all 9 dimensions present; overall = mean;
  every < 5 dimension names a gap and cites evidence; **every evidence link
  resolves on disk**; live pulls reflect the passing artefacts; `SCORECARD.md`
  drift gate. `evals.yml` regenerates + diffs `evidence/SCORECARD.md`.
- `evidence/README.md` now opens with "Start here: SCORECARD.md".

### Check

| Dimension | Score | Backed by |
|---|--:|---|
| Correctness | 5.0 | back-test 3×3 @ ≤5.7% (E10.1) |
| Defensibility | 4.0 | F* ids + calc appendix + register (E5.2/5.3) — board sign-off pending |
| Completeness | 4.0 | 8 data-driven sections — board "edit not author" pending |
| Robustness | 5.0 | 9-file broken-dump corpus, all per E1.4 (E10.2) |
| Usability | 2.0 | no-code path built, timed trial not run |
| Understandability | 2.0 | SOP v1.3 + docs, comprehension trial not run |
| Operability | 3.0 | deploys work + self-contained hooks; no clean-machine CI / chaos drill |
| Security | 3.0 | EasyAuth + RLS + SQL guard + access control + isolation tests; no pen test / signed statement |
| Reliability | 5.0 | eval CI gate — SQL 32/32, scenarios 8/8, faults 30/30, deterministic |
| **Overall** | **3.67 / 5** | |

- **381 pytest** (+6), evals green, `evidence/SCORECARD.md` + `evals/SCORECARD.md`
  no drift, all 27 evidence links resolve.

### Act

- One commit on `c32-scorecard`, merged to `main`, pushed. **Code-only — no deploy.**
- The scorecard now drives the remaining Phase 2 backlog: Usability + Understandability
  (trials, E10.4), Operability (E9.2–9.5), Security (E8.5–8.7 + pentest). Highest
  score leverage: E9.2 clean-machine CI (Operability 3→4) and the data-handling
  statement (Security 3→4, unblocks the CISO sign-off).

---

## Cycle 31 — broken-dump corpus (E10.2, Phase 2 evidence)

**Date:** 2026-09-09 · **Owner:** SWE ·
**Tracker:** E10.2 — the second Phase 2 evidence artefact.

### Plan

`evidence/broken-dumps/`: 6+ deliberately damaged client inventory exports, each
with a documented expected handling, proving **E1.4** — a broken input is never a
silent partial load; the data-quality report says why. Deferred: a live blob-trigger
round-trip (the E1.4 contract surface is `normalize` + `build_report` + the
`_process` classifier, all unit-testable).

### Do

- **`gen_dumps.py`** → 9 files in `dumps/`, one failure mode each: (1) headers match
  no profile, (2) zero bytes, (3) header only, (4) performance export missing the
  required `sample_date`, (5) ragged field counts, (6) non-numeric `vcpu`/`ram_gb`,
  (7) one `server_id` on three rows, (8) UTF-16 encoding, (9) dependency endpoints
  that reference unknown servers.
- **`EXPECTED.json`** — per file: `status` (unrecognised | rejected | ok), rows to
  SQL, `min_confidence`, and `must_say` phrases the rendered DQ report must contain.
- **`check.py`** — `normalize` → `build_report` → the `_process` classifier over
  every dump; asserts the outcome and that the report names the problem; writes
  `RESULTS.md`.
- **`src/api/ingest/dq.py`** — three new `_findings` (a recognised file with no data
  rows; duplicate primary keys; `vcpu`/`ram_gb` unparseable on >30%) and a
  `_confidence` rule (→ Low when vCPU/RAM is unparseable on >50% of servers).
- **`tests/test_broken_dumps.py`** (12, parametrised) + an `evals.yml` step that
  regenerates the corpus and fails on any diff. `.gitattributes` pins the generated
  artefacts + `SCORECARD.md` to LF (autocrlf on Windows would trip the drift gates)
  and marks the UTF-16 dump binary. `evidence/README.md` + SOP v1.3 updated.

### Check

| # | Dump | Outcome | Rows | Confidence |
|--|---|---|--:|:--:|
| 1 | unrecognised firewall export | `unrecognised` | 0 | Low |
| 2 | empty file | `unrecognised` | 0 | Low |
| 3 | servers header only | `ok`, "no data rows" | 0 | Low |
| 4 | performance, no `sample_date` | `rejected` | 0 | Low |
| 5 | ragged rows | `ok`, OS/app gaps named | 12 | Medium |
| 6 | garbage numerics | `ok`, "vCPU unparseable 100%" | 12 | Low |
| 7 | duplicate `server_id` | `ok`, duplicate key named | 9 | Medium |
| 8 | UTF-16 | `unrecognised` | 0 | Low |
| 9 | orphan dependency endpoints | `ok`, orphans named | 8 | Low |

- **375 pytest** (+12), evals 32/32 + 30/30 + 8/8, `SCORECARD.md` no drift.
- **9/9 handled per E1.4** — no silent partial load anywhere.

### Act

- One commit on `c31-broken-dumps`, merged to `main`, pushed. `azd deploy api`
  (`dq.py` changed — new findings reach the live DQ reports); no web/agent change.
- Next Phase 2: E10.3/E10.6 (`evidence/SCORECARD.md` — rubric + score + links),
  then E8.5–8.7, E9.2–9.5, E5.6.

---

## Cycle 30 — cost-method back-test (E10.1, Phase 2 evidence)

**Date:** 2026-09-09 · **Owner:** FinOps + Architect ·
**Tracker:** E10.1 — first Phase 2 (Evidence) artefact.

### Plan

Stand up `evidence/backtest/`: estimate the same estate's Azure run-rate three
independent ways and show they agree within ±15%, with the divergences explained.
Acceptance (PRD E10.1): "Portfolio totals within ±15% across methods; variances
explained." Deferred: real-price accuracy (that's E11.16 POE + S2 re-benchmark);
the broken-dump corpus (E10.2); `evidence/SCORECARD.md` (E10.6).

### Do

- **`estate_gen.py`** — `build_estate(preset)` for `small` (~40 srv, no compliance,
  45% monitored), `midmarket` (~230, PCI+HIPAA, 70%), `enterprise` (~620, +SOX,
  DB-heavy, 82%). Seeded per preset; keys match `scripts/schema.sql`.
- **`pricebook.py`** — a deterministic synthetic price book with **realistic
  non-linearity** (per-vCPU rate eases ~12% with size; family multipliers F 0.86 /
  D 1.00 / E 1.28; Windows licence adder; RI 0.63x / 0.44x). Without this a linear
  book makes linear methods agree trivially.
- **`methods.py`** — three costers over the **same** right-sized footprint
  (`rightsize_many`) and the **same** storage + run-rate-extras; only VM compute
  differs: `engine` (`estimate_compute_cost`, per-SKU), `blended` ($/vCPU median of
  D+F × right-sized vCPU, ×1.4 memory-opt), `bands` (T-shirt XS/S/M/L/XL priced at
  the D/F mean at the band ceiling, ×1.15 memory-opt).
- **`backtest.py`** — `run()` → per estate: 3 totals, spread `(max−min)/median`,
  PASS ≤ 15%, data-driven variance notes. `main()` writes `RESULTS.md`.
- **`tests/test_backtest.py`** (7) + an `evals.yml` step that fails on a stale
  `RESULTS.md` (mirrors the SCORECARD drift gate). `evidence/README.md` indexes it.

### Check

| estate | engine | blended | bands | spread | verdict |
|---|--:|--:|--:|--:|:--:|
| small | $16,451 | $15,923 | $15,548 | 5.7% | ✅ |
| midmarket | $86,648 | $83,646 | $82,328 | 5.2% | ✅ |
| enterprise | $249,921 | $242,459 | $237,313 | 5.2% | ✅ |

- **363 pytest** (+7), evals 32/32 + 30/30 + 8/8, `SCORECARD.md` no drift.
- Engine sits highest on every estate: it prices the exact right-sized SKU, so
  memory-heavy VMs pick up the E-family's ~1.28× premium that the linear rate and
  the D/F bands only partly carry. Compute is 70–76% of each total; shared storage
  + extras damp the spread.

### Act

- One commit on `c30-backtest`, merged to `main`, pushed. **Code-only — no deploy**
  (evidence tooling + tests). CI (`evals #NN`) gates it.
- Next Phase 2: E10.2 broken-dump corpus, then E10.3/E10.6 scorecard, E8.5–8.7,
  E9.2–9.5, E5.6.

---

## Cycle 29 — Phase 1 tail: wave duration model, resource loading, mapping override (E4.3 / E6.2 / E1.7)

**Date:** 2026-09-09 · **Owner:** PMO + SWE ·
**Tracker:** E4.3, E6.2, E1.7 — the last open Phase 1 engine items.

### Plan

Close the three items keeping Phase 1 from "complete":
- **E4.3** — turn the wave list into a dated schedule with a critical path.
- **E6.2 (full)** — wave-by-wave resource loading: a month-by-month FTE curve + peak FTE.
- **E1.7** — let an operator fix a mis-mapped column per engagement without a redeploy.

Deferred: a dedicated resource-loading sheet in the workbook (the curve ships in the
package JSON + dashboard); a holiday calendar beyond configurable blackout windows.

### Do

- **E4.3 — `src/api/waves/schedule.py` (pure).** `build_schedule(wave_plan, cfg, start_date)`:
  each wave's execution weeks = `ceil(servers ÷ throughput_servers_per_week)` floored at
  `min_wave_weeks`, with a `wave_prep_weeks` lead-in and `wave_soak_weeks` tail; waves take
  the earliest free lane of `parallel_waves`; `blackout_windows` push a wave's prep start
  past the window (shift recorded). Programme = `mobilisation_weeks` + waves +
  `programme_hypercare_weeks`. `critical_path` = the lane that finishes last, ordered, with
  the platform wave prepended (every spoke depends on it) and a `reason` per hop. New
  `schedule` config block (defaults + `estimation_config.json`). `plan_waves` attaches
  `result["schedule"]`; `start_date` threaded through the route + OpenAPI spec.
- **E6.2 — `deliverable/effort.py`.** `estimate_effort(…, schedule=…)` adds `resource_loading`:
  each workstream line carries a `phase` (mobilise / execute / cutover / hypercare); PD is
  spread across programme months proportional to day-overlap with the phase window —
  execution weighted by servers/wave, PM + governance + contingency level-loaded across the
  whole programme. Returns `curve[{month, pd, fte, by_workstream}]`, `peak_fte`, `peak_month`,
  `avg_fte` (FTE = PD ÷ `working_days_per_month`). `assemble_estimate` passes
  `wav["schedule"]`; new figures `programme_weeks` + `peak_fte`; `_body_waves` carries the
  schedule + per-wave dates. Deck slides 7 (Go-live column + schedule/critical-path line) +
  9 (loading line). Dashboard: wave card schedule + critical path, effort card FTE sparkline.
- **E1.7 — `ingest/core.py`.** `match_mapping(mapping, filename)` (pure) resolves
  `_mapping.json` — flat `{profile, columns}` or `{files: {exact | glob: {…}}}` — to one
  file's override. `normalize(name, data, overrides=None)` pins the profile and/or prepends
  header aliases to target columns; `NormResult.mapping_notes` records every change.
  `ingest/functions.py::_process` reads `raw/engagements/<c>/<p>/_mapping.json` best-effort
  and folds the notes into the summary + `.dq.json` `mapping_applied`. `operating-sop.html`
  v1.2 with the recipe.

### Check

| gate | result |
|---|---|
| unit | **356 pytest** (+19: 9 schedule, 5 loading, 7 mapping −2 renamed), 2 skipped |
| evals | golden SQL 32/32 · faults 30/30 · scenarios + output guard 8/8 · `SCORECARD.md` no drift |
| pipeline | `_default_`-shaped run: schedule 47 wk, critical path W0→W6, peak 7.8 FTE / avg 3.3 over 12 months |
| determinism | `build_schedule` + `estimate_effort(schedule=…)` byte-identical on repeat |

### Act

- Three commits on `c29-phase1-tail`, merged to `main`, pushed; `azd deploy api` + `azd deploy
  web` (dashboard) + `create_agent.py` re-run (plan_waves description + prompt: state the end
  date, critical path, peak/avg FTE — don't invent dates or team size).
- **Phase 1 engine is complete.** Remaining road to 5/5 is Phase 2 (Evidence): E10 evidence
  pack, E8.5–8.7, E9.2–9.5, E5.6 studio deck.

---

## Cycle 27 — target landing-zone diagram, deterministic (E11.22, core — no new infra)

**Date:** 2026-09-09 · **Owner:** Azure AI Architect + App Eng ·
**Tracker:** E11.22 (core done; C27b = the `ca-drawio` container) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.10 + decision 9 —
a deterministic driver over the diagram engine; the agent does not free-draw.

### Plan

`design_landing_zone` produces the whole topology as JSON but the deliverable had no
picture of it — the deck's hub-spoke slide is hand-drawn and generic. §4.10's design is
a deterministic `design → draw.io` mapping (the skill's rules coded in `lz/diagram.py`)
feeding a `ca-drawio` container that renders `.svg`/`.png`. The container needs
`azd provision` (new Container App) which runs the schema-drop postprovision hook — so
this cycle ships **the deterministic core with zero new infra**: emit the `.drawio` XML
directly and render it in the browser with the draw.io viewer. The container (server-side
raster + deck embed) becomes C27b, gated on a safe provision.

### Do

- **`src/api/lz/diagram.py`** (pure, no network) — `build_drawio(design)` → a valid
  `<mxfile>` document: the hub VNet + every spoke as a swimlane group, hub components and
  a per-spoke workload cell inside, `orthogonalEdgeStyle` edges for peering /
  ExpressRoute-VPN (on-prem) / DR (dashed), labelled with the real `region` / `dr_region`
  and the actual hub components. Palette + swimlane nesting + "no hand-routed edges" from
  the vendored rules. `_esc` escapes `& < > " '`. Also `mcp_plan(design)` (the ordered
  create-group / add-cell-of-shape / add-edge / export-xml plan for the engine) +
  `_shape_for()` (component → `mxgraph.azure.*` key) + `diagram_meta()`.
- **`build_landing_zone_diagram` Function** (`lz/functions.py`, sync — no queue): reads
  the design from the body (`design` / `applications`) or the engagement's
  `tools_raw.json`; writes `estimate/landing_zone.drawio` + `landing_zone_diagram.json`;
  409 if there's no design. `GET ?engagement=` returns the meta. `src/api/openapi/
  build_landing_zone_diagram.json`; `_OPENAPI_TOOLS` entry + a system-prompt line
  ("after design_landing_zone, call build_landing_zone_diagram") + a "Landing-zone
  diagram" prompt card. `publish_estimate` regenerates the diagram from
  `body["landing_zone"]` (best-effort).
- **Web** — `GET /dashboard/landing-zone-diagram?e=` serves the XML (`?download=1` →
  file); the dashboard LZ card `renderLZDiagram()` embeds it in an
  `viewer.diagrams.net/?...#R<xml>` iframe (client-side, no container) + a Download
  .drawio link.
- **`docs/diagram-authoring/`** — `xml-authoring-rules.md`, `azure.md` (palette + shape
  map), `layout-antipatterns.md`, vendored with source + retrieval date.
- **`tests/test_lz_diagram.py`** (13) — valid XML + structure (base layer, swimlanes,
  edges, every cell parented), determinism, no-DR, thin design, regulated colour, XML
  escaping, `mcp_plan` + `meta`; the Function route (inline / stored / 409 / design-from-
  apps / GET meta), `publish_estimate` regenerates it, and the web serves + embeds it.

### Study

| # | Result |
|---|---|
| sample estate | `build_drawio` → 37 cells, 7 edges, hub + 5 spoke swimlanes, `swedencentral` / `westeurope` labelled; parses as well-formed XML; opens in draw.io desktop |
| determinism | same design → byte-identical XML |
| wiring | `publish_estimate` writes `landing_zone.drawio`; `GET /dashboard/landing-zone-diagram` serves it; the card renders it in the viewer iframe |
| suite | **328 pytest** (+13 −0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c27-landing-zone-diagram`, merged to `main`, pushed, deployed
  (api 1m47s + web 1m38s + `create_agent.py`); CI `evals #49` green; **live-verified** —
  the agent called `build_landing_zone_diagram` for `_default_/_default_` and stored the
  `.drawio` (swedencentral, 9 spokes).
- **Follow-up landed same day (`c27-svg`):** `diagram.py::build_svg(design)` — a
  deterministic **self-contained SVG** (swimlane boxes, component rows, peering / hybrid /
  DR edges, region label; no external refs). `build_landing_zone_diagram` + `publish_estimate`
  now store `landing_zone.svg` too; `GET /dashboard/landing-zone-diagram` serves it by
  default (`?fmt=drawio` for the source) and the dashboard renders it **inline** — the
  `viewer.diagrams.net` iframe drops to a fallback. `tests/test_lz_diagram.py` → 15; 330 pass.
- **C27b landed same day (`c27b-drawio-container`) — imperatively, no `azd provision`:**
  `src/drawio/` is a ~30 MB FastAPI + **CairoSVG** container — one endpoint, `POST /render`
  (SVG bytes → PNG), key-guarded, **external ingress** (the Function App shares no VNet with
  the Container Apps environment — the C25 finding). Stood up with `az acr build` +
  `az containerapp create` (`ca-drawio-*`, minReplicas 0) so a schema-dropping `azd provision`
  was avoided entirely. `src/api/lz/render.py::rasterize(svg)` is best-effort — a no-op when
  `DRAWIO_RENDER_URL` is unset, so nothing changes for local/CI. `build_landing_zone_diagram`
  + `publish_estimate` store `landing_zone.png`; `export.py` `to_pptx` swaps its hand-drawn
  hub-spoke slide for the render and `to_docx` embeds it under the landing-zone section
  (`_diagram_png` decodes the b64 payload `publish_estimate` attaches to the package); web
  serves `?fmt=png`. `infra/resources.bicep` gains a param-gated `drawioApp`
  (`deployDrawio=false` — imperative today, flip to reconcile into IaC) + `azure.yaml` a
  `drawio` service. `tests/test_lz_render.py` (7). **337 pass**, evals PASS, no drift.
- **C27b deployed + live-verified (2026-09-09, `main`@`a567023` → `e86c43e`):** `azd deploy
  api` + `azd deploy web` (both exit 0, no provision). `ca-drawio-tmglwfatwcsa2` `/healthz`
  OK; `POST /render` turned the real stored 14.7 KB `_default_` SVG into a 5416×1192 PNG
  (140 KB). Agent `build_landing_zone_diagram` for `_default_/_default_` → `stored` now
  includes `landing_zone.png`. `_default_/_default_` SQL still returns **250 servers** — no
  schema drop. **Cold-start fix (`e86c43e`):** the first build after `ca-drawio` scaled to
  zero timed out `rasterize()` (20 s) and silently dropped the PNG; bumped to 45 s + one
  retry after a 3 s pause.
- **Still optional (not blocking E11.22):** swap CairoSVG for the `simonkurtz-MSFT/drawio-mcp-server`
  engine to get the full `mxgraph.azure.*` icon set + an optional raw MCP "tweak the diagram"
  tool; reconcile `ca-drawio` into IaC by flipping `deployDrawio=true` and running `azd
  provision` with `postprovision:` commented out in `azure.yaml` (schema DROP), then
  `git checkout azure.yaml`.

---

## Cycle 20b — discovery questionnaire, served and round-trippable (E11.25)

**Date:** 2026-09-09 · **Owner:** App Eng + Pre-sales Architect ·
**Tracker:** E11.25 (done) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.5b + decision 13 —
the questionnaire is delivered *through the solution*: served, exported for offline
completion, re-imported, and its answers feed the estimate's assumptions.

### Plan

`docs/discovery-questionnaire.html` was a static file with no route. It carries the
inputs the inventory can't — compliance scope, RPO/RTO, licensing, cutover windows —
so it needs to be a first-class artifact: a URL to send the client, a Word/Excel
export they fill offline, and an importer that turns the returned file into structured
answers the estimate cites.

### Do

- **`scripts/gen_discovery_catalog.py`** — parses the HTML (92 questions, 14 sections)
  into `src/web/discovery_catalog.json` and copies the HTML byte-for-byte to
  `src/web/questionnaire.html` (the web container ships only `src/web/`). A hand-kept
  `FEEDS` map marks the ~15 questions that ground a model input. `tests/test_discovery.py`
  fails on drift — same pattern as `evals/SCORECARD.md`.
- **`src/web/discovery.py`** — `render_xlsx` / `render_docx` (blank, or pre-filled from a
  saved `_discovery.json`); `parse_upload` (xlsx via openpyxl, docx via python-docx —
  matches rows/paragraphs on the question codes, ≥3 hits = the template, skips headings
  and the "…" placeholder); `gaps` (unanswered MUST/SHOULD by section); `discovery_record`
  (the `_discovery.json` payload). `python-docx` added to `src/web/requirements.txt`.
- **Web routes** — `GET /questionnaire` (serves the HTML), `GET /questionnaire.{xlsx,docx}`
  (`?e=` pre-fills), `GET /api/engagements/<c>/<p>/discovery` (answers + gap list). The
  **upload route** now recognises a completed questionnaire dropped into `docs/` and
  writes `raw/engagements/<c>/<p>/_discovery.json`, returning `discovery: {answered, gaps}`.
- **API** — `deliverable/functions.py::_discovery_for(engagement)` reads `_discovery.json`
  and injects it into `assemble_estimate` / `publish_estimate`. `assemble.py` folds each
  answer into the register as a **cited `discovery:<id>` assumption** and the top-12
  unanswered MUST questions as `discovery:*` data-gaps (`+N more` line past 12);
  `register.discovery` carries the headline. `export.py` renders the headline in the
  register section.
- **Surfacing** — dashboard register card shows the discovery headline + an "ask the
  client" link; `create_agent.py` gains a prompt line (read `register.discovery` +
  `discovery:*` gaps for "what's missing?"); the "What's missing?" prompt card + the
  intro capability list mention `/questionnaire`.
- **`tests/test_discovery.py`** (15) — catalog drift gate, catalog shape, xlsx + docx
  round-trip, blank-export sanity, non-questionnaire rejection, `gaps`, `discovery_record`,
  assemble folds it (cited + capped) / is unchanged without it, and the web routes
  (serve, export both formats, upload → `_discovery.json` → `GET …/discovery`).

### Study

| # | Result |
|---|---|
| round-trip | fill 4 answers → export .docx → re-upload → `_discovery.json.answer_map` identical; same for .xlsx |
| template detection | a `servers.csv` / a blank export / a fake `.pdf` are all correctly *not* the template |
| estimate wiring | `assemble_estimate` → `register.assumptions` has `A1 discovery:SC1`, `A2 discovery:R1`; 12 `discovery:*` "Ask the client" gaps + a "+N more"; `register.discovery.headline` = "4/92 answered · 34 required questions still open" |
| exports | docx / xlsx / pptx all render with the discovery lines |
| suite | **315 pytest** (+15 −0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c20b-discovery-questionnaire`, merged to `main`, pushed. Deploy:
  `azd deploy api` + `azd deploy web` + re-run `create_agent.py` (prompt changed).
- **Carry:** `design_landing_zone` doesn't yet *consume* the compliance/DR answers
  (it only lands them as cited assumptions via `assemble`) — a follow-up could have
  `SC1` seed a regulated spoke and `R1`/`R3` drive the DR block. PDF questionnaires
  aren't parsed (the route says so). The `_discovery.json` write is last-write-wins.

---

## Cycle 28 — `design_landing_zone` scored against the Azure (AI) Landing Zone design checklist (E11.23)

**Date:** 2026-09-09 · **Owner:** Azure AI Architect + Cloud Architect ·
**Tracker:** E11.23 (done) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.11 + decision 11 —
the checklist is a *vendored design reference* the deterministic tool applies; the
agent does not re-derive architecture.

### Plan

`design_landing_zone` already derives the whole topology from the portfolio (MG
hierarchy, spokes, IP plan, policy baseline, identity, DR). The gap for a funding /
architecture review is *attribution*: nothing said the design conforms to Microsoft's
own guidance, and nothing surfaced what it deliberately leaves for the build phase.
Same pattern as MEG and the two diagram skills — vendor the checklist, code the rules,
emit a conformance section.

### Do

- **`docs/lz-design/{alz-checklist,ai-lz-checklist}.md`** — the Azure Landing Zone
  design checklist (10 domains: Identity · Resource Organization · Networking ·
  Security · Governance · Management · Monitoring · Reliability · Cost · Data) and the
  AI-LZ overlay, distilled with source URLs + a 2026-09-09 retrieval date. A reference,
  not a live doc.
- **`src/api/lz/conformance.py`** (pure) — ~34 ALZ rules + a 10-item AI-LZ overlay.
  Each rule reads the design's *structured* output (`management_groups`, `hub.components`,
  `policy.baseline/regulated_overlay`, `dr`, `subscriptions`, `connectivity`, …) — never
  prose — and returns `met` / `partial` / `gap` / `n/a` + evidence + a recommendation.
  `n/a` (no regulated scope → SEC-2/3, GOV-3; no AI workloads → the whole overlay) is
  excluded from the met/total ratio. `ai_workloads_present()` sniffs app
  `workload_type` / name / tech-stack for AI/ML/analytics tokens.
- **`design_landing_zone`** returns `checklist_conformance[]`, `checklist_summary`
  (`{met, partial, gap, na, total, met_pct, headline}`), `checklist_gaps[]`,
  `ai_lz_applicable`. Wrapped in try/except — a rule error never breaks the design.
- **`assemble.py`** — `_body_lz` carries a `design_conformance` block (headline +
  gap list); a new `lz_conformance` headline figure ("N met of M checklist items").
- **`export.py`** — the LZ section body lines and the pptx LZ slide render the headline
  + the top gaps with recommendations.
- **`dashboard.html`** — the Landing zone card shows a `N/M checklist items met` pill,
  an `AI-LZ overlay` pill when applicable, and a "gaps to close" `<details>` drawer.
- **`scripts/create_agent.py`** — system-prompt line: quote `checklist_summary.headline`
  and list `gap` rows when the user asks about the target architecture.
- **`tests/test_lz_conformance.py`** (13) — well-formed items, met↔no-recommendation,
  determinism, baseline meets identity/resource-org, no-DR → REL-1 gap, regulated rows
  n/a without a scope, AI overlay only with AI workloads (AILZ-4 met from the baseline
  managed identity), n/a excluded from the ratio, thin-design robustness, assemble +
  all three exports surface it, checklists vendored.

### Study

| # | Result |
|---|---|
| sample estate (PCI app, no AI) | `17/30 checklist items met · 7 gaps`; gaps are the build-time items — central Log Analytics workspace, diagnostic-settings policy, Update Manager, platform alerting, budgets/cost-alerts |
| + an ML workload | `ai_lz_applicable: true`, 10 AI-LZ rows scored (AILZ-4 met, 9 gaps — Foundry hub, PTU plan, private endpoints for AI, APIM gen-AI gateway, Content Safety, …) |
| determinism | same input → byte-identical `checklist_conformance` |
| deliverables | docx / pptx / xlsx all render; dashboard card shows the pill + drawer |
| suite | **300 pytest** (+13 −0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c28-lz-checklist-conformance`, merged to `main`, pushed. Deploy:
  `azd deploy api` + `azd deploy web` + re-run `create_agent.py` (prompt changed).
- **Carry:** COST-1 and the monitoring rows are advisory (`partial`/`gap` with a
  recommendation) — they could go `met` if `conformance.evaluate` also read the
  `compute_cost` / a monitoring config; keep design-only for now. Re-vendor the
  checklists when CAF / AI-LZ guidance changes (they carry a retrieval date).

---

## Cycle 23 — engagement access control + audit + pre-E11 migration (E11.10, E11.11)

**Date:** 2026-09-09 · **Owner:** App Eng + Azure AI Architect ·
**Tracker:** E11.10, E11.11 (done) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §7 decision 2 —
creator + optional group share, recorded on `_engagement.json`.

### Plan

C18–C22 built per-engagement tenancy (ADLS layout, SQL RLS, hard `engagement`
scoping) but nothing yet stopped one signed-in user from *listing* or *opening*
another user's engagement, and there was no attributable record of who ran or
published what. Two gaps to close: (E11.10) visibility filtering + an audit trail;
(E11.11) a clean path for a deployment that predates the engagement layout.

### Do

- **`src/api/engagement.py`** — `normalize_visibility` (`owner` | `group:<id>` |
  `all`, fail-closed), `can_view(manifest, viewer, groups)`, `principal_from_easyauth`
  (decodes the base64 `x-ms-client-principal`, incl. `groups` claims). Mirrored, self-
  contained, in **`src/web/access.py`** (the web container doesn't ship `src/api`).
- **`src/api/audit.py`** — `record` / `read` over
  `answers/engagements/<c>/<p>/_audit.jsonl` (append-only, best-effort). Wired into
  engagement-create, `run_engagement`, `publish_estimate`. `GET …/audit` on both the
  Function (`engagements.py`) and the web app, newest-first.
- **Enforcement** — Function `_list` + `engagement_one` (403); web `engagements_list`,
  every engagement-scoped read via `_engagement(customer, project, request)` (404 —
  indistinguishable from absent), and the `/dashboard/*` routes via `_guard_eid`.
- **`scripts/migrate_to_default_engagement.py`** — dry-run by default; `--apply` moves
  the flat `raw/inventory/` + `raw/docs/` + `answers/estimate/` blobs under
  `engagements/_default_/_default_/…`, writes the seed `_engagement.json`
  (`visibility: all`), and backfills un-keyed rows across the 6 SQL tables (RLS policy
  toggled off around the `UPDATE`). Idempotent.
- **Shim** — `_read_estimate_blob` still resolves the pre-E11 flat `estimate/` path for
  one release and logs a deprecation warning when it does.
- **Docs** — `operating-sop.html` gains an "Access control & audit" ref section + an
  operator migration step (v1.1).
- **Tests** — `tests/test_access_control.py` (can_view matrix ×2 modules, principal
  decode, Function list filtering + groups, 403; web list + 404 guard + dashboard 403 +
  audit route), `tests/test_audit.py` (record/read roundtrip, resilience, publish wires
  it), `tests/test_migration.py` (dry-run is a no-op, apply moves + seeds, idempotent).

### Study

| # | Result |
|---|---|
| visibility matrix | `owner` → creator only; `group:<id>` → creator + members; `all` → anyone; unknown value → fail-closed to `owner`; no Easy Auth header → filtering off (local deploy sees all) |
| enforcement | Function `_list` returns own + public + matched-group only; `engagement_one` 403; web engagement-scoped reads + `/dashboard/data` 404/403 for a non-viewer |
| audit | create / `run_engagement` / `publish_estimate` each append an `{at, actor, event, …}` line; `GET …/audit` returns them newest-first |
| migration | dry-run prints the plan and changes nothing; `--apply` moves 4 blobs + writes the manifest; second `--apply` is a no-op |
| suite | **287 pytest** (+30 -0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c23-access-control-migration`, merged to `main`, pushed. Deploy: `azd
  deploy api` + `azd deploy web` + re-run `create_agent.py` (no agent-prompt change this
  cycle — the audit route is not an agent tool).
- **Carry:** `_audit.jsonl` is last-write-wins (fine for the pre-sales single-writer
  case; add an append lease if it goes concurrent); `group:` needs the app registration
  to emit `groups` claims — document in DEPLOY.md; a dashboard "audit" tab; run the
  migration script live against `rg-landfall` (SQL side is a no-op there — C18 already
  re-loaded the sample estate as `_default_/_default_`).

---

## Cycle 26 — per-engagement conversation memory + engagement export / import (E11.26)

**Date:** 2026-09-08 · **Owner:** Azure AI Architect + FinOps + App Eng ·
**Tracker:** E11.26 (done, deployed) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.12 + decision 14 —
conversation memory is the Responses API's own server-side store, keyed per
engagement in blob; **not** the preview managed Memory feature.

### Plan

Sponsor: *"memory should be under the Foundry agent"* — the chat only remembers the
current browser tab today (lost on New chat / close / second device, not tied to the
customer/project). Also: the solution is deployed with `azd up` and **torn down with
`azd down` to save cost**, so it must be **portable** — an engagement should survive a
teardown/redeploy or move between deployments.

Panel verdict (AI architect / cloud architect / FinOps / director):

- **Not** the new managed Foundry Memory feature — it needs the **Standard agent setup
  backed by Cosmos DB**; Landfall runs a **low-code prompt agent** on purpose. Cosmos
  carries a 24/7 RU floor (breaks near-free), it's preview (API churn hurts a
  redeploy-months-later story), and it's the wrong model: a **funding POE must be
  deterministic** — the agent's context is the uploaded inventory + `_discovery.json` +
  the published estimate, which it already reads through tools. Don't make the LLM
  *remember* a compliance scope; make it *look it up*.
- **Do** persist the conversation server-side per engagement. The Responses API already
  stores the chain in the Foundry project (`store=true`); keep the **pointer + a
  transcript** in the engagement's own blob. Zero new resources.
- **Do** add engagement **export / import** — the real portability piece for a
  tear-down-friendly tool.

### Do

- **`src/web/app.py`**
  - `answers/engagements/<c>/<p>/_chat.json` = `{current_response_id, started_at,
    turns[], archived[]}`. `/api/chat` reads the pointer from there (not the browser
    body), chains `previous_response_id`, appends the user + assistant turns, saves.
    Falls back to a body `thread_id` only when unscoped.
  - `GET  /api/engagements/<c>/<p>/chat` — the transcript (page renders it on load /
    engagement switch).
  - `POST /api/engagements/<c>/<p>/chat/new` — archive the current thread into
    `archived[]` (summary + last response id — the Foundry chain stays retrievable),
    start fresh.
  - `GET  /api/engagements/<c>/<p>/export` — one `.zip`: `raw/_engagement.json` + every
    `raw/inventory|docs/*` + every `answers/estimate/*` + `answers/_chat.json` +
    `export.json`. 250 MB cap; skips empties + HNS directory markers.
  - `POST /api/engagements/import` — restore a `.zip` (validates `export.json`, slug-
    checks the id, blocks `..`/absolute paths); **409 unless `overwrite=true`**.
  - `_SEG_RE` relaxed to allow the `_default_` sentinel's underscores (it was 404-ing).
- **Chat page** — loads + renders the engagement's saved transcript on select; "New
  chat" archives server-side; header gains **↓ export** (when an engagement is active)
  and **↑ import** (hidden file input); dropped the `localStorage` thread id (the
  engagement id still persists locally so the page reopens where you left off).
- **`tests/test_engagement_memory.py`** (6) — chain continuity, transcript GET, archive-
  not-destroy, export/import round-trip, 409-on-existing, non-zip rejection.

### Study

| # | Result |
|---|---|
| conversation continuity (live, real agent) | turn 1 "how many prod servers?" → *173*; turn 2 "**their** total vCPU?" → *1,436* — the agent resolved "their" from the stored chain, i.e. memory works |
| persistence | `_chat.json` written to `answers/engagements/_default_/_default_/_chat.json`, 4 turns + pointer; a `GET …/chat` reload returns them |
| New chat | archives to `archived[]` with the last response id; next turn starts a fresh chain (no `previous_response_id`) |
| export | live: 2.54 MB `.zip`, 12 members — `raw/_engagement.json`, `answers/_chat.json`, `answers/estimate/{latest.*, landing_zone.*, tools_raw.json}` |
| import | round-tripped a re-keyed engagement; imported `_chat.json` had all 4 turns; existing id → **409**, `overwrite=true` → 201 |
| tests | **208 pytest** (+6) + 32/8/30 evals green |
| cost | **no new Azure resources**; nothing added to the `azd up` path |

### Act

- Committed + pushed; deployed `web`. PDCA log + PRD §4.12 + decision 14 + work item
  E11.26 + `INSTALL.md` note ("export engagements before `azd down`, import after
  `azd up`") — *INSTALL note still to write*.
- **Carry:** last-write-wins on `_chat.json` (fine for one pre-sales user; add an ETag
  check if it ever goes multi-user); an "archived threads" viewer on the dashboard;
  re-key on import (import under a *new* customer/project, not just the original id);
  a one-click "export all engagements" before teardown.

---

## Cycle 25 — POE pipeline live (async) + engagement upload panel (E11.16, E11.6 part, E11.24)

**Date:** 2026-09-08 · **Owner:** App Eng + Azure Pre-Sales Architect + Platform Eng ·
**Tracker:** E11.16 (async — done, live), E11.20 (done), E11.6 (upload panel — done),
E11.24 (upload confirmation — done); E11.19 (adapter accuracy — open) ·
**Decisions:** [`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.5a
(upload: server-side, content-sniffed, per-engagement-isolated, visible confirmation),
§4.6 + decision 10 (ca-calc is queue-decoupled), decision 12 (upload).

### Plan

Two things. **(1)** Get the Pricing Calculator POE actually working: C24 built the
pieces but a live smoke showed the agent's `build_calculator_estimate` call returning
502. **(2)** A pre-sales architect with no CLI must be able to upload the client's
server + application inventory (`.csv`, `.xlsx`, …) from the dashboard into a **dedicated
per-customer/project ADLS folder**, with a **visual indication** each file landed, and
outputs kept in a separate folder for the same engagement.

### Do

**POE async (E11.16).** Root cause of the 502: the Flex Consumption Function App shares
no VNet with the Container Apps Environment, so it can't reach `ca-calc`'s internal
ingress at all — *and* a ~55-line Playwright drive overruns the ~230 s Functions HTTP
limit regardless. Rebuilt around a **storage queue**:

- new `calc-jobs` queue (Bicep). `build_calculator_estimate` POST now stages the spec
  to `{prefix}/_calc_spec.json`, writes `landing_zone.json` status `building`, drops one
  `calc-jobs` message, and returns **202**. New `GET ?engagement=` status route +
  `get_calculator_estimate` OpenAPI tool for polling; agent system-prompt reworked
  ("the POE builds in the background — watch the dashboard").
- `src/calc/worker.py` — `consume_forever()`: `DefaultAzureCredential(uami)` +
  `QueueClient`, drains a message, reads the spec, `build_estimate`, parse + reconcile,
  writes `landing_zone.{xlsx,json,png}` (ready|failed) to the engagement folder itself,
  deletes the message either way. `asyncio.wait_for(..., 1500 s)` budget. `app.py`
  lifespan starts it; `minReplicas: 1` (KEDA queue-scale-to-zero deferred — the MI
  scale-rule auth shape isn't in this Bicep type version and shared-key auth is off).
- Dashboard POE card renders `building` (auto-refresh) / `failed` / `ready`.
- `azure` SDK HTTP logging → WARNING (it was drowning the worker's own logs).

**Upload panel (E11.6 / E11.24).**

- `src/web/uploads.py` (pure, 5 tests) — `classify(name, head)` checks type by **magic
  bytes + structure**, not extension: `.csv/.tsv/.json/.xlsx/.xls/.zip` → `inventory/`,
  `.pdf/.docx/.md/.txt/.png/.jpg` → `docs/`; rejects `.xlsm/.docm`/exe/other archives
  with a reason. `peek(name, data)` — best-effort header + row count + a profile hint
  (RVTools vInfo / CMDB / server inventory / …). Caps: 100 MB/file, 250 MB/request,
  2 GB/engagement.
- `src/web/app.py` — `POST /api/engagements/{customer}/{project}/upload` (multipart,
  **streamed in 4 MB blocks** via `stage_block`/`commit_block_list`, slug-validated so a
  file can't be written outside its engagement prefix, magic-byte checked on the first
  8 KB before any block is committed, `peek` metadata stamped on the blob),
  `GET …/files` (manifest: name, kind, size, uploaded-at/by, profile, rows),
  `DELETE …/files/{name}`. New deps `python-multipart`, `openpyxl`.
- Chat page — an **Upload panel** appears whenever an engagement is selected: drag-drop
  or browse, auto/data/docs toggle, per-file rows that go
  `uploading NN%` → `checking…` → **✓ inventory · RVTools vInfo · 412 rows · 152 KB**
  (or `✗ <reason>`), a toast, and a **persisted manifest** that re-lists the folder on
  load with a remove button. Welcome copy points the user at it.
- Wrote the missing `_engagement.json` for the seed `_default_/_default_` engagement
  (`Sample Estate — Reference Migration`, `visibility: all`) so it shows in the picker.

### Check

| # | Result |
|---|---|
| POE end-to-end, live | agent → **202 in 10 s** → `calc-jobs` → `ca-calc` drove the real calculator (55 products) → genuine `ExportedEstimate.xlsx` (56 KB) + `.png` + `.json` at `answers/engagements/_default_/_default_/estimate/landing_zone.*` |
| POE reconciliation | **−73 %** ($26,314 calc vs $97,624 internal) — the ~14 unverified adapters added the products but didn't set quantities, so the calculator used defaults. Flagged `within_tolerance: false`. → **E11.19 is the open work** |
| queue consumer auth | `ca-calc` polls `calc-jobs` with the workload identity, HTTP 200, no shared key |
| upload — isolation | test: `servers.csv` → only `raw/engagements/contoso-ltd/dc-exit/inventory/servers.csv`, nowhere else; `../../etc/passwd` path → 404 |
| upload — validation | `.xlsm` → 415 "re-save as .xlsx"; `<html>` renamed `.xlsx` → 415 "doesn't look like a real .xlsx"; binary `.csv` → 415 |
| upload — confirmation | `peek` returns `RVTools vInfo · 412 rows` from a real vInfo header; xlsx row count via openpyxl |
| tests | **202 pytest** (+10 new: `test_upload.py`, `test_calc_service.py`, rewritten `test_build_calculator_estimate.py`) + 32/8/30 evals green |

### Act

- Committed + pushed: `c96be46` (queue decouple) → `3bc6ff7` (PRD) → this cycle's web
  upload commit. Deployed: `azd provision` + `azd deploy calc` + `azd deploy api` +
  `azd deploy web` + `create_agent.py` (16 OpenAPI tools).
- **Carry to C25b / next:** **E11.19** — verify every `ca-calc` product adapter against
  the live calculator so the reconciliation delta closes (the POE isn't submittable until
  it does). Then KEDA queue-scale-to-zero for `ca-calc`, the weekly adapter smoke, and
  `run_engagement` → `build_calculator_estimate` hook.
- **Carry:** wire the upload panel's manifest to a **"Start analysis"** button
  (`run_engagement`, E11.4) so uploaded files get ingested + DQ-reported per file;
  `.zip` expansion; the discovery questionnaire round-trip (E11.25).
- No maths, CAF logic or eval-gate changes — plumbing + UX only.

---

## Cycle 24 — Azure Pricing Calculator POE + chat engagement scoping (E11.15–E11.18, part E11.6/E11.7)

**Date:** 2026-09-08 · **Owner:** Azure Pre-Sales Architect + App Eng ·
**Tracker:** E11.15 (done), E11.16 (code done, deploy pending), E11.17 (done),
E11.18 (done), E11.6/E11.7 (chat engagement picker done) · **Decisions:**
[`engagement-workspaces-prd.md` §3.4 / §4.6](engagement-workspaces-prd.md) —
Microsoft migration-funding POE accepts only the calculator's own Excel; the end
user picks the target region.

### Plan

Sponsor: the landing-zone + workload cost estimate for a Microsoft funding
submission must be the **Azure Pricing Calculator's own Excel export**, per
engagement, on the dashboard, downloadable. Also: the user must not have to type
the `<customer>/<project>` engagement id, and needs a working-indicator + new-chat
+ prompt cards + a greeting in the chat UI.

### Do

- **`src/api/lz/calculator_spec.py`** (E11.15, pure, 21 tests) — `design_landing_zone`
  + `estimate_compute_cost` + `estimate_storage_cost` (+ `run_rate`) → a calculator
  **line-item spec with no prices**. Azure-region→calculator-code map (61 regions;
  an unsupported region raises at build), VM SKU→size slug, disk tier→module,
  storage category→module (incl. ANF), LZ platform components→modules (Bastion /
  Firewall / DDoS / DNS / ExpressRoute / VPN GW / 2× AD DCs / Log Analytics /
  Key Vault / egress Bandwidth), ASR for tier-1/2 → DR region. Unpriceable items
  (Oracle, DR compute, no-module storage) → `spec["skipped"]` with a reason.
  `internal_monthly_estimate` kept for reconciliation.
- **`src/api/lz/calculator_export.py`** (E11.16, 4 tests vs the real fixture) —
  parse `ExportedEstimate.xlsx` → `{estimate_name, line_items[], total_monthly,
  licensing_program, created_at, …}`; `reconcile()` flags a >15% delta.
- **`src/calc/`** (E11.16) — **`ca-calc` Container App**: `mcr.microsoft.com/playwright/python`
  image, `POST /build` takes the spec, drives the live calculator (native value
  setter + `input`/`change` events — verified), sets estimate-name / currency /
  `discountLevel`, clicks `button.export-button`, returns `{xlsx_b64, screenshot_b64,
  applied[], skipped[]}`. **`adapters.py`** — 20 product adapters; VM + managed-disks
  verified end-to-end, the rest built from the observed module shape and marked
  `verified: false` (the E11.19 weekly smoke fills them in; an adapter that can't
  set a field records it, an adapter that errors → the line goes to `skipped`).
- **`src/api/lz/functions.build_calculator_estimate_route`** (E11.16/E11.18) —
  `POST /api/build_calculator_estimate {engagement}` → read `latest.json` +
  `tools_raw.json` + `_engagement.json` → `build_calculator_spec` → `POST CALC_URL/build`
  → parse + `reconcile` → write `answers/engagements/<c>/<p>/estimate/landing_zone.{xlsx,json,png}`.
  `publish_estimate` now also writes `tools_raw.json` (the raw tool outputs). 3 tests
  (fake blob + fake ca-calc).
- **OpenAPI** `build_calculator_estimate.json` + `create_agent.py` tool #13 + a
  system-prompt line ("for a Microsoft migration-funding POE, call
  `build_calculator_estimate` AFTER `publish_estimate`…").
- **Dashboard** (E11.17) — `src/web/app.py` `GET /dashboard/landing-zone` +
  `GET /dashboard/download/landing-zone-xlsx`; `dashboard.html` "Azure landing
  zone — Pricing Calculator POE" card ($X/mo, reconciliation delta chip, "not in
  the calculator estimate" drawer, Download Excel (POE), Open calculator ↗).
- **Chat engagement scoping** (E11.6/E11.7) — header **engagement `<select>`** +
  inline **"New engagement"** form (customer, project, **target region** from
  `/api/calc_regions` = the calculator's supported set, DR region, licensing
  program, currency). `src/web/app.py` lists/creates engagements **directly in
  blob** (`GET/POST /api/engagements`) — no Function-to-Function token.
  `/api/chat` takes `engagement` and **prepends a scoping instruction** to the
  input so the agent uses it for every tool call and never asks the user for the
  id. Selected engagement persists in `localStorage`. `_engagement.json` gains
  `target_region` / `dr_region` / `currency` / `licensing_program` /
  `target_region_calculator_supported`.
- **Chat UX** — "+ New chat" (clear + fresh session), animated "The estimator is
  working… (Ns)" bubble with the input disabled, a greeting (agent intro +
  capability list), clickable prompt cards from `src/web/prompt_cards.json`
  (`GET /api/prompt_cards`).
- **infra** — `ca-calc` Container App (internal ingress, scale-to-zero, 1 vCPU /
  2 GiB); `CALC_URL` on the Function; `azure.yaml` `calc` service;
  `main.bicep` / `main.parameters.json` param threading.

### Check

| # | Result |
|---|---|
| C1 | `build_calculator_spec` on the sample estate: 54 line items (31 VM groups, 8 disk tiers, DB storage, 11 platform lines, ASR), region `sweden-central`, `internal_monthly_estimate` ~$97.6k; Oracle + ANF + DR-compute in `skipped` |
| C2 | `parse_calculator_export` on the real `ExportedEstimate.xlsx`: name, 1 line item, `total_monthly` 5664.8, `created_at`; bytes + no-total-row fallback covered |
| C3 | `build_calculator_estimate_route` (mocked): spec is region-correct + price-free, calls ca-calc, stores `landing_zone.{xlsx,json,png}`, reconciliation delta computed |
| C4 | Chat page: engagement picker + New-engagement form present; `/api/chat` prepends `[Active engagement: …]`; `/api/calc_regions` returns 61 supported regions |
| C5 | **183 pytest + 32/8/30 evals green**; `az bicep build` clean |

### Act

- **Deployed 2026-09-08:** `azd deploy web` + `azd deploy api` + `create_agent.py`
  re-run (tool #13 attached). Chat picker + POE card live.
- **`ca-calc` NOT deployed yet** — needs `azd provision` (new Container App) +
  `azd deploy calc` (Playwright image build ~5–10 min). Until then
  `build_calculator_estimate` returns 503 ("CALC_URL not configured"). **C24 tail.**
- **C25:** E11.19 weekly Playwright adapter smoke; verify/complete the ~14
  unverified product adapters against the live calculator; wire the
  `run_engagement` → `build_calculator_estimate` hook; authenticated Save →
  `landing_zone_url` (deferred).
- **Known:** the `ca-calc` adapters beyond VM/disk are best-effort; a real POE run
  will surface which need field-map fixes. The spec builder's platform quantities
  (egress GB, LA GB, DNS zones) are heuristic — an architect reviews before submit.

---

## Cycle 18 — engagement tenancy foundation (E11.1 / E11.2 / E11.3)

**Date:** 2026-09-08 · **Owner:** App + Data Eng · **Tracker:** E11.1–E11.3 (done, live),
E11.4 / E11.5 (partial) · **Decisions:** [`engagement-workspaces-prd.md` §7](engagement-workspaces-prd.md)
(engagement_id column + RLS; creator+group visibility; studio-deck container deferred).

### Do

- **`src/api/engagement.py`** — engagement identity: `slug()`, `make_engagement_id()`,
  `normalize_engagement()` (`^[a-z0-9][a-z0-9-]{0,39}$` per segment), the per-engagement
  ADLS prefixes (`inventory_prefix` / `answers_prefix` / `estimate_prefix` /
  `ingest_report_prefix` / `history_prefix`), and `parse_inventory_blob()` (bare path or
  full Event Grid subject → `(engagement, filename)`). Pure, no Azure imports.
  `DEFAULT_ENGAGEMENT = "_default_/_default_"` folds the pre-E11 single estate.
- **`src/api/engagement_sql.py`** — `set_engagement(cursor, id)` → `sp_set_session_context`.
- **`scripts/schema.sql`** — `engagement_id NVARCHAR(120) NOT NULL` on all 6 tables;
  composite PKs `(engagement_id, <id>)` for servers/applications/storage; indexes on the
  IDENTITY tables; **Row-Level Security** — `dbo.fn_engagement_predicate` +
  `dbo.EngagementFilter` `SECURITY POLICY` filtering every table by
  `SESSION_CONTEXT('engagement_id')`. **No context set → no rows** (fail closed); every
  reader sets it first. INSERTs unaffected (loader writes `engagement_id` explicitly).
- **`src/api/ingest/loader.py`** — `engagement_id` first in every `TABLE_COLS` list;
  `load(table, rows, engagement, conn=None)` validates the id up front, sets the session
  context, keys the DELETE on `(engagement_id, source_file)`; `existing_keys(engagement)`
  and `write_log` scoped too.
- **`src/api/ingest/functions.py`** — blob trigger path
  `raw/engagements/{customer}/{project}/inventory/{name}`, engagement derived via
  `parse_inventory_blob`; `POST /api/ingest` takes `engagement`; DQ reports written to
  `answers/engagements/<c>/<p>/_ingest/`.
- **`src/api/engagements.py`** (new blueprint) — `POST /api/engagements`
  (slug + uniqueness → `_engagement.json` + folder skeleton; records `created_by` from
  the EasyAuth principal + `visibility`), `GET /api/engagements` (list, filtered by
  creator/visibility), `GET /api/engagements/{customer}/{project}`.
- **`src/api/tools.py`** — `query_inventory` takes `engagement` (defaults to
  `_default_/_default_`), sets the RLS context before running the model's SQL — this is
  what makes free-form text-to-SQL tenant-safe regardless of what the model writes.
- **`src/api/deliverable/functions.py`** — `assemble_estimate` / `export_estimate` /
  `publish_estimate` take `engagement`; `publish_estimate` writes to
  `answers/engagements/<c>/<p>/estimate/`; the package `meta.engagement` is stamped.
- **`src/web/app.py`** — `/dashboard/data` + `/dashboard/download/{fmt}` accept `?e=`;
  `_read_estimate_blob` tries the engagement path, then `_default_`, then the legacy
  `estimate/` path (back-compat for cycles 1–17).
- **OpenAPI specs** (`query_inventory`, `assemble_estimate`, `export_estimate`,
  `publish_estimate`) + `create_agent.py` SYSTEM_PROMPT gain the `engagement` argument /
  the ENGAGEMENT SCOPE rule.
- **`eventgrid.{sh,ps1}`** — inventory subscription subject → `/blobs/engagements/`.
- **Tests** — `tests/test_engagement.py` (22 cases: slugs, ids, prefixes, blob parsing,
  loader scoping); `test_dashboard.py` + `test_smoke_imports.py` updated. **150 pytest +
  32/8/30 evals green.**

### Check

| # | Result |
|---|---|
| C1 | `make_engagement_id("Contoso Ltd", "DC Exit 2027")` → `contoso-ltd/dc-exit-2027`; a duplicate becomes `…-2` |
| C2 | `loader.load` stamps `engagement_id`, sets the session context, keys the delete on `(engagement_id, source_file)`; a bad id raises before any DB call |
| C3 | `publish_estimate` with `engagement=contoso-ltd/dc-exit` writes only under that prefix; `meta.engagement` set |
| C4 | dashboard still reads the legacy `estimate/` path when nothing is published to an engagement |
| C5 | 150 pytest, evals 32/32 · 8/8 · 30/30 |

### Act

- **Deployed & verified live in rg-landfall (2026-09-08).**
  1. `azd deploy api` — new `query_inventory` / `publish_estimate` code live on `func-tmglwfatwcsa2`.
  2. `schema.sql` applied direct (mssql-python + `AzureCliCredential`) — the DROP+CREATE
     wiped the RLS-free tables and rebuilt all 6 with `engagement_id`, composite PKs, the
     `dbo.fn_engagement_predicate` TVF and the `dbo.EngagementFilter` `SECURITY POLICY`
     (`STATE = ON`); `id-landfall-tmglwfatwcsa2` re-granted `db_datareader + db_datawriter`.
     (`apply_sql.py` via `azd` hung on the serverless resume; ran the batches directly instead.)
  3. Sample estate re-loaded as `_default_/_default_` — servers 250 / applications 31 /
     dependencies 461 / storage 566 / performance 5190, every row stamped `engagement_id`.
  4. Estimate re-published to `answers/engagements/_default_/_default_/estimate/latest.{json,xlsx,docx,pptx}`.
  5. `azd deploy web` — dashboard now reads the engagement-scoped prefix (was pre-C18 code).
  6. Event Grid `landfall-inventory` subscription recreated with subject
     `/blobServices/default/containers/raw/blobs/engagements/`.
  7. `create_agent.py` re-run (managed auth) — agent picks up the ENGAGEMENT SCOPE prompt
     + the `engagement` arg on the 4 specs.
- **Live checks:**
  - RLS fail-closed: no session context → 0 rows; `acme/other` → 0 rows; `_default_/_default_` → 250 servers.
  - Live agent, `engagement=_default_/_default_`: "173 prod servers, 1,436 vCPU" (matches the local repro).
  - Live agent, `engagement=acme-corp/pilot`: "0 servers" — same `dbo.servers` table, isolated by context.
  - First agent call 502'd (Function cold start, 23 s); the retry and all subsequent calls succeed.
- **`schema.sql` still DROPs+recreates on every apply** — fine for `_default_` today, unacceptable
  once real engagements hold data. Tracked for C23 (migration + additive-only schema changes).
- **C19:** `run_engagement` bulk-ingest Function; tighten `engagement` to required + a
  run/publish audit line; `test_evals` per-engagement isolation cases (E11.13).
- **C20:** the dashboard UX (engagements home, new-engagement form, upload panel, start
  analysis).

---

## Plan note — 2026-09-08 — Epic E11 Engagement Workspaces raised

Sponsor: the solution must produce **per-customer / per-project** deliverables, driven
from the dashboard — enter customer + project, upload docs to a **unique ADLS folder per
engagement**, start the analysis, and use a **chat bot with predefined prompt cards**.
Also asked: can the four skills run "at the Foundry agent"?

**Decision & answer** (full write-up: [`engagement-workspaces-prd.md`](engagement-workspaces-prd.md)):

- **Skills cannot be loaded into a Foundry agent** — it has instructions + tools
  (OpenAPI/MCP/Code Interpreter/File Search) + the Responses API, no `SKILL.md` mechanism.
  `docx`/`xlsx` → design references baked into `export.py` (+ a CI recalc gate);
  `presentation-skill`/`ppt-master` → a **containerised OpenAPI tool** (`ca-deckgen`, Node
  toolchain) the agent calls. The agent orchestrates; `export.py` authors the files.
- **Move from "one deployment per engagement" to "one deployment, many engagements,
  isolated by an `<customer>/<project>` key"** — ADLS `raw|answers/engagements/<c>/<p>/…`,
  `engagement_id` column on all 6 SQL tables, `engagement` a required argument on every
  OpenAPI tool + the agent prompt. Hard isolation stays a `--tier regulated` option.
- New epic **E11** (13 items) added to `tracker.md`; scheduled as **PDCA cycles 18–23**.
  E11 is plumbing + UX + tenancy around the existing engine — no maths changes.

**Changes already on `main`** relevant to the sponsor's framing: cycles 15–17 (live
deploy + verification, E8.2 auth, `to_pptx` rebuilt as a narrative deck, generation-model
docs). Nothing multi-engagement is built yet.

---

## Cycle 17 — PowerPoint export rebuilt as a narrative assessment deck (E5.4 / E5.4q)

**Date:** 2026-09-08 · **Owner:** SWE + Writer · **Tracker:** E5.4 (pptx done),
E5.4q (in-progress) · **Trigger:** sponsor — "make the ppt highly professional with the
right visuals, icons, narrative, data, story; refer to Microsoft PPT and `Azure/migration`."

### Plan

`to_pptx` was a text dump on the stock template (11 slides, one big textbox each, no
charts, DRAFT on 1 slide). Rebuild it as a client-facing deck whose *narrative* follows
the Microsoft **Migration Execution Guide** lifecycle, with native charts and a design
system — still pure Python in `export.py` (the tool the Foundry agent calls; **no LLM
authors the file**).

### Do

- **`src/api/deliverable/export.py` — `to_pptx` fully rewritten** (~450 lines). 12 slides:
  cover · executive summary · approach (Assess→Optimise chevron flow) · current state ·
  landing zone · 6R disposition · wave plan · run-rate cost · effort · risk register ·
  next steps · traceability.
- Design system: Segoe UI, Azure palette (`0078D4` / `1B2A4A` / semantic green-amber-red),
  KPI tiles, section rules, a one-line takeaway band per slide.
- **Native charts from package data:** 2 doughnut (6R mix, cost drivers with an "Other"
  slice to 100%), 2 horizontal bar (servers-by-env, effort-by-workstream); a
  colour-coded wave table; a hub-and-spoke landing-zone diagram; numbered next-steps.
- **DRAFT watermark + page number + "Confidential" on every slide** (was 1 of 11);
  speaker notes on every content slide; every figure keeps its `F#` ref.
- `tests/test_export.py` — `test_pptx_opens_and_has_narrative_deck` rewritten (12 slides,
  ≥3 charts, a table, watermark on ≥11 slides). **127 pytest + 32/8/30 evals green.**
- Deployed (`azd deploy api`) and re-published to the live dashboard — the PowerPoint
  button on `/dashboard` now serves the 97 KB narrative deck.

### Check

| # | Result |
|---|---|
| C1 | `to_pptx` renders from the live package: 12 slides, 0 off-slide shapes, 4 charts + 2 tables |
| C2 | degraded package (failed compute tool) still exports all 3 formats |
| C3 | narrative reads end-to-end (exec summary sentence is generated from figures) |
| C4 | 127 pytest green; eval harness 32/32 · 8/8 · 30/30 |

### Act

- E5.4 `.pptx` **done**. **E5.4q** now covers the `.xlsx` (formulas-not-literals +
  LibreOffice-recalc CI gate) and `.docx` (US-Letter DXA + tracked-changes) polish — the
  `docx`/`xlsx` skill rules implemented in `export.py`, plus a CI recalc step.
- **E5.6** (studio deck via `presentation-skill` / `ppt-master`) stays a Phase-2 side-car —
  clarified in the docs that the Foundry agent is never in the generation path.
- Docs updated: audit block, `path-to-5x5` §"Deliverable polish" (generation model +
  role table), PRD E5.4 / E5.6, tracker.

---

## Cycle 16 — Function App EasyAuth, live (E8.2)

**Date:** 2026-09-08 · **Owner:** Security · **Tracker:** E8.2 (done) · **Trigger:**
sponsor said "yes" to the E8.2 follow-up from cycle 15.

### Plan

Turn on the Function App's built-in auth so no `/api/*` route answers anonymously, and
have the agent call every tool with its managed-identity token.

### Do

- **App registration** `landfall-func-tmglwfatwcsa2` (`920abc3e-35f7-4eac-a2e9-b11da46eecb5`),
  identifier URI `api://<guid>`, SP created.
- **Bicep** (`resources.bicep`): `allowedAudiences` now `[<guid>, api://<guid>]`;
  new `functionAuthAllowedClientIds` param → `defaultAuthorizationPolicy.allowedApplications`
  (empty = any tenant token for the audience); `excludedPaths` corrected (see Check).
  Threaded through `main.bicep`.
- **`create_agent.py`**: `AGENT_TOOL_AUTH=managed` now applies `OpenApiManagedAuthDetails`
  to **all 12** OpenAPI tools, not just `query_inventory` — EasyAuth is app-global, so
  it's all-or-nothing. Audience from `FUNC_AUTH_AUDIENCE`.
- `azd env set ENABLE_FUNCTION_AUTH true` / `FUNCTION_AUTH_CLIENT_ID` / `FUNC_AUTH_AUDIENCE`
  / `AGENT_TOOL_AUTH=managed`; `azd provision` (×2 — see Check).
- **DEPLOY.md** step 3 rewritten ("Harden the Function App").

### Check

| # | Result |
|---|---|
| C1 | Anonymous `curl` → **401** on `/api/vm_rightsize`, `/api/query_inventory`, `/api/azure_retail_prices`, `/api/publish_estimate` |
| C2 | Agent (Responses API, MSI) → calls `query_inventory` ×4 + `estimate_compute_cost` ×2, `status: completed`, sourced answer |
| C3 | Event Grid ingestion still fires — re-uploaded `raw/inventory/*`, DQ reports refreshed, 250 servers in SQL |
| C4 | Durable `start` unaffected (same `/runtime/webhooks/blobs` exclusion) |

**Bug found:** EasyAuth matches `excludedPaths` as **literal prefixes** — `"/runtime"`
alone did **not** exclude `/runtime/webhooks/blobs`, so the first provision broke the
Event Grid webhook (validation → 401). Fixed to
`["/runtime/webhooks/blobs", "/runtime/webhooks/durabletask"]`.
**Also:** a hand `az rest PUT` of `authsettingsV2` with only `globalValidation` wiped
`identityProviders` (PUT replaces the whole resource) → re-ran `azd provision` to
restore it declaratively. Lesson: only change `authsettingsV2` through Bicep.

### Act

- E8.2 **done and verified live.** E8 security epic now: E8.1/E8.3/E8.4 done, E8.2 done;
  E8.5–8.7 (private endpoints, thread-principal binding, signed data-handling statement)
  remain in Phase 2.
- **Follow-ups:** (1) set `functionAuthAllowedClientIds` to the Foundry MSI client id to
  restrict callers (Stage 2). (2) `schema.sql` drops+recreates every table on each
  `azd provision` — wipes loaded inventory; needs idempotent `IF NOT EXISTS` + a real
  migration path. (3) move `create_agent.py` to the postdeploy hook.

---

## Cycle 15 — first live deployment + verification pass (E1.6, E5.5, E5.4)

**Date:** 2026-09-08 · **Owner:** SWE · **Tracker:** E1.6 (done), E5.5 (verified),
E5.4 (verified) · **Trigger:** sponsor gave subscription access
(`f609eb5b…`, `rg-landfall`, swedencentral) — deploy cycles 5–14 and verify live.

### Plan

- `azd provision` + `azd deploy` to lift the running environment from ~cycle 11 to
  cycle 14 (SQL guard, Office exports, `publish_estimate`, dashboard, 12-tool agent).
- Verify the three items that need a real subscription: **E1.6** ingestion end-to-end
  (Event Grid + operator HTTP), **E5.5** `publish_estimate` → `/dashboard`, **E5.4**
  Office exports generated server-side.

### Do

- `azd provision` — Bicep idempotent; postprovision re-applied schema (7 batches via
  `apply_sql.py` — no sqlcmd), rebuilt the search index, recreated the agent.
- `azd deploy` — `src/api` (20 functions incl. the 8 new tool routes) + `src/web`
  (dashboard) live.
- Re-ran `create_agent.py` → agent **v4**, 14 tools (2 built-in + 12 OpenAPI), active.
- Recreated the `landfall-inventory` Event Grid subscription.
- Ingested the sample estate (`raw/inventory/*` → SQL): 250 servers / 31 apps /
  484 deps / 566 storage / 5190 perf rows; DQ reports in `answers/_ingest/`.
- `publish_estimate` (live) wrote `answers/estimate/latest.{json,xlsx,docx,pptx}`.
- Ran the web app against live storage: `/dashboard` 200, `/dashboard/data` returns the
  package, `/dashboard/download/{xlsx,docx}` stream with the right mime, bad fmt → 400.
- Agent smoke test (Responses API): "servers by env + rough 3yr-RI compute cost" →
  calls `query_inventory` then `estimate_compute_cost`, returns the
  Answer/Basis/Assumptions/Data-gaps/Confidence block. Numbers match direct SQL
  (250 / 1940 vCPU / 10 528 GB).

### Check — three bugs found and fixed

| # | Bug | Fix |
|---|---|---|
| B1 | `apply_sql.py` granted the workload identity `db_datareader` only; the ingestion loader needs INSERT/DELETE → every load failed `DELETE permission was denied`. | Grant `db_datareader` **+ `db_datawriter`**. `query_inventory` stays SELECT-only via `sqlguard.py` (code, not DB perm). Identity split tracked under E8. |
| B2 | `eventgrid.sh` run under Git Bash: MSYS rewrote `--subject-begins-with "/blobServices/…"` to `C:/Program Files/Git/blobServices/…`, so the inventory subscription matched nothing. | `export MSYS_NO_PATHCONV=1` / `MSYS2_ARG_CONV_EXCL="*"` + a post-create filter assertion in the script. |
| B3 | Text-to-SQL `SCHEMA_HINT` had no enum note for `powerstate`; agent guessed `= 'on'` (data is `poweredOn`/`poweredOff`) → "no servers". | Add value hints for `powerstate`, `dependencies.direction`, `dependencies.confidence`, `compliance_scope`. Redeployed; agent smoke test then correct. |

Serverless SQL auto-pause: first connection after idle returns "database is not
currently available"; a retry wakes it (~40 s). Expected, not a bug — noted for the SOP.

### Act

- **Verified live:** E1.6 (both ingestion paths), E5.4 (server-side Office export),
  E5.5 (dashboard reads the published package + downloads).
- **Still open:** **E8.2** — Function App EasyAuth (needs an Entra app registration +
  `AGENT_TOOL_AUTH=managed` re-run of `create_agent.py`); the func routes are anonymous
  today, guarded only by `sqlguard`. Next deliberate step.
- **Follow-ups:** `create_agent.py` should move to a **postdeploy** hook (on a first-ever
  `azd up`, `SERVICE_API_NAME` isn't set at postprovision time, so the OpenAPI tools are
  skipped — the WARN path — and need a manual re-run). Phase 1 tail unchanged
  (E4.3 / E6.2 / E1.7).

---

## Cycle 14 — assessment dashboard web app (E5.5)

**Date:** 2026-09-08 · **Owner:** SWE · **Tracker:** E5.5 (done) · **Sponsor ask:** an
Azure Migrate–style interactive dashboard on the Container App with in-page export.

### Plan

- **`publish_estimate`** (Function) — assemble → write `answers/estimate/latest.json` +
  `latest.{xlsx,docx,pptx}` to blob.
- **`src/web`** — the FastAPI Container App gains `/dashboard` (static page),
  `/dashboard/data` (the package JSON from blob, 404 if unpublished),
  `/dashboard/download/{fmt}` (streams the export blob). Chat client lazy-init'd so the
  container starts without Foundry.
- **`src/web/dashboard.html`** — a self-contained page (no CDN): header with DRAFT
  badge + confidence pill + Excel/Word/PPT buttons; a strip of headline tiles; a panel
  grid (inventory & readiness with a by-env bar chart; run-rate cost with a donut +
  driver table; landing zone with spoke chips; 6R as a stacked bar; the wave table with
  per-wave risk bars; effort with a workstream bar chart); a collapsible calculation
  appendix and the register. Every figure shows its `F*` id. Light + dark.
- **Bicep** — `STORAGE_URL` env on the container app.

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | `publish_estimate` writes exactly `latest.json` + 3 exports; the JSON round-trips | `test_dashboard` |
| C2 | `publish_estimate` rejects an empty body | `test_dashboard` |
| C3 | `/dashboard` serves the page and wires `/dashboard/data` + the 3 download links | `test_dashboard` |
| C4 | `/dashboard/data` → 404 when nothing published; returns the package when it is | `test_dashboard` |
| C5 | `/dashboard/download/{fmt}` streams with the right mime + attachment header; bad fmt → 400 | `test_dashboard` |
| C6 | `/healthz` reports `estimate_published` | `test_dashboard` |
| C7 | renders correctly against a real package (visual check) | Playwright screenshot |

### Do

- `src/api/deliverable/functions.py` — `_container_client` + `POST /api/publish_estimate`.
  `src/api/openapi/publish_estimate.json` + `create_agent.py` tool #12.
- `src/web/app.py` — lazy OpenAI client, `_read_estimate_blob`, 3 dashboard routes,
  `/healthz` extended, chat header links `/dashboard`. `src/web/dashboard.html` — new.
  `src/web/requirements.txt` — `azure-storage-blob`. `infra/resources.bicep` — container
  `STORAGE_URL`.
- `tests/test_dashboard.py` — 7 cases (127 total); `fastapi` + `httpx` added to
  `tests/requirements-dev.txt`. `DEPLOY.md`, `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **127 passed**. Visual: rendered the dashboard against the full
sample package (Playwright) — headline tiles, the by-env bars, the cost donut (with an
"Other" slice to 100%), the spoke chips, the 6R stacked bar, the 7-wave risk table, the
workstream bars, the collapsible appendix — all correct, Azure-portal-like, light+dark.

### Act

- **E5.5 done.** The estimate is now (a) a JSON package, (b) a markdown render, (c)
  Excel / Word / PowerPoint files, and (d) an interactive dashboard the client opens by
  URL and exports from.
- **Watch:** the dashboard needs `publish_estimate` to have been called (shows a
  friendly "nothing published yet" state otherwise). The container-app routes are
  behind the same Easy Auth as the chat page (manual, per DEPLOY step 1). A live `azd
  deploy web` is the real confirmation (same bucket as E1.6 / E8.2).
- **Phase 1 backlog left:** E1.7 (mapping override), E4.3 (duration model), full E6.2
  resource loading. **Phase 1 engine is otherwise complete.**
- **Next:** E1.6 / E8.2 / E5.5 live verification via `azd`, then Phase 2 (evidence pack).

---

## Cycle 13 — client-ready exports: Excel / Word / PowerPoint

**Date:** 2026-09-08 · **Owner:** SWE + Staff Writer · **Tracker:** E5.4 (done) ·
**New scope** from the sponsor: the deliverable must ship as `.xlsx` / `.docx` / `.pptx`.

### Plan

`deliverable/export.py` — `export(package, fmt) -> (bytes, filename, mime)`:
- **xlsx** (openpyxl): Cover, Headline, a sheet per section, Calculation appendix,
  Register — styled headers, frozen panes, auto widths.
- **docx** (python-docx): title page + DRAFT watermark, headline table, every section,
  the appendix table, the register lists.
- **pptx** (python-pptx): title, headline numbers, one slide per section, assumptions.

Every figure keeps its `F*` ref; all three carry the watermark. `POST /api/export_estimate`
(`{format, package}` or the assemble inputs). Deterministic from the package.

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | unknown format → ValueError / 400 | `test_export` |
| C2 | xlsx opens; one sheet per section + Cover + Appendix + Register; every `F*` in the appendix | `test_export` |
| C3 | docx opens; carries "DRAFT"; has the appendix; every register id present | `test_export` |
| C4 | pptx opens; title + headline + one slide per section + assumptions | `test_export` |
| C5 | content is deterministic (parsed, ignoring the zip timestamp) | `test_export` |
| C6 | a degraded package (a failed tool) still exports all three | `test_export` |

### Do

- `src/api/deliverable/export.py` — new. `deliverable/functions.py` —
  `POST /api/export_estimate`. `__init__.py` exports `export`.
- `src/api/requirements.txt` + `tests/requirements-dev.txt` — `python-docx`,
  `python-pptx`. `src/api/openapi/export_estimate.json` + `create_agent.py` tool #11.
- `tests/test_export.py` — 6 cases (120 total). `DEPLOY.md`, `README.md`,
  `tests/README.md` updated.

### Check

`pytest tests -q` → **120 passed**. Sample pipeline → `landfall-estimate.xlsx` (18 KB,
12 sheets), `.docx` (41 KB, 85 paras / 3 tables), `.pptx` (40 KB, 11 slides); all three
re-open cleanly and every figure id appears in the workbook's appendix.

### Act

- **E5.4 done.** The estimate is now downloadable in the three Office formats.
- **Next — Cycle 14:** E5.5 — the Azure Migrate–style assessment dashboard on the
  `src/web` Container App: read the assembled package (written to blob by the assemble
  step), render the interactive panels, wire the "Download Excel / Word / PPT" buttons
  to `export_estimate`. Needs an assemble→blob "publish" step + the dashboard page +
  vendoring or an API call for the render.

---

## Cycle 12 — security & isolation, self-contained hooks (Phase 1 close)

**Date:** 2026-09-08 · **Owner:** Security & Compliance Architect + SRE · **Tracker:**
E8.3 / E8.4 / E9.1 done; E8.1 / E8.2 in-review · **Closes audit** SEC-1/2/3/8, P0-8, OPS-5.

### Plan

- **E8.3** replace the keyword-blocklist `_safe_select` with an allow-list parser:
  single `SELECT`/`WITH`, only the six inventory tables, no comments hiding keywords,
  no `sys.`/`information_schema`/`WAITFOR`/`OPENROWSET`/…; add a statement timeout.
- **E8.4** the question and generated SQL never reach the logs — log a `sha256[:12]`
  hash + the table list + the query shape only.
- **E9.1** move the schema load + `db_datareader` grant off `sqlcmd` into
  `scripts/apply_sql.py` (pure Python, `mssql-python` + Entra token) so the hook needs
  neither `sqlcmd` nor `azd` on PATH.
- **E8.2** wire Function-App EasyAuth into the Bicep (`enableFunctionAuth` param, off by
  default, `excludedPaths ["/runtime"]`) so turning auth on is `azd env set` + `azd
  provision`, not a manual CLI recipe.
- **E8.1** document + verify one datastore per engagement (`resourceToken` already makes
  every resource env-unique; `azd down --purge`).

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | guard accepts real analytics (joins, CTEs, group-by, TOP, trailing comment) | `test_sqlguard` |
| C2 | guard rejects 2nd statement, non-SELECT, `sys.`/`information_schema`, unknown table, `WAITFOR`, `INTO`, `OPENROWSET`, comment-hidden `UNION sys.*`, unbalanced parens | `test_sqlguard` |
| C3 | table allow-list is exactly the six inventory tables; CTE names aren't flagged | `test_sqlguard` |
| C4 | `signature()` contains no question text and no SQL text; hash is stable | `test_sqlguard` |
| C5 | `query_inventory` logs a hash + tables + shape, never the text | code review |
| C6 | `apply_sql.py` splits `schema.sql` on `GO`, skips comment-only batches | unit-ish check |
| C7 | `az bicep build` clean with the new auth param (default off = no behaviour change) | `az bicep build` |

### Do

- `src/api/sqlguard.py` — new (`safe_select`, `signature`, `ALLOWED_TABLES`). `tools.py`
  — imports it, drops the old guard, adds `QUERY_TIMEOUT_S` + `cur.timeout`, scrubs
  every `logging.*` call (hash only).
- `scripts/apply_sql.py` — new. `postprovision.{sh,ps1}` — call it instead of the
  `sqlcmd` block. `scripts/requirements.txt` — `mssql-python`.
- `infra/{main,resources}.bicep` + `main.parameters.json` — `enableFunctionAuth` /
  `functionAuthClientId` params + `authsettingsV2` (conditional) + `QUERY_TIMEOUT_S`
  app setting.
- `tests/test_sqlguard.py` — 20 cases (114 total). `DEPLOY.md` updated (sqlcmd removed,
  auth recipe, isolation note).

### Check

`pytest tests -q` → **114 passed** (20 new). `az bicep build infra/main.bicep` → clean.
`apply_sql._run_batches` over `schema.sql` → 7 real batches, trailing comment skipped.
Guard spot-checks: `SELECT ... FROM sys.databases` → blocked (`sys.`); `SELECT * FROM
servers /* x */ UNION SELECT name,1,2 FROM sys.tables` → blocked; `WITH prod AS (...)
SELECT COUNT(*) FROM prod` → accepted.

### Act

- **E8.3 / E8.4 / E9.1 done.** `query_inventory` is now allow-list-parsed, timed out,
  and log-safe; the deploy no longer needs `sqlcmd`.
- **E8.2 / E8.1 in-review** — the Bicep path is ready and defaults off (no behaviour
  change); a live `azd provision` with `ENABLE_FUNCTION_AUTH=true` + an app registration
  is needed to confirm anonymous → 401 and the agent still works via MSI. Same live-verify
  bucket as E1.6.
- **Phase 1 backlog left:** E1.7 (mapping override), E4.3 (duration model), full E6.2
  resource loading, E8.5–8.7 / E9.2–9.5 (Phase 2). Plus the live checks (E1.6, E8.2).
- **New scope from the sponsor (this session):** client-ready **XLSX / DOCX / PPTX**
  exports of the estimate package, and an **Azure Migrate–style assessment dashboard**
  web app on the existing Container App from which end users export those artifacts.
  Added to the PRD as **E5.4** (exports) and **E5.5** (assessment web app). Next cycles.
- **Next — Cycle 13:** E5.4 — `deliverable/export.py`: the assembled package →
  a formatted Excel workbook, a Word document, and a PowerPoint deck.

---

## Cycle 11 — fault injection, output guard, CI gate

**Date:** 2026-09-08 · **Owner:** Applied Scientist + SRE · **Tracker:** E7.3 / E7.4 /
E7.5 (done) · **Closes audit** AI-3..6 (a tool failure or an un-sourced number could
slip through; nothing gated regressions).

### Plan

- **E7.3 fault injection** — every deterministic HTTP tool, given a broken request,
  returns a clean error (HTTP ≥ 400, body = an `error` string only) and never a 200
  with fabricated numbers; `assemble_estimate` omits a section when an upstream slot
  carries `{"error": ...}`.
- **E7.4 output guard** — a checker that flags any numeric claim (money, %, unit'd
  counts, magnitudes ≥ 1000) not backed by a tool value or a citation; run it against
  each scenario's own `summary_markdown` (the deliverable must be self-sourcing).
- **E7.5 CI gate** — a GitHub Actions workflow runs `pytest` + `evals/runner.py` on
  every push / PR; a stale `SCORECARD.md` or any regression fails the build. Changes to
  `scripts/create_agent.py` ride the same gate.

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | every tool leaks nothing on a bad request (empty / wrong-type / missing) | `run_faults` / `test_evals` |
| C2 | `assemble_estimate` degrades: failed slot → section omitted, gap recorded, no fabricated figure | `run_faults` |
| C3 | output guard passes a real package render; flags a planted un-sourced number | `test_evals` |
| C4 | guard is quiet on dates, structural ints, and cited assumption/basis lines | manual + scenario runs |
| C5 | `evals/runner.py` exits non-zero on any golden / scenario / fault / guard failure | manual |
| C6 | CI workflow runs the full gate and diffs `SCORECARD.md` | `.github/workflows/evals.yml` |

**Design.** `evals/faults.py` (drives the real route functions with a fake
`func.HttpRequest`), `evals/output_guard.py` (`check_message` + `sourced_from_package`),
`runner.py` gains `run_faults` + a per-scenario guard check + a fault section in the
scorecard, `.github/workflows/evals.yml`. `assemble._ok()` skips a tool slot with an
`error` key and records the gap (+ `meta.tools_failed`).

### Do

- `evals/{faults,output_guard}.py` — new. `evals/runner.py` — `run_faults`, guard in
  `run_scenarios`, `scorecard(golden, scenarios, faults)`, dropped the daily date so the
  committed `SCORECARD.md` is stable. `evals/SCORECARD.md` regenerated (now 3 suites).
- `src/api/deliverable/assemble.py` — `_ok()` + `failed_tools` + register gap +
  `meta.tools_failed`.
- `.github/workflows/evals.yml` — new. `tests/test_evals.py` — +4 cases (94 total).
  `evals/README.md`, `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **94 passed**. `python evals/runner.py` → **PASS**:
```
Golden text-to-SQL (E7.1)                      32/32 (100%)   ✅
Full-estimate scenarios + output guard (E7.2/E7.4)  8/8       ✅
Fault injection (E7.3)                         26/26          ✅
```
Faults: 8 tools × 3–4 broken bodies each → all return `{"error": ...}` at 4xx/5xx;
the downstream case (compute + storage slots = `{"error": ...}`) → `tools_failed`
lists both, no compute/storage figures, register carries the gap. Guard: catches
`$2,400,000/year` / `1,200 person-days` / bare `63%`; passes every scenario's render.

### Act

- **E7 epic complete** (E7.1–E7.5). The engine now has a correctness gate that runs on
  every change.
- **Watch:** the output guard is heuristic — it challenges *claims*, not every digit,
  and exempts assumption/basis prose. It's a safety net for the agent's free text, not
  a formal proof; the live "agent never states an un-sourced number" drill is Phase 2.
  The CI workflow hasn't run yet (no push has triggered it) — first green run is the
  real confirmation.
- **Next — Cycle 12:** E8 (security & isolation — `query_inventory` auth on by default,
  allow-list SQL parse + statement timeout, SQL text out of logs, one datastore per
  engagement) + E9.1 (self-contained hooks). That closes Phase 1.

---

## Cycle 10 — eval harness (golden SQL + full-estimate scenarios)

**Date:** 2026-09-08 · **Owner:** Applied Scientist + FinOps + SRE · **Tracker:**
E7.1 / E7.2 (done) · **Closes audit** P0-7 / AI-1..8 (nothing proved the tools stay
correct as the agent, prices, or SKUs change).

### Plan

**Objective.** An offline harness that gates correctness:
- **E7.1** a golden text-to-SQL set (≥30 `question → T-SQL → expected` cases) run
  against a SQLite copy of the sample estate; each SQL must pass `tools._safe_select`
  and match its expected result exactly. Gate: ≥95%.
- **E7.2** ≥8 full-estimate scenarios — run the whole tool chain + `assemble_estimate`
  with deterministic synthetic price books and assert every headline figure lands in an
  expected band, every figure is traceable, and a re-run is byte-identical.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | ≥30 golden cases; ≥95% exact match over the sample | `runner.run_golden` / `test_evals` |
| C2 | every golden SQL passes the read-only SELECT guard | `test_evals` |
| C3 | ≥8 scenarios, all pass (figures in band + traceable + deterministic) | `runner.run_scenarios` / `test_evals` |
| C4 | scenarios exercise real levers (RI term, AHB, dev/test, appetite, DQ, slice) | scenarios.json |
| C5 | `python evals/runner.py` exits non-zero on any failure; writes SCORECARD.md | manual |

**Design.** `evals/` — `sample_db.py` (CSV → in-memory SQLite + a small test-only
T-SQL→SQLite shim: `TOP`→`LIMIT`, `GETDATE()`→fixed date, `DATEDIFF`, `ISNULL`…),
`fixtures.py` (synthetic price/rate books), `pipeline.py` (run every tool → assemble),
`runner.py` (golden + scenarios + scorecard + exit code), `golden_sql.json` (32 cases),
`scenarios.json` (8). `tests/test_evals.py` wraps it so `pytest` catches regressions.

**Deferred.** E7.3 fault-injection (each tool 5xx → agent reports, never invents),
E7.4 output guard (reject un-sourced numeric claims), E7.5 CI gate on every
`create_agent.py` change — next cycle. The live "model generates matching SQL" gate
needs credentials and belongs in CI.

### Do

- `evals/{sample_db,fixtures,pipeline,runner}.py`, `evals/{golden_sql,scenarios}.json`,
  `evals/README.md`, `evals/SCORECARD.md` (generated).
- `tests/test_evals.py` — 4 wrapper cases. `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **91 passed**. `python evals/runner.py` → **PASS**:
```
Golden text-to-SQL (E7.1)        32/32 (100%)   gate ≥95%   ✅
Full-estimate scenarios (E7.2)   8/8                        ✅
```
The 32 golden queries span servers / apps / storage / dependencies / performance —
counts, sums, group-bys, top-N, EOL date logic, distinct scopes. The 8 scenarios move
the RI term, AHB, dev/test pricing, disposition appetite, DQ confidence, and the estate
slice, and each lands in-band (e.g. no-AHB run-rate $132.6k vs house $113.9k;
aggressive-appetite effort 968 PD vs 834).

### Act

- **E7.1 / E7.2 done.** `SCORECARD.md` is committed as the evidence artifact; the runner
  regenerates it and any purposeful maths change re-commits it with adjusted expecteds.
- **Watch:** the SQLite shim is deliberately narrow — a golden query using a T-SQL
  construct it doesn't cover will error in the runner (not silently pass). Keep golden
  SQL within the documented shim surface or extend `sample_db.to_sqlite`.
- **Next — Cycle 11:** E7.3 / E7.4 / E7.5 — fault-injection harness, the un-sourced-
  number output guard, and the CI scorecard gate. Then E8 / E9 (security + ops), which
  finishes Phase 1.

---

## Cycle 9 — assemble_estimate (the structured deliverable)

**Date:** 2026-09-08 · **Owner:** PM + Staff Writer + SWE · **Tracker:** E5.1 / E5.2 /
E5.3 (done), E2.5 (done), E6.2 (basic) · **Closes audit** P0-5 / PS-2..4 (output was a
chat transcript, figures had no provenance, the assumptions register was hand-merged).

### Plan

**Objective.** `assemble_estimate` — stitch the other tools' outputs + an inventory
summary into ONE package:
- **E5.1** 8 sections (config-driven list).
- **E5.2** a stable ID on every headline figure + a calculation-appendix entry per
  figure (source tool, inputs, formula, assumptions applied, confidence).
- **E5.3** a machine-built assumptions / exclusions / data-gaps register, collected from
  every tool's own `assumptions` / `caveats` / `not_costed` / `missing_prices` /
  `needs_human_decision` arrays + the DQ report + standing exclusions — deduped, ID'd,
  categorised.
- **E2.5** top-3 cost drivers on the run-rate total.
- **E6.2 (basic)** a parametric person-day + services-cost estimate (contingency tied to
  the DQ confidence — E6.3).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | Assembles from inventory alone; a tool not run leaves its section marked, not dropped | unit test |
| C2 | Every figure has a calculation-appendix entry with a non-empty formula + source | unit test |
| C3 | Register collects each tool's caveats + standing exclusions; deduped and ID'd | unit test |
| C4 | Run-rate figures reconcile (compute + storage + extras); top-3 drivers ranked | unit test |
| C5 | Effort contingency = 8/12/20% for High/Medium/Low DQ confidence | unit test |
| C6 | Effort range + services cost reconcile | unit test |
| C7 | Overall confidence = worst of the figure confidences | unit test |
| C8 | Full pipeline (6 tools → assemble) is deterministic over the sample estate | unit test |

**Design.** `src/api/deliverable/{effort,assemble}.py` — pure, tool outputs injected.
`deliverable/functions.py` — `POST /api/assemble_estimate`. New `effort` (extended) +
`deliverable` config blocks. OpenAPI spec + agent tool #10 + prompt line.
`deliverable_bp` in `function_app.py`. Markdown render built in.

**Deferred.** Full effort model (wave-by-wave resource loading, peak FTE, the loading
curve) = a later E6.2 cycle. A rendered PDF/DOCX export = out of scope (the markdown
drops into the proposal template).

### Do

- `src/api/deliverable/{__init__,effort,assemble,functions}.py` — new package.
  `function_app.py` — `deliverable_bp`. `cost/config.py` — `effort` extended + new
  `deliverable` block.
- `src/api/openapi/assemble_estimate.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 10) + `SYSTEM_PROMPT` line.
- `tests/test_deliverable.py` — 7 cases incl. the full-pipeline test. `estimation_config.json`,
  `DEPLOY.md`, `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **87 passed**. C1–C8 pass (see test names).

Full pipeline over the sample estate (real prices + live storage rates):
```
HEADLINE       run-rate  $119,181 /mo   $1,430,167 /yr   (confidence Low)
               one-time  $77,170
               effort    834 PD (709–959)   services ~$650,286 ($553k–$748k)
SECTIONS       8 (current state / LZ / 6R / waves / run-rate / effort / register / next steps)
FIGURES        14, each with a formula + inputs + confidence in the appendix
REGISTER       28 assumptions · 6 exclusions · 8 data gaps  (all source-tagged)
TOP DRIVERS    compute effective 47% · managed disk 25% · monitoring 10%
```

### Act

- **E5.1/E5.2/E5.3 + E2.5 done. E6.2 partial** (basic parametric; full resource-loading
  model is a later cycle — tracker E6.2 stays `in-review` with that note).
- The deliverable is the audit's review-drill target: "hand it to an uninvolved
  architect; they answer 'where did this come from?' for 10 random figures using only
  the document." The calculation appendix + register are built for exactly that.
- **Watch:** effort execution-PD-per-disposition and the LZ/testing/hypercare constants
  are first-pass — a firm calibrates them against `sample-estate/effort-inputs.md`
  (which lands EAC ~775 PD; the tool gives ~834 for Medium confidence — same ballpark).
- **Next — Cycle 10:** E7.1/E7.2 — the eval harness: a golden text-to-SQL set (30+) with
  a runner, and full-estimate scenarios (8+) with expected ranges, 0 un-sourced numbers,
  identical on re-run. Uses the `microsoft-foundry` skill.

---

## Cycle 8 — score_dispositions + plan_waves (the wave engine)

**Date:** 2026-09-08 · **Owner:** Architect + PM + SWE · **Tracker:** E4.1 / E4.2 (done) ·
**Closes audit** P0-4 / MA-1..5 (no move-group / wave plan — the agent was inventing them).

### Plan

**Objective.** Two deterministic tools:
- **`score_dispositions` (E4.2)** — a rule-derived 6R candidate + rationale + confidence
  per app from inventory signals (servers, EOL OS, criticality, internet-facing, DB
  engine, stack, retire/repurchase markers). The agent explains it, never invents it.
- **`plan_waves` (E4.1)** — server dependency graph → drop stale / low-confidence /
  commodity (AD, DNS, NTP) edges → roll up to app-to-app edges → affinity move-groups
  (connected components) → risk-score each group → order low-risk-first into waves
  (platform wave 0, pilot next, regulated last), capped by servers/apps per wave, with
  entry/exit criteria and cross-wave blocking dependencies (real + dropped-but-flagged).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | 0 servers / retire marker → Retire; repurchase marker → Repurchase | unit test |
| C2 | small single-PaaS-DB low-criticality app → Replatform; clustered DB → Rehost (IaaS) | unit test |
| C3 | tier-1 PaaS-DB app → Rehost but notes the Replatform alternative; `aggressive` appetite flips it | unit test |
| C4 | EOL-OS servers noted on the Rehost rationale | unit test |
| C5 | chatty apps land in one move-group; standalone apps are singletons | unit test |
| C6 | stale / low-confidence / commodity edges excluded and counted | unit test |
| C7 | platform (shared-infra) group is wave 0; regulated group is last; pilot is low-risk | unit test |
| C8 | per-wave server / app cap splits into multiple waves | unit test |
| C9 | a dropped edge across waves is surfaced as an `unverified` blocking dependency | unit test |
| C10 | deterministic over the full sample estate | unit test |

**Design.** `src/api/waves/{disposition,plan}.py` — pure (own union-find, no graph lib).
`waves/functions.py` — `POST /api/score_dispositions` + `POST /api/plan_waves`. New
`disposition` + `waves` blocks in `cost/config.py` + `estimation_config.json`. 2 OpenAPI
specs + agent tools #8/#9 + prompt lines. `waves_bp` wired into `function_app.py`.

**Deferred.** E4.3 duration model (servers/wave ÷ throughput → dated plan + critical
path) — needs the effort model (E6.2). Same-wave non-prod-before-prod is a scheduling
note, not a separate wave.

### Do

- `src/api/waves/{__init__,disposition,plan,functions}.py` — new package.
  `function_app.py` — `waves_bp`. `cost/config.py` — `disposition` + `waves` blocks.
- `src/api/openapi/{score_dispositions,plan_waves}.json` — new. `scripts/create_agent.py`
  — `_OPENAPI_TOOLS` (now 9) + `SYSTEM_PROMPT` lines.
- `tests/test_waves.py` — 14 cases. `estimation_config.json`, `DEPLOY.md`, `README.md`,
  `tests/README.md` updated.

### Check

`pytest tests -q` → **80 passed**. C1–C10 pass (see test names).

Full sample estate (31 apps, 250 servers, 484 dependency rows):
```
DISPOSITIONS  Rehost 25 / Replatform 3 / Repurchase 2 / Retire 1
  Replatform: Corporate Website (CMS), Document Management, Procurement Portal  (all low conf)
  Repurchase: Learning Management, [Collaboration]      Retire: Analytics Sandbox
  needs_human_decision: 6

GRAPH  31 app nodes, 0 app edges, 31 components   (362 commodity/platform edges excluded,
       0 stale after the filter, platform_apps = [app-31])
  -> the sample's only cross-app coupling is AD/DNS/shared-infra; every business app is
     self-contained. Affinity clustering will bind groups on a messier real estate.

WAVES  0 platform  (app-31, 35 srv, high — foundation)
       1 pilot     (2 apps, 3 srv, medium — incl. the Retire app)
       2 standard  (6 apps, 23 srv, risk 47)
       3 standard  (6 apps, 30 srv, risk 60)
       4 standard  (6 apps, 29 srv, risk 71)
       5 standard  (6 apps, 29 srv, risk 77)
       6 regulated (5 apps, 34 srv, risk 79 — PCI-DSS + HIPAA, QSA gate)
```
7 waves, risk rising 47→79 across the standard band — matches the discovery answer's
7-wave shape, but derived from `dependencies.csv` + `applications.csv`.

### Act

- **E4.1 / E4.2 done.** The migration plan (move-groups + risk-ordered waves) and the 6R
  disposition are now deterministic tools.
- **Watch:** the sample's dependency data has no cross-app application-layer flows (all
  LDAP/DNS) so every app is a singleton move-group. That's a property of the synthetic
  data, not a bug — a real RVTools/DR-Migrate export with app-tier flows exercises the
  affinity clustering. Consider adding a few cross-app HTTP flows to `sample-estate` to
  demo it (candidate for a follow-up).
- **Next — Cycle 9:** E5.1/E5.2/E5.3 — "assemble estimate" into one structured
  deliverable (8 sections), stable IDs + calculation appendix on every figure, and the
  machine-tracked assumptions & exclusions register. Plus E2.5 (top-3 cost drivers)
  folds in here.

---

## Cycle 7 — design_landing_zone (CAF ALZ from the portfolio)

**Date:** 2026-09-08 · **Owner:** Architect (CAF/Landing Zones) + SWE · **Tracker:**
E3.1 / E3.2 / E3.3 (done) · **Closes audit** P0-3 / LZ-1..3 (no landing-zone output —
the biggest "toy → real" gap).

### Plan

**Objective.** A deterministic tool that turns the application portfolio + a server
summary into a **client-specific** CAF Azure Landing Zone: management-group hierarchy,
subscriptions, hub-spoke VNets + IP plan, policy set, identity, connectivity, DR, and a
**dedicated regulated spoke** (+ Confidential MG + CMK/private-endpoint overlay) for
every distinct compliance scope in the portfolio. The topology must be *derived* — swap
the portfolio and the spoke count / regulated flag change (E3.2). Resiliency tier per
app from criticality 1–4 (E3.3).

**Why a tool and not the `azure-enterprise-infra-planner` skill:** that skill is a
7-phase interactive IaC-generation pipeline (Bicep/Terraform + deploy, MCP-tool driven)
— it's what a delivery architect runs *after* the estimate. Landfall needs the
deterministic design the agent quotes during pre-sales. The tool's output is shaped as a
requirements document to hand to that skill downstream (`next_step` field).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | Zone rules: internet_facing→Online; regulated scope→Regulated; else Corp | unit test |
| C2 | No regulated app ⇒ no regulated spoke, no Confidential MG, no overlay | unit test |
| C3 | A regulated app ⇒ dedicated spoke pair + Confidential MG + CMK/PE + built-in initiative | unit test |
| C4 | Swapping the portfolio changes the spoke count and the zone set | unit test |
| C5 | IP plan blocks are inside the supernet and non-overlapping | unit test |
| C6 | criticality → resiliency tier; DR rollup counts | unit test |
| C7 | identity_model switch changes the hub (DCs vs none) | unit test |
| C8 | Deterministic over the full sample portfolio | unit test |

**Design.** `src/api/lz/design.py` — pure. `lz/functions.py` —
`POST /api/design_landing_zone`. New `landing_zone` block in `cost/config.py` DEFAULTS +
`estimation_config.json`. OpenAPI spec + agent tool #7 + prompt line. Wired into
`function_app.py` (`lz_bp`).

**Deferred.** Business-domain spoke grouping (the tool uses CAF archetype grouping —
zone × env; a per-app-affinity spoke map is an E4 wave-engine concern). Bicep
generation (hand off to the skill). Cost of the LZ platform itself (fixed services —
commercial line).

### Do

- `src/api/lz/{__init__,design,functions}.py` — new package. `function_app.py` —
  `lz_bp` registered. `cost/config.py` — `landing_zone` block.
- `src/api/openapi/design_landing_zone.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 7) + `SYSTEM_PROMPT` LZ line.
- `tests/test_landing_zone.py` — 8 cases. `estimation_config.json`, `DEPLOY.md`,
  `README.md`, `sample-estate/effort-inputs.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **66 passed**. C1–C8 pass (see test names).

Full sample portfolio (31 apps) + server summary:
```
CAF ALZ, swedencentral (DR westeurope). 9 spokes: 16 corp / 10 online / 5 regulated.
regulated: HIPAA, PCI-DSS  -> dedicated spoke pair + alz-confidential MG + policy overlay
  (CMK, deny public access, private endpoints, PCI DSS v4 + HIPAA HITRUST initiatives)
MGs:  platform{connectivity,identity,management} / landingzones{corp,online,confidential}
      / sandbox / decommissioned
subs: 3 platform + 8 LZ + sandbox = 12
IP:   hub 10.100.0.0/22 ; spokes 10.100.4.0/22 .. 10.100.36.0/22 ; DR supernet 10.104.0.0/14
hub:  ExpressRoute GW + backup VPN GW + Azure Firewall Premium (forced tunnel) + Bastion
      + Private DNS Resolver + 2x AD DC (extend AD)
DR:   region pair; ASR + native DB replication for tiers 1-2; tiers 3-4 from GRS backup
tiers: 13 T1 / 8 T2 / 6 T3 / 4 T4  (= criticality mix)
```
Matches the discovery answers (SC2 CMK, ID3 extend-AD, N2 ER+VPN, N7 forced tunnel,
B4/R3 Sweden Central + West Europe + AZs) — but derived from `applications.csv`, not the
discovery doc.

### Act

- **E3.1/E3.2/E3.3 done.** The landing-zone deliverable — the audit's #1 gap — now
  exists as a deterministic, portfolio-driven tool.
- **Watch:** HIPAA (1 app) gets its own spoke pair + subs. That's the correct
  conservative default (isolate per compliance boundary); a firm that folds HIPAA into
  the PCI segment edits `landing_zone.regulated_scopes`.
- **Next — Cycle 8:** E4.1/E4.2 — `plan_waves` (dependency graph → move groups →
  risk-ordered waves) + the deterministic 6R disposition scorer.

---

## Cycle 6 — estimate_run_rate_extras (run-rate + one-time migration cost)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.4 (done).

### Plan

**Objective.** The lines beyond compute + storage that still land on the monthly Azure
bill — **backup** (vault storage + protected-instance fees), **internet egress** (from
`net_out_gb_30d`), **monitoring** (Log Analytics ingestion + Defender for Servers),
**support plan** — plus the **one-time** cost of the migration (Azure Migrate/ASR
tooling after its free window, replication egress, dual-running on-prem + Azure during
cutover). Deterministic; all rates from `estimation_config.json ["extras"]`, nothing
fetched. `monthly_infra_cost` (compute + storage) drives the dual-run line.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | Powered-off servers excluded from every per-server line | unit test |
| C2 | Backup = protected-data·factor·$/GB + instances·$/instance | unit test |
| C3 | Egress applies the internet fraction and the free tier | unit test |
| C4 | Monitoring = LA ingestion + Defender; Defender toggle works | unit test |
| C5 | Support is the configured flat plan rate (0 for `none`) | unit test |
| C6 | Tooling one-time = 0 while avg migration months < free window; > 0 after | unit test |
| C7 | Dual-run one-time scales linearly with `monthly_infra_cost` | unit test |
| C8 | `total_monthly` reconciles; `first_year_extras = run_rate·12 + one_time` | unit test |
| C9 | Deterministic over the full sample `servers.csv` | unit test |

**Design.** `cost/run_rate.py` — one pure function, no network. `cost/functions.py` —
`POST /api/estimate_run_rate_extras`. New `extras` block in `config.py` DEFAULTS +
`estimation_config.json`. OpenAPI spec + agent tool #6 + prompt line.

**Deferred.** ExpressRoute/VPN and landing-zone fixed services stay separate proposal
lines (E3 / commercial). Commitment-tier LA discounts are a config edit, not modelled.

### Do

- `src/api/cost/run_rate.py` — new. `functions.py` — 4th route. `config.py` — `extras`
  block. `__init__.py` exports `estimate_run_rate_extras`.
- `src/api/openapi/estimate_run_rate_extras.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 6) + `SYSTEM_PROMPT` run-rate line.
- `tests/test_run_rate.py` — 9 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **58 passed**. C1–C9 pass (see test names).

Full sample estate (233 powered-on servers), Sweden Central, infra bill $102.9k/mo:
```
backup          $  4,163 /mo   (vault storage + 233 protected instances)
internet egress $    491 /mo   (30% of 33 TB net_out, less 100 GB free, @ $0.05/GB)
monitoring      $ 11,534 /mo   (Log Analytics $8,039 @ 0.5 GB/server/day + Defender $3,495)
support         $    100 /mo   (Standard, flat)
RUN-RATE EXTRAS $ 16,287 /mo   ($195,445 /yr)

one-time: dual-run $77,170 (1.5 mo x 50% of infra) ; tooling $0 (within 180-day free window)
first-year extras  $272,615
```

### Act

- **E2.4 done.** Full Azure run-rate for the sample estate: compute+disk ~$86k +
  storage ~$16.5k + extras ~$16.3k ≈ **~$119k/mo (~$1.43M/yr)**, plus ~$77k one-time.
- **Watch:** monitoring is the largest extra and the most assumption-sensitive
  (LA GB/server/day). Default is deliberately conservative (0.5 GB — syslog + counters,
  not verbose VM insights); a real engagement sets it from the client's logging policy.
- **E2.1–E2.4 done** — right-size, compute BoM, storage BoM, run-rate extras. Every
  result already carries a low/expected/high range; **E2.5** (an explicit top-3
  cost-driver / sensitivity block on each result) is still open, small, and can fold
  into the E5 deliverable cycle. **Next — Cycle 7:** E3.1/E3.2 — `design_landing_zone`
  (ALZ topology, spoke count, regulated-spoke flag from the portfolio + compliance
  scope), using the `azure-enterprise-infra-planner` skill.

---

## Cycle 5 — estimate_storage_cost (file / DB / object BoM)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.3 (done) ·
**Closes audit** FIN-3 remainder (compute BoM landed in Cycle 4; storage was deferred).

### Plan

**Objective.** Cost the `dbo.storage` table — file shares (Files Premium / NetApp),
managed/PaaS DB volumes (SQL MI, Hyperscale, PostgreSQL/MySQL Flexible, Oracle), object
(Blob). Line-item bill + by-type totals + low/expected/high, deterministic on injected
rates. **Disjoint** from `estimate_compute_cost`: that tool prices one managed disk per
VM (`type='block'`), so block volumes are excluded here and only reported — unless
`storage.price_block_from_storage_table` is set (then the caller suppresses disk in the
compute tool).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | `classify()` maps type + target_service → the right rate category | unit test |
| C2 | Block volumes excluded by default, counted in `excluded`; switch includes them | unit test |
| C3 | Files-premium / ANF min-provision floor billed even when the share is smaller | unit test |
| C4 | DB lines get the growth-headroom % and carry the "storage only" caveat | unit test |
| C5 | Injected rate overrides the config rate; `range.low ≤ expected ≤ high`; totals reconcile | unit test |
| C6 | Missing / zero size flagged in `not_costed`, never fatal | unit test |
| C7 | Deterministic over the full sample `storage.csv` | unit test |
| C8 | Live retail rates parse and are sanity-clamped to the config baseline | live fetch spot-check |

**Design.** `cost/storage_cost.py` — pure rate math on a `{category: usd_gb_month}`
book. `cost/pricing.py` gains `fetch_storagebook(region)` (best-effort per-service
queries, `_cheapest_stored` after a backup/redundancy exclude list, `_sane()` clamp to
0.4×–2.5× of the documented baseline so a mis-matched meter can't silently replace a
defensible rate). `cost/functions.py` — `POST /api/estimate_storage_cost` (6 h rate
cache). New `storage` block in `config.py` DEFAULTS + `estimation_config.json`. New
OpenAPI spec + agent tool #5 + prompt line.

**Deferred.** E2.4 — run-rate extras (backup, egress, monitoring, support) + one-time
migration cost. Object-tier lifecycle rules. Per-DB compute sizing (that's a replatform
concern, E4).

### Do

- `src/api/cost/storage_cost.py` — new. `pricing.py` — `fetch_storagebook` + helpers.
  `functions.py` — 3rd route + `_storage_rates` cache. `config.py` — `storage` block.
  `__init__.py` exports `estimate_storage_cost`, `classify`.
- `src/api/openapi/estimate_storage_cost.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 5) + `SYSTEM_PROMPT` storage line.
- `tests/test_storage_cost.py` — 10 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md` updated.

### Check

`pytest tests -q` → **49 passed**. C1–C7 pass (see test names).

C8 — live fetch (`swedencentral`, price_date `2026-09-01`): kept
`anf_standard 0.147`, `anf_premium 0.294`, `db_sql_mi 0.137` (GP LRS),
`db_sql_hyperscale 0.119`, `db_flex_postgresql 0.115`, `blob_hot 0.017`. Rejected by the
sanity clamp and fell back to config: `files_premium` (live 0.06 vs baseline 0.164 — a
Provisioned-v2 PAYG meter), `anf_ultra` (no match), `db_oracle` (no public meter).

Full sample estate (566 storage rows), Sweden Central:
```
file shares (5, 30 TB)     $  8,235 /mo
PaaS-DB volumes (39, 53 TB) $  8,301 /mo   (storage only — DB compute is a replatform line)
object                     $      0 /mo
TOTAL                       $ 16,536 /mo   ($198,430 /yr)
range                       $ 12,402 .. $ 20,670 /mo
excluded: 522 block volumes (~161 TB) — in the compute BoM's per-VM managed disk
```

### Act

- **E2.3 done.** Compute + storage now give a full infra run-rate: ~$86k/mo compute +
  disk, ~$16.5k/mo file/DB/object → **~$103k/mo (~$1.24M/yr)** for the sample estate,
  before dev/test pricing and E2.4 extras.
- **Watch:** the live storage-rate fetcher is heuristic (meter names vary by
  service). The `_sane()` clamp is the safety net; anything it rejects uses the
  documented `estimation_config.json` rate. Oracle DB@Azure has no retail meter — config
  rate only.
- **Next — Cycle 6:** E2.4 (`estimate_run_rate_extras` — backup GB, egress from
  `net_out_gb_30d`, monitoring, support tier + one-time migration/egress cost), then E3
  landing-zone deliverable (`azure-enterprise-infra-planner`).

---

## Cycle 4 — estimate_compute_cost (compute BoM)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.2 (done), E6.1 (advances) ·
**Closes audit** FIN-3 (nothing aggregated the SKU mix into a costed bill).

### Plan

**Objective.** Turn the right-size output into a monthly Azure compute cost — a
line-item bill of materials with PAYG / reserved / AHB, per-environment scaling, and a
low/expected/high range — deterministic for a given price date.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | AHB prices a Windows server at the Linux (no-licence) rate; flagged per line | unit test (injected prices) |
| C2 | Reserved blend = coverage·RI + (1−coverage)·PAYG at the configured term | unit test |
| C3 | Per-environment factor scales dr / non-prod compute | unit test |
| C4 | A SKU with no price is flagged in `missing_prices`, never fatal; line falls back to disk-only | unit test |
| C5 | `range.low ≤ expected ≤ high`; totals reconcile; `annual == monthly·12` | unit test |
| C6 | Deterministic | unit test |
| C7 | Real retail prices parse correctly (RI = amortised term total, Windows vs Linux) | live fetch spot-check |

**Design.** `cost/compute_cost.py` — pure math on an injected **PriceBook**
(`{sku: {linux|windows: {payg, ri1y, ri3y}}}`) + **DiskBook** (`{tier: monthly}`).
`cost/pricing.py` — builds those from prices.azure.com (VM + Premium SSD meters, chunked
OData, paging). `cost/functions.py` — `POST /api/estimate_compute_cost` (right-size →
collect SKUs → fetch prices, 6 h cache → cost). New OpenAPI spec + agent tool + prompt
("pass env + os_name too; never cost servers yourself"). Config `uplift` block reworked
to `nonprod_of_prod_pct` / `dr_of_prod_pct` / `dev_test_discount_pct`.

**Deferred.** Storage-table cost (file shares / DB / object) = E2.3. Run-rate extras
(backup, egress, monitoring, support) + one-time migration cost = E2.4. `ESTIMATION_CONFIG`
now supports an inline-JSON app setting; a package-baked default file is still TODO.

### Do

- `src/api/cost/{compute_cost,pricing}.py` — new. `functions.py` — 2nd route + price cache.
  `__init__.py` exports. `config.py` — `uplift` rework + inline-JSON `ESTIMATION_CONFIG`.
- `src/api/openapi/estimate_compute_cost.json` — new. `scripts/create_agent.py` — tool +
  prompt.
- `tests/test_compute_cost.py` — 8 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md` updated.

### Check

`pytest tests -q` → **40 passed**. C1–C6 pass (see test names).

C7 — live fetch (`swedencentral`, price_date `2026-06-01`):
`Standard_D4s_v5` linux `{payg 0.204, ri1y 0.12591, ri3y 0.08059}`, windows payg `0.388`
(the ~$0.184/hr delta is the Windows licence). First fetch returned RI as a **term lump
sum** (1103.0 / 2118.0) — fixed: reservations are always amortised `price/(years·8760)`.

Full 250-server estate, 1yr RI @ 80%, AHB on Windows:
```
compute PAYG        $ 81,106 /mo
compute RI          $ 50,315 /mo
compute effective   $ 56,473 /mo
managed disk        $ 29,884 /mo
TOTAL               $ 86,358 /mo   ($1,036,292 /yr)
range               $ 69,915 .. $138,840 /mo
missing_prices []   by_env prod 173 / nonprod 47 / dr 3 / dev 27
```
All 250 SKUs priced. Higher than `effort-inputs.md`'s old hand estimate (~$28–38k/mo) —
that assumed a 40% right-sizing cut and omitted managed-disk cost; the doc note is
updated. Every line is now traceable and ranged.

### Act

- E2.2 → `in-review` (unit + live-fetch verified; end-to-end via the agent with E1.6).
- **Next — Cycle 5:** E2.3 `estimate_storage_cost` over the `storage` table (file shares
  → Files/ANF, DB volumes → PaaS tiers, object), keeping it disjoint from the per-VM
  managed disk in `estimate_compute_cost`.

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
