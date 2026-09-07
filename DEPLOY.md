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
(pushes `src/api` and `src/web`) → `postdeploy` hook (Event Grid subscription).

---

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| [Azure Developer CLI](https://aka.ms/azd) ≥ 1.11 | orchestrates everything | `winget install microsoft.azd` / `brew install azd` |
| [Azure CLI](https://aka.ms/azcli) | used by the postprovision hook | `winget install -e --id Microsoft.AzureCLI` |
| Python 3.11 + pip | runs the helper scripts | — |
| [`sqlcmd` (go-sqlcmd)](https://learn.microsoft.com/sql/tools/sqlcmd/sqlcmd-utility) | loads the SQL schema | `winget install sqlcmd` / `brew install sqlcmd` |
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
   - loads `scripts/schema.sql` into the SQL database (Entra auth) and grants the
     workload identity read-only access (`grant_api_sql.sql`, for `query_inventory`),
   - builds the AI Search data source / skillset / index / indexer (`setup_search.py`),
   - creates (versions) the **Migration Estimator** prompt agent (`create_agent.py`) with
     the Microsoft Learn MCP tool, the AI Search tool, and the three OpenAPI tools
     (`query_inventory`, `vm_rightsize`, `azure_retail_prices`) pointed at the Function
     app. The agent is addressed by **name** (`landfall-migration-estimator`), not an
     `asst_` id; that name is written to `AGENT_ID` in the azd env and pushed to both
     running services.
3. **deploy** — zip-deploys `src/api` to the Function app and builds + pushes the
   `src/web` image to the registry, then updates the Container App.
4. **postdeploy** (`scripts/eventgrid.*`) — creates the `landfall-questions` Event Grid
   subscription so blobs dropped in `questions/` trigger the `start` function. This runs
   after `deploy` because the subscription's webhook needs the function app's
   `blobs_extension` system key, which only exists once the function is published.
   Idempotent and `continueOnError` — re-run by hand with `azd hooks run postdeploy` if
   the function host was still warming up.

At the end `azd` prints the **`SERVICE_WEB_URI`** — the chat UI.

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

3. **Harden `query_inventory`** *(strongly recommended)*. The three OpenAPI tools ship as
   **anonymous** HTTP functions on the Function app so the first deploy works.
   `vm_rightsize` and `azure_retail_prices` hold no client data. `query_inventory` returns
   inventory rows (SELECT-only, read-only DB user, 200-row cap), so put Entra auth in
   front of it:
   ```bash
   RG=$(azd env get-value AZURE_RESOURCE_GROUP); FUNC=$(azd env get-value SERVICE_API_NAME)
   # 1. fill in the <...> tokens in scripts/funcapp-auth.json (tenant id, an app
   #    registration client id, api://$FUNC audience, the Foundry account MI object id:
   #    az cognitiveservices account show -g $RG -n $(azd env get-value FOUNDRY_ACCOUNT_NAME) --query identity.principalId -o tsv )
   az webapp auth set -g "$RG" -n "$FUNC" --body @scripts/funcapp-auth.json
   # 2. re-attach query_inventory with managed-identity auth
   AGENT_TOOL_AUTH=managed python scripts/create_agent.py
   ```
   `excludedPaths: ["/runtime"]` in the template keeps the Event Grid webhook and durable
   endpoints reachable. Skip this only if the agent must call `query_inventory` and you
   accept the public endpoint for the life of the engagement.

4. **Load client data.** Upload narrative docs to `raw/docs/` (the indexer picks them up
   on its 6-hour schedule, or run it now). Load the four inventory tables in SQL with
   your own import (Azure Data Studio, `bcp`, or a script). **To demo without client
   data**, `sample-estate/` has a synthetic 250-server / 31-app estate plus a completed
   discovery questionnaire and effort model:
   ```bash
   python sample-estate/load_estate.py            # -> SQL (Entra auth)
   ACC=$(azd env get-value AZURE_STORAGE_ACCOUNT)
   az storage blob upload-batch --account-name "$ACC" --auth-mode login \
     -d raw/docs -s sample-estate --pattern "*.md"
   ```

5. **Budget alert.** Cost Management → Budgets → $25 with alerts at 50 / 80 / 100%.

---

## Everyday commands

```bash
azd deploy api          # redeploy just the Function app after a code change
azd deploy web          # rebuild + redeploy just the chat UI
azd provision           # re-apply infra changes
azd hooks run postprovision   # rebuild SQL schema / search index / agent
azd hooks run postdeploy      # re-create the Event Grid subscription for the batch runner
azd env get-values      # see all endpoints / names
azd down --purge        # delete everything (including soft-deleted Key Vault / Foundry)
```

`azd down` between engagements takes the run cost to zero; `azd up` rebuilds in ~15 min.

---

## Cost

Idle: a few dollars a month (storage + Log Analytics). Per estimate run: a few tens of
cents of `gpt-4o` tokens. AI Search Free, SQL Free offer, Container Apps and Functions
free grants keep the rest at $0. Expect **$5–15/month** at 5–20 runs.
