# Learning path — Landfall as a working reference (E13.12)

Landfall was built to deliver real pre-sales estimates *and* to be a hands-on
reference for three things the sponsor wanted to learn by doing:

1. **Azure AI Foundry** — a low-code prompt agent orchestrating deterministic tools
2. **Azure Container Apps** — scale-to-zero containers, KEDA, Jobs, Easy Auth
3. **Enterprise-scale design** — multi-tenancy, evidence, guardrails, cost control

This page maps each goal to the files and PRD sections where it actually lives, so
you can read the code rather than a tutorial. Everything referenced is in this
repository. PRD section numbers refer to
[`prd/engagement-workspaces-prd.md`](../prd/engagement-workspaces-prd.md).

---

## 1 · Azure AI Foundry — an agent that orchestrates, never calculates

**The pattern.** A single Foundry **prompt agent** (`landfall-migration-estimator`)
holds only instructions and a list of OpenAPI tools. Every number it reports comes
from a deterministic Python tool — the model chooses *which* tool and *when*, never
*what the answer is*. See PRD §3.1 ("deterministic tools under an agent") and §13
("same input → same estimate").

| What to read | Where | Why |
|---|---|---|
| Agent definition — name, system prompt, tool registration | `scripts/create_agent.py` (`AGENT_NAME`, `SYSTEM_PROMPT`, `main()`) | The whole agent is ~200 lines; the prompt is the product's guardrail (no fabricated numbers, always cite a tool, DRAFT boundary). |
| Name-addressed invocation via the Responses API | `src/web/app.py` → `chat()` (`agent_reference` by name, `previous_response_id` chaining) | How a stateless web tier talks to a stored-conversation agent. |
| The deterministic tools the agent calls | `src/api/tools.py`, `src/api/deliverable/assemble.py`, everything under `src/api/` | Text-to-SQL is `query_inventory`; the rest are pure functions over inventory + config. |
| The OpenAPI contracts (one file per tool) | `src/api/openapi/` (17 specs — `query_inventory.json`, `estimate_compute_cost.json`, `publish_estimate.json`, …) | Foundry registers tools from these; the `engagement` arg is required on every one. |
| Offline evaluation harness | `evals/runner.py` (golden SQL + scenario bands + fault injection + adversarial) | Runs the full pipeline with synthetic price books; gates CI. `python evals/runner.py`. |
| Adversarial guardrail suite | `evals/adversarial.py` (SQL-guard, engagement isolation, path traversal, malicious upload, output guard, system-prompt) | 74 cases; a regression fails the build. |
| Output guard — catches an un-sourced number | `evals/output_guard.py` (`check_message`) | Any money / % / FTE / large figure in prose must trace to a tool value or a citation. |

**Takeaway:** the LLM is a router and a writer. Correctness lives in Python and is
proven offline before any model sees it.

---

## 2 · Azure Container Apps — scale-to-zero, KEDA, Jobs, Easy Auth

All compute except the Function App runs as Container Apps in one managed
environment. Infra is in [`infra/resources.bicep`](../infra/resources.bicep);
parameters thread through [`infra/main.bicep`](../infra/main.bicep) and
`infra/main.parameters.json`.

| Concept | Where | Notes |
|---|---|---|
| Managed environment + the app definitions | `infra/resources.bicep` (`containerEnv`, `containerApp` = web, `calcApp`, `drawioApp`) | One environment, three workloads, one user-assigned managed identity (`uami`). |
| Scale to zero | `containerApp` / `drawioApp` `scale.minReplicas: isProd ? 1 : 0` | The web tier costs nothing when idle on the free tier; first request pays a cold start. |
| The queue-decouple pattern | PRD §4.6 + decision 10; `src/api/lz/functions.py` (`stage_calc_run`) → `src/calc/worker.py` | The Function returns **202** and drops a `calc-jobs` queue message; the calculator drive (minutes of Playwright) runs out-of-band, well past the Functions HTTP limit. |
| Container Apps **Jobs** (event-driven, `minExecutions: 0`) | `infra/resources.bicep` (`calcJob`, `if (useCalcJob)`); entrypoint `src/calc/job.py` → `src/calc/worker.py` `run_once()` | E13.13. A KEDA `azure-queue` rule with **managed-identity auth** starts one execution per batch of messages, drains the queue, and exits — no always-on replica. Ships dormant (`USE_CALC_JOB=false`); `azd env set USE_CALC_JOB true` activates it. |
| KEDA queue trigger with managed identity | `calcJob` `eventTriggerConfig.scale.rules[].identity: uami.id` | The storage account has `allowSharedKeyAccess: false`, so the scaler must authenticate as the identity — no connection string. |
| Easy Auth (platform-level auth, no app code) | `infra/resources.bicep` (`webAuthConfig` for the web app, `functionAuth` = `authsettingsV2` for the Function); recipe in [`DEPLOY.md`](../DEPLOY.md) | `requireAuthentication` + `Return401`; the Function's `excludedPaths` must list the blob + durabletask webhook paths literally or Event Grid breaks. |
| Cold-start budget check | `scripts/smoke.py --cold` | Times the first hit to each front door and fails past a budget. |
| Nicer hostname for $0 (planned) | PRD §5a / E12.11 — rename the app, free community subdomain, free ACA managed cert | Not yet implemented; documented as the $0 path (no Front Door, no paid domain). |

**Takeaway:** the always-on cost of this stack is essentially one light Function
App and a serverless SQL database. Containers are present only while working.

---

## 3 · Enterprise-scale design — multi-tenancy, evidence, guardrails

| Concept | Where | Notes |
|---|---|---|
| Per-engagement isolation (one deployment, many customers) | `src/api/engagement.py` (identity + ADLS prefixes), `src/api/engagement_sql.py` (`set_engagement`) | Key is `<customer>/<project>`; blobs at `raw\|answers/engagements/<c>/<p>/…`. |
| Row-Level Security, fail-closed | `scripts/schema.sql` (`fn_engagement_predicate` TVF + `EngagementFilter` `SECURITY POLICY`, `STATE = ON`) | No `SESSION_CONTEXT('engagement_id')` set → **zero rows**. `set_engagement` binds it read-only (`sp_set_session_context … @read_only = 1`) before any SELECT. See PRD §7.1. |
| SQL injection surface reduced to a guarded allow-list | `src/api/sqlguard.py` (`safe_select`) | Single SELECT/WITH, 6-table allow-list, forbidden-keyword regex, balanced parens, 4000-char cap. `signature()` logs a fingerprint with no SQL text. |
| ADLS is the system of record; SQL is a projection | PRD §4.2, §4.5a, decision 14 | Inventory lands as blobs first; the ingest pipeline (`src/api/ingest/`) projects it into SQL. A teardown can rebuild SQL from the blobs. |
| Evidence-based scoring + PDCA | `evidence/scorecard.py` (`rubric`, 9 dimensions), `prd/pdca-log.md`, `prd/tracker.md` | Every cycle: pick a lever → plan/do/check/act → regenerate the scorecard → no drift. |
| Adversarial + fault evals gate CI | `evals/adversarial.py`, `evals/faults.py`, `.github/workflows/evals.yml` | A guardrail change without a matching adversarial case fails the build. |
| End-of-cycle quality gate | `.claude/agents/landfall-judge.md` | A read-only reviewer agent: tests + evals + scorecard drift + correct `azd deploy` target + never `azd provision` + bookkeeping. |
| Param-gated deployment tiers | `infra/main.bicep` (`deploymentTier`, default `free`); PRD E9.3 | `free` = Free-tier SKUs, auto-pause, no SLA (~$5–15/mo). `prod` = paid SLAs (~$350–450/mo). One switch. |
| Cost guardrails | `infra/*.bicep` (`Microsoft.Consumption/budgets`, 50/80/100 % alerts), `scripts/spend.py` | Budget amount is in the **subscription billing currency** (INR here), not USD. `spend.py` reports MTD actual vs budget + burn projection. |
| Ephemeral operating model | `scripts/teardown.sh` / `scripts/rehydrate.sh`, `scripts/export_all.py` | `azd up` on demand → work → `scripts/teardown.sh` exports every engagement, verifies the export, then `azd down --purge`. `rehydrate.sh` refuses to run against a live RG. |
| Browser-automation validation of every UI change | `tests/browser/` (`serve.py` offline app, `test_chat_page.py`); PRD §4.17 | Playwright against a local app with offline stubs; 0 console errors is an assertion. |
| Answer-quality observability | [`docs/observability.md`](observability.md), `infra/workbook-answer-quality.json` | Per-tool latency/error rate + structured traces; `engagement` is always a SHA-256 prefix, never the raw customer name. |

**Takeaway:** the security and cost story is defence-in-depth with no expensive
parts — RLS + a SQL guard + Entra-only auth instead of private endpoints
(descoped on cost, PRD §4.14 note), Free-tier SKUs, and a budget alert.

---

## Deployment profiles — lab → customer → enterprise

`DEPLOYMENT_TIER` (`free` / `prod`) is the one switch in code today. The table
below is the intended progression; only **lab** is exercised.

| Aspect | Lab (today) | Customer engagement | Enterprise |
|---|---|---|---|
| **Tier** | `DEPLOYMENT_TIER=free` — Free-offer SQL, free AI Search, serverless auto-pause | `free` still fine for a single engagement; `prod` if an SLA / no cold start is needed | `prod` — paid SKUs, SLAs |
| **Tenancy** | Many engagements in one deployment, isolated by RLS | Same, or a dedicated deployment per client if contractually required | Dedicated deployment or dedicated DB per client (`--tier regulated`, PRD §7) |
| **Auth** | Easy Auth on web + Function; single Entra tenant | Same; restrict `functionAuthAllowedClientIds` to the Foundry MSI | Same + conditional access; per-client app registrations |
| **Network** | Public SQL + storage; RLS + SQL guard + Entra-only auth is the data-plane control | Same (private endpoints descoped on cost — PRD §4.14) | Private endpoints + VNet if the client mandates it (re-scoped, budget permitting) |
| **Cost** | ~$5–15/mo, ephemeral (`azd down --purge` between sessions) | Same; keep it up for the engagement window | Steady-state paid; budget alert amount raised |
| **Data lifecycle** | `scripts/teardown.sh` exports every engagement before `azd down` | Export + hand off the `.zip` per engagement at close | Retention policy + scheduled export |

---

## Suggested reading order

1. [`docs/how-landfall-works.html`](how-landfall-works.html) — the pipeline and the answer contract, with a worked example.
2. `scripts/create_agent.py` — the whole agent, top to bottom.
3. `src/api/tools.py` + one estimator under `src/api/cost/` — a deterministic tool.
4. `evals/runner.py` then `evals/adversarial.py` — how correctness and safety are proven offline.
5. `infra/resources.bicep` — the three containers, the Job, Easy Auth, the managed identity.
6. `scripts/schema.sql` — the RLS policy.
7. `prd/pdca-log.md` (newest first) — how the work was actually sequenced.
