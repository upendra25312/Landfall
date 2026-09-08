# Landfall

Low-code Azure agentic solution that reads a client's **on-premises server and application
inventory** from Azure Data Lake and drafts the **landing-zone and migration numbers** needed
for an RFP proposal — with **no discovery tooling installed on the client estate**.

Built to run under **$30/month**, for **bursty use** (5–20 estimate runs per month).

> Output is a **draft estimate for a human architect to review and own** — not a bid.
> Client-supplied inventory is typically incomplete and lacks performance data; every answer
> the agent gives carries stated assumptions and a confidence level.

---

## How it works

```
Client inventory exports ──► ADLS Gen2 ──► Normalize (Event Grid ingest) ──► Azure SQL (Free)
   (RVTools, CMDB, app portfolio, docs)   raw/inventory/  │  detect → map → load    servers / applications
                                                 │        └─► data-quality report ──► answers/_ingest/
                                                 └─► AI Search (Free)  ◄─ narrative docs
                                                          │
                        Azure AI Foundry Agent ("Migration Estimator")
                        tools: query_inventory · vm_rightsize · azure_retail_prices
                               · search_documents · microsoft_docs (Learn MCP)
                                                          │
                           ┌──────────────────────────────┴───────────────────────┐
                    Chat UI (Azure Container Apps)              RFP question sheet (Durable Functions)
                    min replicas 0, Entra ID auth              questions.xlsx ──► answers.xlsx + email
```

## Stack (all free / near-free tiers)

| Area | Choice |
|---|---|
| File store | ADLS Gen2 (hierarchical namespace) |
| Structured store | Azure SQL Database — Free offer (serverless, auto-pause) |
| Retrieval index | Azure AI Search — Free (narrative docs only, 512-dim vectors) |
| Models | `gpt-4o` + `text-embedding-3-small` |
| Agent host | Microsoft Foundry — prompt agent, driven through the Responses API |
| Agent tools | AI Search · Azure SQL text-to-SQL · Azure Retail Prices API · deterministic VM right-sizer · Microsoft Learn MCP |
| Chat UI | Azure Container Apps (scale-to-zero) |
| Batch runner | Azure Durable Functions (Consumption) |

Typical cost: **$5–15/month**, almost entirely Azure OpenAI tokens for the runs you actually do.

## Deploy

```bash
azd auth login && az login
azd env new landfall
azd env set AZURE_LOCATION eastus2
azd up
```

`azd up` provisions everything in `infra/`, runs `scripts/postprovision.*` (loads the SQL
schema, builds the AI Search index, creates the Foundry agent), deploys `src/api` and
`src/web`, then runs `scripts/eventgrid.*` to subscribe the batch runner to `questions/`
blob events.

- **[INSTALL.md](INSTALL.md)** — full walkthrough from a clean machine: every prerequisite,
  tool install commands per OS, Azure account setup, deploy, verify, troubleshoot, tear down.
- **[DEPLOY.md](DEPLOY.md)** — the short version for when the tooling is already in place.

## Repository layout

| Path | What |
|---|---|
| `azure.yaml` | azd template — services `api` (Function) and `web` (Container App) |
| `infra/main.bicep`, `infra/resources.bicep` | all Azure resources + data-plane role assignments |
| `scripts/postprovision.*` | post-provision hook (SQL schema, search index, agent creation) |
| `scripts/eventgrid.*` | post-deploy hook — wires `questions/` blobs to the batch runner via an Event Grid subscription (Flex Consumption needs this) |
| `scripts/schema.sql` | inventory tables — `servers`, `applications`, `dependencies`, `storage` |
| `scripts/setup_search.py` | builds the AI Search data source / skillset / index / indexer (512-dim) |
| `scripts/create_agent.py` | creates the **Migration Estimator** agent — Learn MCP + AI Search + the three OpenAPI tools |
| `scripts/grant_api_sql.sql` | read-only (`db_datareader`) SQL user for the workload identity (`query_inventory`) |
| `src/api/function_app.py` | Durable Functions RFP-question-sheet batch runner (fan-out / fan-in) |
| `src/api/ingest/` | inventory ingestion — `raw/inventory/*` → detect source (RVTools / CMDB / native) → map to the schema → load Azure SQL → data-quality report in `answers/_ingest/` |
| `src/api/tools.py` | agent HTTP tools — `query_inventory` (text-to-SQL), `azure_retail_prices` |
| `src/api/cost/` | deterministic cost engine — `vm_rightsize`, `estimate_compute_cost`, `estimate_storage_cost`, `estimate_run_rate_extras`, SKU catalogue, `estimation_config.json` loader |
| `src/api/lz/` | `design_landing_zone` — CAF Azure Landing Zone (MGs, subs, hub-spoke + IP plan, policy, identity, DR) derived from the app portfolio + compliance scope |
| `src/api/waves/` | `score_dispositions` (rule-derived 6R + rationale) and `plan_waves` (dependency graph → affinity move-groups → risk-ordered waves) |
| `src/api/deliverable/` | `assemble_estimate` — every tool's output → one package (8 sections, calculation appendix + stable figure IDs, assumptions/exclusions register, parametric effort + services cost, markdown render); `export_estimate` — the package as an Excel workbook, Word document, or PowerPoint deck |
| `estimation_config.json` | your firm's estimation inputs — pricing, right-sizing, storage/extras rates, `landing_zone`, `disposition`, `waves`, `effort` bands, `deliverable` sections |
| `src/api/openapi/` | OpenAPI 3.0 specs for those tools; `create_agent.py` points them at the deployed Function app |
| `src/web/` | FastAPI chat UI container |
| `samples/smoke-questions.xlsx` | two-question sheet for a first end-to-end test of the batch runner |
| `docs/operating-sop.html` | **how to use a deployed Landfall** — step-by-step SOP from data load to architect hand-off |
| `docs/build-spec.html` | solution build specification |
| `docs/effort-and-resource-loading.html` | pre-sales parametric effort model + 6-month resource loading |
| `docs/discovery-questionnaire.html` | client questionnaire + assumptions register (AS-01…14) + risk register (RK-01…12) |
| `prompts/production-readiness-audit.md` | reusable expert-panel audit prompt — "toy → production" review against the pre-sales scenario |
| `audits/` | recorded runs of that audit — observations, prioritized backlog, rubric scores, the path to 5/5 |
| `prd/` | the "Landfall to 5/5" PRD, work tracker, and PDCA delivery log |
| `tests/` | unit tests (`pytest`) — ingestion, cost engine, landing zone, wave engine, deliverable |
| `evals/` | offline eval harness (`python evals/runner.py`) — 32 golden text-to-SQL cases + 8 full-estimate scenarios + fault injection + output guard + `SCORECARD.md` |
| `.github/workflows/evals.yml` | CI — runs `pytest` + the eval harness on every push / PR; a stale `SCORECARD.md` or any regression fails the build |

Read them online at **[upendra25312.github.io/Landfall](https://upendra25312.github.io/Landfall/)**
(GitHub Pages, served from `docs/`), or open the `docs/*.html` files locally — each is a
self-contained, theme-aware page.

## Before you run a real estimate

Edit **[`estimation_config.json`](estimation_config.json)** with your firm's numbers — the
estimation tools apply these rather than inventing rates. Anything you omit falls back to
the documented defaults in `src/api/cost/config.py`. Consumed by `vm_rightsize` (target
utilisation, retain floors), `estimate_compute_cost` / `estimate_storage_cost` /
`estimate_run_rate_extras` (pricing, reserved term, storage rates, backup / egress /
monitoring), `design_landing_zone` (region, IP supernet, connectivity, identity model,
regulated compliance scopes, criticality→RPO/RTO tiers), `score_dispositions` /
`plan_waves` (6R appetite, dependency-confidence and staleness filters, per-wave caps),
and `assemble_estimate` (effort bands, contingency-by-confidence, the deliverable's
section list).

- right-sizing targets and retain floors, how to treat servers with no perf data
- pricing: region, reserved-instance term, Azure Hybrid Benefit, dev/test pricing
- non-prod + DR compute uplift %
- S / M / L / XL effort bands, PM / governance overhead %, blended day rate

## Between engagements

Nothing runs continuously. `azd down --purge` deletes everything and takes run cost to
zero; `azd up` rebuilds in ~15 minutes. Or leave it idle — storage + Log Analytics is a
couple of dollars a month.
