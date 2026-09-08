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

1. **Lock down the chat UI.** The Container App ingress is public until you add auth.
   ```bash
   RG=$(azd env get-value AZURE_RESOURCE_GROUP); WEB=$(azd env get-value SERVICE_WEB_NAME)
   TENANT=$(az account show --query tenantId -o tsv)
   FQDN=$(az containerapp show -g "$RG" -n "$WEB" --query properties.configuration.ingress.fqdn -o tsv)
   APPID=$(az ad app create --display-name "landfall-web ($WEB)" --sign-in-audience AzureADMyOrg \
     --web-redirect-uris "https://$FQDN/.auth/login/aad/callback" --enable-id-token-issuance true \
     --query appId -o tsv)
   az ad sp create --id "$APPID"
   SECRET=$(az ad app credential reset --id "$APPID" --years 2 --query password -o tsv)
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

3. **Harden `query_inventory`** *(strongly recommended)*. The OpenAPI tools ship as
   **anonymous** HTTP functions on the Function app so the first deploy works.
   `vm_rightsize`, `estimate_compute_cost`, `estimate_storage_cost`,
   `estimate_run_rate_extras`, `design_landing_zone`, `score_dispositions`,
   `plan_waves`, `assemble_estimate` and `azure_retail_prices` hold no client data
   (they take their inputs in the request body). `query_inventory` returns
   inventory rows — its SQL is a single `SELECT`/`WITH` against the six inventory
   tables only, no comments, no admin/timing keywords, 200-row cap, 20 s statement
   timeout (`src/api/sqlguard.py`, E8.3); the question and SQL text never reach the
   logs, only a hash + the table list (E8.4). Still, put Entra auth in front of it:
   ```bash
   # provision-time (preferred): turn EasyAuth on via the template
   APPID=$(az ad app create --display-name "landfall-func ($(azd env get-value SERVICE_API_NAME))" \
     --identifier-uris "api://$(azd env get-value SERVICE_API_NAME)" --query appId -o tsv)
   azd env set ENABLE_FUNCTION_AUTH true
   azd env set FUNCTION_AUTH_CLIENT_ID "$APPID"
   azd provision            # applies authsettingsV2 with excludedPaths ["/runtime"]
   AGENT_TOOL_AUTH=managed FUNC_AUTH_AUDIENCE="api://$(azd env get-value SERVICE_API_NAME)" \
     python scripts/create_agent.py     # agent now calls it with its managed identity
   ```
   Or, on an already-running app, the CLI path:
   ```bash
   RG=$(azd env get-value AZURE_RESOURCE_GROUP); FUNC=$(azd env get-value SERVICE_API_NAME)
   az webapp auth set -g "$RG" -n "$FUNC" --body @scripts/funcapp-auth.json
   AGENT_TOOL_AUTH=managed python scripts/create_agent.py
   ```
   `excludedPaths: ["/runtime"]` keeps the Event Grid webhook and durable
   endpoints reachable. Skip this only if the agent must call `query_inventory` and you
   accept the public endpoint for the life of the engagement.

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

---

## Cost

Idle: a few dollars a month (storage + Log Analytics). Per estimate run: a few tens of
cents of `gpt-4o` tokens. AI Search Free, SQL Free offer, Container Apps and Functions
free grants keep the rest at $0. Expect **$5–15/month** at 5–20 runs.
