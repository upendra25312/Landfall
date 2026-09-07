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
(pushes `src/api` and `src/web`).

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

Quota: the deployment needs **30K TPM each** for `gpt-4o-mini` (GlobalStandard) and
`text-embedding-3-small` (Standard) in your chosen region. Check
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
#    azd env set CHAT_MODEL_VERSION 2024-07-18
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
   - loads `scripts/schema.sql` into the SQL database (Entra auth),
   - builds the AI Search data source / skillset / index / indexer (`setup_search.py`),
   - creates the **Migration Estimator** agent with the Microsoft Learn MCP tool and the
     AI Search tool (`create_agent.py`), then writes `AGENT_ID` into the azd env and into
     both running services.
3. **deploy** — zip-deploys `src/api` to the Function app and builds + pushes the
   `src/web` image to the registry, then updates the Container App.

At the end `azd` prints the **`SERVICE_WEB_URI`** — the chat UI.

---

## Manual follow-ups (not yet automated)

These need the portal or a couple of CLI calls once, after the first `azd up`:

1. **Lock down the chat UI.** Container App → *Authentication* → add Microsoft (Entra ID)
   as identity provider, set *Restrict access: Require authentication*. Until you do
   this the UI is reachable by anyone with the URL.

2. **Foundry connection for AI Search.** If `create_agent.py` warned that no connection
   was found: Foundry portal → *Management center* → *Connected resources* → add your
   search service, then re-run `python scripts/create_agent.py` (env still loaded via
   `azd env get-values`).

3. **The three OpenAPI tools** (`query_inventory`, `vm_rightsize`, `azure_retail_prices`).
   Publish their OpenAPI specs from the Function app, then add them to the agent in the
   Foundry portal (*Agents* → tools → *OpenAPI 3.0*). The agent works without them for
   document questions; they add the SQL sizing / live-pricing answers. Scaffolding for
   these functions goes under `src/api/` as a follow-up.

4. **Load client data.** Upload inventory to `raw/inventory/` and narrative docs to
   `raw/docs/` in the storage account. The indexer picks up `raw/docs/` on its 6-hour
   schedule (or run it now from the Search portal). Load the inventory tables into SQL
   with your own import (Azure Data Studio, `bcp`, or a small load Function).

5. **Budget alert.** Cost Management → Budgets → $25 with alerts at 50 / 80 / 100%.

---

## Everyday commands

```bash
azd deploy api          # redeploy just the Function app after a code change
azd deploy web          # rebuild + redeploy just the chat UI
azd provision           # re-apply infra changes
azd env get-values      # see all endpoints / names
azd down --purge        # delete everything (including soft-deleted Key Vault / Foundry)
```

`azd down` between engagements takes the run cost to zero; `azd up` rebuilds in ~15 min.

---

## Cost

Idle: a few dollars a month (storage + Log Analytics). Per estimate run: cents of
`gpt-4o-mini` tokens. AI Search Free, SQL Free offer, Container Apps and Functions
free grants keep the rest at $0. Expect **$3–10/month** at 5–20 runs.
