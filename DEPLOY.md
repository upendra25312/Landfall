# Deploying Landfall with `azd`

> For a clean machine — every prerequisite, per-OS install commands, Azure account
> setup, verification and teardown — use **[INSTALL.md](INSTALL.md)**. This file is the
> condensed version.

The whole solution provisions from one template with the **Azure Developer CLI**.

```
azd auth login
azd env new landfall
azd up
```

`azd up` = `azd provision` (Bicep in `infra/`) → `postprovision` hook → `azd deploy`
(pushes `src/api` and `src/web`) → `postdeploy` hook (two Event Grid subscriptions:
`landfall-questions` for the batch runner, `landfall-inventory` for the ingestion pipeline).

---

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| [Azure Developer CLI](https://aka.ms/azd) ≥ 1.11 | orchestrates everything | `winget install microsoft.azd` / `brew install azd` |
| [Azure CLI](https://aka.ms/azcli) | used by the postprovision hook | `winget install -e --id Microsoft.AzureCLI` |
| Python 3.11 + pip | runs the helper scripts | — |
| ~~`sqlcmd`~~ | *no longer needed* — `scripts/apply_sql.py` loads the schema + grant in pure Python (Entra token) | — |
| Docker | `azd` builds the `web` container image | Docker Desktop |
| An Azure subscription where you can create resources **and assign roles** (Owner or User Access Administrator on the target scope) | the Bicep creates data-plane role assignments | — |

Quota: the deployment needs **30K TPM each** for `gpt-4o` and `text-embedding-3-small`
(both GlobalStandard) in your chosen region. Check
`az cognitiveservices usage list -l <region>` first; request an increase if needed, or
lower `MODEL_CAPACITY` (`azd env set MODEL_CAPACITY 10`).

---

## Step by step

```bash
# 1. sign in (both CLIs)
azd auth login
az login

# 2. create an environment
azd env new landfall
azd env set AZURE_LOCATION eastus2          # a region with the two models + SQL free offer

# 3. (optional) override model versions if the defaults are retired in your region
#    azd env set CHAT_MODEL_VERSION 2024-11-20
#    azd env set EMBEDDING_MODEL_VERSION 1

# 4. provision + deploy
azd up
```

What `azd up` does:

1. **provision** — creates the resource group `rg-landfall` and everything in
   `infra/resources.bicep`: ADLS Gen2, AI Search (Free), Foundry account + project +
   model deployments, Azure SQL (Free offer), Container Apps env + registry, the
   Function app (Flex Consumption), Key Vault, Log Analytics / App Insights, the shared
   managed identity, and all role assignments.
2. **postprovision** (`scripts/postprovision.*`) —
   - runs `scripts/apply_sql.py` — loads `scripts/schema.sql` and grants the workload
     identity `db_datareader` (for `query_inventory`), in pure Python with an Entra
     token; **no `sqlcmd`, no `azd`-on-PATH** needed (E9.1),
   - builds the AI Search data source / skillset / index / indexer (`setup_search.py`),
   - creates (versions) the **Migration Estimator** prompt agent (`create_agent.py`) with
     the Microsoft Learn MCP tool, the AI Search tool, and the OpenAPI tools
     (`query_inventory`, `vm_rightsize`, `estimate_compute_cost`,
     `estimate_storage_cost`, `estimate_run_rate_extras`, `design_landing_zone`,
     `score_dispositions`, `plan_waves`, `assemble_estimate`, `export_estimate`,
     `publish_estimate`, `azure_retail_prices`) pointed at the Function app. The
     agent is addressed by **name**
     (`landfall-migration-estimator`), not an `asst_` id; that name is written to
     `AGENT_ID` in the azd env and pushed to both running services.
3. **deploy** — zip-deploys `src/api` to the Function app and builds + pushes the
   `src/web` image to the registry, then updates the Container App.
4. **postdeploy** (`scripts/eventgrid.*`) — creates two Event Grid subscriptions:
   `landfall-questions` (blobs in `questions/` → the `start` batch-runner function) and
   `landfall-inventory` (blobs in `raw/inventory/` → the `ingest_blob` function). This runs
   after `deploy` because each subscription's webhook needs the function app's
   `blobs_extension` system key, which only exists once the function is published.
   Idempotent and `continueOnError` — re-run by hand with `azd hooks run postdeploy` if
   the function host was still warming up.

At the end `azd` prints the **`SERVICE_WEB_URI`** — the Container App. It serves two
pages: `/` (the chat UI) and `/dashboard` (the **assessment dashboard** — an Azure
Migrate–style read of the estimate, with Excel / Word / PowerPoint download buttons).
The dashboard is populated when the agent (or an operator) calls **`publish_estimate`**,
which writes the assembled package + the three exports to `answers/estimate/`.

---

## Manual follow-ups (not yet automated)

These need the portal or a couple of CLI calls once, after the first `azd up`:

1. **Lock down the chat UI** — Easy Auth on `ca-web`. **A fresh `azd up` leaves the
   web app open** (threat T5). One Entra app registration, then either
   `azd provision` (IaC) or `az` (imperative).

   ```bash
   RG=$(azd env get-value AZURE_RESOURCE_GROUP); WEB=$(azd env get-value SERVICE_WEB_NAME)
   FQDN=$(az containerapp show -g "$RG" -n "$WEB" --query properties.configuration.ingress.fqdn -o tsv)
   APPID=$(az ad app create --display-name "landfall-web ($WEB)" --sign-in-audience AzureADMyOrg \
     --web-redirect-uris "https://$FQDN/.auth/login/aad/callback" --enable-id-token-issuance true \
     --query appId -o tsv)
   az ad sp create --id "$APPID"
   SECRET=$(az ad app credential reset --id "$APPID" --years 2 --query password -o tsv)
   ```

   **IaC (preferred — survives a re-provision):**
   ```bash
   azd env set WEB_AUTH_CLIENT_ID "$APPID"
   azd env set --secret WEB_AUTH_CLIENT_SECRET   # paste $SECRET when prompted
   azd provision                                  # comment out the postprovision hook first (schema.sql drops tables)
   ```
   With `WEB_AUTH_CLIENT_ID` set, `infra/resources.bicep` deploys the
   `authConfigs` (`RedirectToLoginPage`, tenant-restricted audience). Empty = no
   Bicep-managed web auth.

   **Imperative (if you can't re-provision):**
   ```bash
   TENANT=$(az account show --query tenantId -o tsv)
   az containerapp secret set -g "$RG" -n "$WEB" --secrets "microsoft-provider-authentication-secret=$SECRET"
   az containerapp auth microsoft update -g "$RG" -n "$WEB" --client-id "$APPID" \
     --client-secret-name microsoft-provider-authentication-secret \
     --issuer "https://login.microsoftonline.com/$TENANT/v2.0" --yes
   az containerapp auth update -g "$RG" -n "$WEB" --enabled true --action RedirectToLoginPage \
     --redirect-provider azureactivedirectory --require-https true
   ```
   `--sign-in-audience AzureADMyOrg` restricts sign-in to your tenant. Unauthenticated
   requests then get a 302 to Microsoft login (browsers) or 401 (API clients).

2. **Foundry connection for AI Search.** If `create_agent.py` warned that no connection
   was found: Foundry portal → *Management center* → *Connected resources* → add your
   search service, then re-run `python scripts/create_agent.py` (env still loaded via
   `azd env get-values`). This publishes a new agent version; the services reference the
   agent by name, so they pick it up with no redeploy.

3. **Harden the Function App** *(strongly recommended)*. The OpenAPI tools ship as
   **anonymous** HTTP functions so the first deploy works. Even the low-risk tools
   (`vm_rightsize`, `estimate_compute_cost`, …, `azure_retail_prices`) take their inputs
   in the request body and hold no client data; `query_inventory` returns inventory rows
   — its SQL is a single `SELECT`/`WITH` against the six inventory tables only, no
   comments, no admin/timing keywords, 200-row cap, 20 s statement timeout
   (`src/api/sqlguard.py`, E8.3); the question and SQL text never reach the logs, only a
   hash + the table list (E8.4). EasyAuth is **app-global** (it can't protect one route
   and not another), so turning it on moves *every* tool call behind an Entra token and
   the agent must use its managed identity for all of them:
   ```bash
   # 1. an app registration whose token audience the Function App will accept
   APPID=$(az ad app create --display-name "landfall-$(azd env get-value SERVICE_API_NAME)" \
     --sign-in-audience AzureADMyOrg --query appId -o tsv)
   az ad app update --id "$APPID" --identifier-uris "api://$APPID"
   az ad sp create --id "$APPID"

   # 2. turn EasyAuth on through the template and re-provision
   azd env set ENABLE_FUNCTION_AUTH true
   azd env set FUNCTION_AUTH_CLIENT_ID "$APPID"
   azd env set FUNC_AUTH_AUDIENCE  "api://$APPID"
   azd env set AGENT_TOOL_AUTH     managed
   azd provision      # applies authsettingsV2; postprovision re-runs create_agent.py
                      # so all 12 OpenAPI tools switch to managed-identity auth
   ```
   `excludedPaths: ["/runtime/webhooks/blobs", "/runtime/webhooks/durabletask"]` keeps
   the Event Grid blob webhook (ingestion + the durable `start` function) and the
   durable-task APIs reachable — note EasyAuth matches `excludedPaths` as literal
   prefixes, so `/runtime` alone does **not** cover `/runtime/webhooks/blobs`.
   **Verify:** an anonymous `curl` to any `/api/*` route returns `401`; the agent still
   answers (it calls the tools with its MSI token). Optionally tighten to just the
   Foundry identity by setting `functionAuthAllowedClientIds` (Bicep param) to the
   project's managed-identity client id.
   Roll back with `azd env set ENABLE_FUNCTION_AUTH false` (+ `AGENT_TOOL_AUTH` unset)
   then `azd provision`.

4. **Load client data.**
   - **Inventory** → drop the client's exports (RVTools workbook, CMDB extract,
     application portfolio, dependency/flow list, performance export) into
     `raw/inventory/`. The `ingest_blob` function detects the format, maps columns to
     `scripts/schema.sql`, normalises units, and loads Azure SQL. A data-quality report
     lands in `answers/_ingest/<file>.dq.md` — an overall confidence plus a
     "what's missing to firm up the estimate" list to send back to the client.
     Re-uploading a corrected file replaces only its rows.
   - **Narrative docs** → `raw/docs/` (the AI Search indexer picks them up on its 6-hour
     schedule, or run it now).
   ```bash
   ACC=$(azd env get-value AZURE_STORAGE_ACCOUNT)
   az storage blob upload-batch --account-name "$ACC" --auth-mode login \
     -d raw/inventory -s ./client-inventory --pattern "*.csv"
   az storage blob upload-batch --account-name "$ACC" --auth-mode login \
     -d raw/docs -s ./client-docs
   ```
   **To demo without client data**, `sample-estate/` has a synthetic 250-server / 31-app
   estate with 30-day performance data, plus a completed discovery questionnaire and
   effort model:
   ```bash
   ACC=$(azd env get-value AZURE_STORAGE_ACCOUNT)
   az storage blob upload-batch --account-name "$ACC" --auth-mode login \
     -d raw/inventory -s sample-estate --pattern "*.csv"     # -> ingestion pipeline
   az storage blob upload-batch --account-name "$ACC" --auth-mode login \
     -d raw/docs -s sample-estate --pattern "*.md"
   # or, no deploy needed, load SQL directly:
   python sample-estate/load_estate.py
   ```

5. **Estimation config (optional).** The estimation tools (`vm_rightsize`,
   `estimate_compute_cost`, `estimate_storage_cost`, `estimate_run_rate_extras`,
   `design_landing_zone`, `score_dispositions`, `plan_waves`) apply
   `estimation_config.json` (`storage` = file / DB / object $/GB-month rates + the
   `price_block_from_storage_table` switch; `extras` = backup / egress / monitoring
   / support run-rate and the one-time migration knobs; `landing_zone` = region, IP
   supernet, connectivity, identity model, regulated compliance scopes and the
   criticality→RPO/RTO tiers; `disposition` = 6R appetite and the marker lists;
   `waves` = confidence / staleness filters, per-wave caps, commodity protocols;
   `effort` = person-day bands and the contingency-by-confidence table; `deliverable`
   = the 8 section keys, watermark and cost-driver count). The deployed Function uses the
   built-in defaults (`src/api/cost/config.py`) unless you set an **`ESTIMATION_CONFIG`**
   app setting — a path inside the package, or the JSON inline:
   ```bash
   RG=$(azd env get-value AZURE_RESOURCE_GROUP); FUNC=$(azd env get-value SERVICE_API_NAME)
   az functionapp config appsettings set -g "$RG" -n "$FUNC" \
     --settings "ESTIMATION_CONFIG=$(python -c 'import json;print(json.dumps(json.load(open("estimation_config.json"))))')"
   ```
   Or pass per-run overrides in the tool call body (`{"config": {...}}`) — no redeploy.

6. **Budget alert.** Cost Management → Budgets → $25 with alerts at 50 / 80 / 100%.

---

## Everyday commands

```bash
azd deploy api          # redeploy just the Function app after a code change
azd deploy web          # rebuild + redeploy just the chat UI
azd provision           # re-apply infra changes
azd hooks run postprovision   # rebuild SQL schema / search index / agent
                              # NOTE: schema.sql DROPs and recreates the inventory tables

azd hooks run postdeploy      # re-create the Event Grid subscriptions (batch runner + ingestion)
azd env get-values      # see all endpoints / names
azd down --purge        # delete everything (including soft-deleted Key Vault / Foundry)
```

`azd down` between engagements takes the run cost to zero; `azd up` rebuilds in ~15 min.

**One deployment per engagement (E8.1).** Every resource name carries a `resourceToken`
derived from the subscription + `AZURE_ENV_NAME` + location, so a second `azd env new`
gets its own resource group, storage account, SQL database, Foundry project and Function
app — two engagements never share a datastore. Use a distinct env name per client
(`azd env new acme-migration`), and `azd down --purge` when the engagement closes (it
also removes the soft-deleted Key Vault and Foundry account so the names free up).

### Close-out — export before you tear down (E9.5)

`azd down --purge` is irreversible. **Before it**, retain every engagement:

```bash
python scripts/export_all.py --sql            # -> ./_closeout/<UTC>/<customer>__<project>.landfall.zip
#                                                each zip: raw/ inventory + docs, answers/ artifacts +
#                                                chat, sql/*.csv (the six tables, RLS-scoped), export.json
python scripts/export_all.py --dry-run        # preview: engagements + sizes, writes nothing
```

Each `.zip` re-imports into a fresh deployment via `POST /api/engagements/import`
(or the chat header's **↑ import**). `--sql` retries through a paused serverless
DB; a SQL hiccup never loses the blob export (`raw/` is the source of truth and
re-ingests on import). Needs a SQL reader login for `--sql` (the deploy identity
or an `az login` user with `db_datareader`); `STORAGE_URL` + `AZURE_SQL_*` come
from `azd env get-values`.

---

## Post-deploy smoke test (E9.2)

`scripts/smoke.py` asserts a deployment is actually serving — every expected
resource exists, the Function host and web container answer, SQL is reachable,
the blob containers are there. Stdlib only; `az` must be logged in.

```bash
python scripts/smoke.py                    # uses `azd env get-values`, then os.environ
python scripts/smoke.py --json smoke.json  # + structured result
python scripts/smoke.py --deep             # + agent-resolves, + live query_inventory (needs SMOKE_API_TOKEN)
```

Exit code is non-zero on the first hard failure. A captured run against
`rg-landfall` lives at `evidence/ops/smoke-live.json`.

### Clean-machine CI — `.github/workflows/clean-machine.yml`

Provisions a throwaway env from nothing on both Linux and Windows runners
(`azd up` → `smoke.py` → `azd down --force --purge`), so a Bicep or hook
regression fails in CI before it reaches the live environment. **Dormant until
armed** — it needs an Entra service principal with rights to create resources +
role assignments in a subscription, wired to GitHub via OIDC:

1. Create an app registration + service principal; give it **Contributor** and
   **Role Based Access Control Administrator** (or Owner) on the target
   subscription (the Bicep creates data-plane role assignments).
2. Add a **federated credential** on the app for
   `repo:<org>/<repo>:ref:refs/heads/main` (and `:environment:` /
   `:pull_request` if you extend the triggers).
3. Repository → Settings → Secrets and variables → Actions:
   - secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
     `AZURE_PRINCIPAL_ID` (the SP's **object id**, for the SQL admin + data-plane grants)
   - variable: `CLEAN_MACHINE_CI` = `true`  (the job's `if:` guard)
   - variable (optional): `CLEAN_MACHINE_LOCATION` (default `eastus2` — pick a
     region with **10K TPM** free for `gpt-4o` + embeddings; the CI env sets
     `MODEL_CAPACITY=10`)

Until step 3's variable is set the workflow is skipped on every trigger. Trigger
a manual run from the Actions tab once armed.

**Known drift the CI would surface:** the live `web` Container App has Easy Auth
enabled *imperatively* (not in `infra/resources.bicep`), so a fresh `azd up`
brings the web app up with **no auth**. `smoke.py` treats both 200 and 401 on
`/healthz` as "up", but the difference is real — fold the container-app
`authConfig` into Bicep (an E8.2 follow-up) so live and fresh match.

---

## Deployment tiers (`DEPLOYMENT_TIER`)

One switch moves the stack off the Free tiers. Default is `free`; set
`azd env set DEPLOYMENT_TIER prod` then `azd provision`.

| Resource | `free` (default) | `prod` | ~ monthly delta |
|---|---|---|---|
| Azure SQL DB | Free offer (100k vCore-sec/mo free → AutoPause), **1 h** auto-pause, 0.5-vCore floor, 32 GB | no free-limit cap, **24 h** auto-pause, 1-vCore floor, 100 GB | **+$95–210** (serverless GP_S billed while active; ends the "database is not currently available" wake-up on the first query after an hour idle) |
| AI Search | `free` (50 MB, shared, no SLA, no semantic ranker) | `basic`, 2 replicas (2 GB, **99.9 % SLA**) | **+$150** |
| Container Registry | `Basic` | `Standard` (100 GB, higher throughput) | **+$15** |
| Storage | `Standard_LRS` | `Standard_ZRS` (zone-redundant) | +~25 % on storage/txn — a few $ |
| Web Container App | scale 0→2 (cold start after idle) | scale **1**→4 (a replica always warm) | **+$15–20** |
| Log Analytics | 30-day retention | 90-day retention | a few $ (days 31–90 billed) |
| Foundry / models / Functions | — | unchanged | $0 |

**Rough total: +$300–450/month**, dominated by Search `basic` and SQL leaving the
Free offer.

`prod` does **not** touch: private networking (private endpoints are descoped —
sponsor decision, cost; RLS + `sqlguard` + Entra-only auth carry the SQL data
plane), the all-Azure SQL firewall rule, model TPM, the Function tier, or
DR / multi-region.

**Moving an existing `free` deployment to `prod`:** AI Search and the SQL
free-limit are **not** in-place editable. A fresh `azd up --e prod-env` is clean;
converting in place means the search service is replaced (re-run
`scripts/setup_search.py`) and the DB needs `az sql db update ... --set-free-limit`
removed or a recreate — **export the engagement(s) first**
(`GET /api/engagements/<c>/<p>/export`).

---

## Cost

Idle: a few dollars a month (storage + Log Analytics). Per estimate run: a few tens of
cents of `gpt-4o` tokens. AI Search Free, SQL Free offer, Container Apps and Functions
free grants keep the rest at $0. Expect **$5–15/month** at 5–20 runs on the `free` tier;
**~$350–450/month** on `prod` (see the table above).

A clean-machine CI run provisions a full throwaway stack: budget ~**$1–3** of
compute/model spend per run (mostly the GP_S SQL + a few model tokens), then
`azd down --purge` takes it to zero.

### Cost guardrails (E13.4) — for a fixed monthly budget

If you run Landfall on a fixed budget (see `prd/engagement-workspaces-prd.md` §4.15
— the reference target is **$40–50/month, deployed on demand**), a default `azd up`
now creates:

| Guardrail | Default | Env var |
|---|---|---|
| **Cost Management budget** on the resource group + alerts at **actual 50 %, actual 80 %, forecast 100 %** — emails `ALERT_EMAIL` (if set) and always the RG **Owner**. In the **subscription billing currency** (run `scripts/spend.py` to see yours; on an INR sub set ~4200 for a $50 target) | **50, ON** (`0` opts out) | `MONTHLY_BUDGET` |
| **Log Analytics daily ingestion cap** — a runaway-telemetry brake (`prod` uncaps) | **0.5 GB/day** (`-1` = uncapped) | `LOG_ANALYTICS_DAILY_CAP_GB` |
| **`ca-calc` always-on replicas** — `1` keeps the POE queue worker running while the stack is up (a few $/month — the ACA free grant covers most of the idle). `0` is cheaper but a POE run may sit unprocessed (KEDA MI-auth scale-up didn't work in C25b) | **1** | `CALC_MIN_REPLICAS` |

```bash
azd env set MONTHLY_BUDGET 50               # in your BILLING currency (e.g. 4200 on an INR sub)
azd env set ALERT_EMAIL you@example.com     # so the alert reaches you, not just the Owner role
azd up
```

**The budget is a safety net, not the control.** What actually keeps the bill low:

1. **Never `DEPLOYMENT_TIER=prod`** — it flips AI Search free→`basic` (~$75/mo) and
   SQL off the Free offer. `free` (default) is ~$0 idle. This is the only realistic
   way to overshoot a $40–50 budget.
2. **`azd down --purge` between sessions** — `--purge` (not plain `azd down`) so
   nothing lingers in soft-delete (Cognitive Services, Key Vault, Log Analytics).
   A purged deployment costs **$0**. (Grounded: the live stack left up runs
   ~$5–12/month, so this is a good habit rather than a hard necessity.)
3. On a **Visual Studio subscription**, keep the **spending limit ON** — a hard $0
   stop when the monthly credit runs out.

Check month-to-date spend against the budget any time:

```bash
python scripts/spend.py                      # RG from `azd env get-values`
python scripts/spend.py --rg rg-landfall --budget 50 --json
```

(Cost Management data lags ~8–24 h and needs the *Cost Management Reader* role.)
