# Landfall — Prerequisites, Installation &amp; Deployment

A complete walkthrough from a clean machine to a running solution. If you already have
the Azure tooling, skip to [§4](#4-get-the-code).

- [1. What you are deploying](#1-what-you-are-deploying)
- [2. Azure account prerequisites](#2-azure-account-prerequisites)
- [3. Install the tooling](#3-install-the-tooling)
- [4. Get the code](#4-get-the-code)
- [5. Deploy](#5-deploy)
- [6. Post-deployment configuration](#6-post-deployment-configuration)
- [7. Load data and run](#7-load-data-and-run)
- [8. Verify](#8-verify)
- [9. Update, redeploy, tear down](#9-update-redeploy-tear-down)
- [10. Troubleshooting](#10-troubleshooting)

---

## 1. What you are deploying

| Component | Azure service | Tier |
|---|---|---|
| File store | Storage account, ADLS Gen2 (hierarchical namespace) | Standard LRS |
| Structured inventory store | Azure SQL Database | **Free offer** (serverless, auto-pause) |
| Narrative-doc retrieval index | Azure AI Search | **Free** |
| Models | Azure OpenAI `gpt-4o` + `text-embedding-3-small` | 30K TPM each |
| Agent runtime | Microsoft Foundry account + project — prompt agent via the Responses API | S0 control plane |
| Chat UI | Azure Container App | Consumption, scale-to-zero |
| RFP batch runner | Azure Functions (Durable) | Flex Consumption |
| Secrets / logging | Key Vault, Log Analytics, Application Insights | Standard / free grant |

Running cost at 5–20 estimate runs/month: **$5–15**, almost all `gpt-4o` tokens.

---

## 2. Azure account prerequisites

You need **all** of the following:

1. **An Azure subscription.** A pay-as-you-go or MSDN/Visual Studio subscription is fine.
   A brand-new free-trial subscription also works but check the model quota (step 5).

2. **Permission to create resources _and assign roles_** in that subscription. The Bicep
   creates data-plane role assignments (Storage, Search, Foundry, ACR, Key Vault), so you
   need one of:
   - **Owner** on the subscription or on a resource group you pre-create, or
   - **Contributor + User Access Administrator**.

   Check with:
   ```bash
   az role assignment list --assignee "$(az ad signed-in-user show --query id -o tsv)" \
     --query "[].roleDefinitionName" -o tsv
   ```

3. **Ability to register resource providers** (or have an admin do it once):
   ```bash
   for p in Microsoft.Storage Microsoft.Search Microsoft.CognitiveServices \
            Microsoft.Sql Microsoft.Web Microsoft.App Microsoft.ContainerRegistry \
            Microsoft.KeyVault Microsoft.OperationalInsights Microsoft.Insights \
            Microsoft.ManagedIdentity; do
     az provider register --namespace $p
   done
   ```

4. **Azure OpenAI access.** On most subscriptions `gpt-4o` and
   `text-embedding-3-small` are available immediately. If your subscription has never used
   Azure OpenAI, the first deployment in a region may require a one-time enablement.

5. **A region that has all of:** the two models, the Azure SQL **free offer**, Container
   Apps, and Microsoft Foundry project management (`allowProjectManagement`). Good
   choices: `eastus2`, `westus3`, `swedencentral`, `uksouth`.
   The free SQL offer is **one per subscription** — if you already used it, the deploy
   fails on the database; see [§10](#10-troubleshooting).

6. **The Azure SQL free-offer limit is one database per subscription.** Confirm none is
   already claimed:
   ```bash
   az sql db list --query "[?currentSku.name=='GP_S_Gen5' && properties.useFreeLimit].name" -o tsv 2>/dev/null
   ```

---

## 3. Install the tooling

You need six tools. Commands are grouped by OS.

| Tool | Min version | Purpose |
|---|---|---|
| Git | any | clone the repo |
| Azure Developer CLI (`azd`) | 1.11 | orchestrates provision + deploy |
| Azure CLI (`az`) | 2.60 | used by the postprovision hook |
| Python | 3.11.x | runs the helper scripts and the Functions/UI code locally |
| Docker | any recent | `azd` builds the chat-UI container image |
| `sqlcmd` (go-sqlcmd) | 1.6 | loads the SQL schema with Entra auth |
| PowerShell 7 (`pwsh`) | 7.2 | postprovision hook on Windows (optional on macOS/Linux — the `.sh` hook is used there) |

### Windows (winget)

```powershell
winget install --id Git.Git -e
winget install --id Microsoft.Azd -e
winget install --id Microsoft.AzureCLI -e
winget install --id Python.Python.3.11 -e
winget install --id Docker.DockerDesktop -e
winget install --id Microsoft.Sqlcmd -e
winget install --id Microsoft.PowerShell -e
```

Close and reopen the terminal so `PATH` updates. Start Docker Desktop and wait until it
says "running".

### macOS (Homebrew)

```bash
brew install git python@3.11 azure-cli
brew install azd
brew install --cask docker
brew install sqlcmd
brew install --cask powershell   # optional
```

Launch Docker Desktop once so the daemon starts.

### Linux (Debian/Ubuntu)

```bash
# git, python
sudo apt-get update && sudo apt-get install -y git python3.11 python3-pip

# azd
curl -fsSL https://aka.ms/install-azd.sh | bash

# az
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out/in afterwards

# sqlcmd (go-sqlcmd)
curl -fsSL -o sqlcmd.tar.bz2 https://github.com/microsoft/go-sqlcmd/releases/latest/download/sqlcmd-linux-amd64.tar.bz2
sudo tar -xjf sqlcmd.tar.bz2 -C /usr/local/bin sqlcmd && rm sqlcmd.tar.bz2
```

### Verify all six

```bash
git --version
azd version
az version
python --version        # or python3 --version  -> 3.11.x
docker --version && docker info >/dev/null && echo "docker ok"
sqlcmd --version
```

---

## 4. Get the code

```bash
git clone https://github.com/upendra25312/Landfall.git
cd Landfall
```

---

## 5. Deploy

### 5.1 Sign in (both CLIs, same account and tenant)

```bash
azd auth login
az login
az account set --subscription "<your-subscription-id-or-name>"
```

### 5.2 Create an environment

```bash
azd env new landfall
azd env set AZURE_LOCATION eastus2
```

Optional overrides:

```bash
azd env set MODEL_CAPACITY 10                       # if you have limited TPM quota
azd env set CHAT_MODEL_VERSION 2024-11-20           # if the default is retired in your region
azd env set EMBEDDING_MODEL_VERSION 1
```

### 5.3 Check model quota for the region

```bash
az cognitiveservices usage list -l eastus2 \
  --query "[?contains(name.value,'gpt-4o') || contains(name.value,'text-embedding-3-small')].{name:name.value, current:currentValue, limit:limit}" -o table
```

If `limit - current` is below `MODEL_CAPACITY` (default 30) for either model, either lower
`MODEL_CAPACITY` or request an increase in the Azure AI Foundry portal → *Quota*.

### 5.4 Provision and deploy

```bash
azd up
```

This runs, in order:

1. **provision** — `infra/main.bicep` → `infra/resources.bicep`. ~8–12 minutes. Creates
   the resource group `rg-landfall` and every resource in [§1](#1-what-you-are-deploying),
   plus all role assignments on a shared user-assigned managed identity.
2. **postprovision** — `scripts/postprovision.ps1` (Windows) or `.sh` (macOS/Linux):
   - installs `scripts/requirements.txt`,
   - loads `scripts/schema.sql` into the SQL database via `sqlcmd` (Entra auth),
   - runs `scripts/setup_search.py` — builds the AI Search data source, skillset
     (split + embed at 512 dimensions), index, and indexer,
   - runs `scripts/create_agent.py` — creates (versions) the **Migration Estimator**
     prompt agent with the Microsoft Learn MCP tool and the AI Search tool. The agent is
     addressed by **name** (`landfall-migration-estimator`), not an `asst_` id; that name
     is stored as `AGENT_ID` in the azd environment and pushed to the Function app and
     Container App.
3. **deploy** — zip-deploys `src/api` to the Function app; builds the `src/web` Docker
   image, pushes it to the container registry, and updates the Container App.
4. **postdeploy** — `scripts/eventgrid.ps1` / `.sh`: creates the `landfall-questions`
   Event Grid subscription on the storage account's system topic so blobs dropped in the
   `questions/` container trigger the batch runner. On the Flex Consumption plan a blob
   trigger *must* be driven by Event Grid, and the subscription's webhook needs the
   function app's `blobs_extension` key — which only exists after `deploy` — so this is a
   post-deploy step. It is idempotent and marked `continueOnError`: if the function host
   is still warming up when it runs, re-run it by hand once the host is up:
   ```bash
   azd hooks run postdeploy
   ```

On success `azd` prints outputs including **`SERVICE_WEB_URI`** — the chat UI URL.

See every value any time with:

```bash
azd env get-values
```

---

## 6. Post-deployment configuration

Five one-time steps. Only #1 is required before sharing the URL.

### 6.1 (Required) Lock down the chat UI

The Container App ingress is public until you add authentication.

Portal: **Container App → Settings → Authentication → Add identity provider → Microsoft**
→ accept the app-registration defaults → **Restrict access: Require authentication** →
*Unauthenticated requests: HTTP 302 redirect to log in*.

CLI equivalent:

```bash
RG=$(azd env get-value AZURE_RESOURCE_GROUP)
WEB=$(azd env get-value SERVICE_WEB_NAME)
az containerapp auth microsoft update -g "$RG" -n "$WEB" \
  --client-id "<new-app-registration-client-id>" \
  --issuer "https://login.microsoftonline.com/$(az account show --query tenantId -o tsv)/v2.0"
az containerapp auth update -g "$RG" -n "$WEB" --unauthenticated-client-action RedirectToLoginPage
```

### 6.2 (If warned) Add the Foundry → AI Search connection

If `create_agent.py` printed `WARN: no Foundry connection found for the search service`:

Portal: **Azure AI Foundry → your project → Management center → Connected resources →
+ New connection → Azure AI Search →** pick the `srch-…` service → **Connect**.

Then re-run just the agent step:

```bash
# reload env vars, then:
python scripts/create_agent.py
```

### 6.3 (Optional, adds SQL + pricing answers) The three OpenAPI tools

`query_inventory`, `vm_rightsize`, and `azure_retail_prices` are Function endpoints the
agent calls. Their scaffolds are a follow-up task; the agent answers document questions
without them. When built, add each in **Foundry → Agents → Migration Estimator → Tools →
+ Add → OpenAPI 3.0** and paste the spec URL from the Function app.

### 6.4 (Recommended) Budget alert

Portal: **Cost Management → Budgets → Add** → amount **$25**, alerts at **50 / 80 / 100%**
to your email.

### 6.5 (Recommended) Confirm data-handling approval

Before uploading any client inventory, confirm with the client that placing it in this
storage account is covered by your MNDA/DPA. See the discovery questionnaire, question
SC7.

---

## 7. Load data and run

### 7.1 Upload inventory and documents

```bash
ACC=$(azd env get-value AZURE_STORAGE_ACCOUNT)

# narrative docs -> indexed automatically (6-hourly, or trigger now in the Search portal)
az storage blob upload-batch --account-name "$ACC" --auth-mode login \
  -d "raw/docs" -s ./client-docs

# inventory spreadsheets -> staged; load into SQL next
az storage blob upload-batch --account-name "$ACC" --auth-mode login \
  -d "raw/inventory" -s ./client-inventory
```

### 7.2 Load inventory into SQL

Load your RVTools / CMDB / app-portfolio spreadsheets into the `servers`,
`applications`, `dependencies`, `storage` tables (`scripts/schema.sql` defines them).
Use Azure Data Studio's flat-file import, `bcp`, or a small load script — whatever fits
your data. Column names in `schema.sql` are what the agent's `query_inventory` tool
expects.

### 7.3 Ask questions

- **Chat:** open `SERVICE_WEB_URI`, sign in, ask (e.g. *"How many prod Windows Server 2012
  VMs, and total vCPU across them?"*).
- **Batch:** put questions in column **Question** of an `.xlsx`, upload to the
  `questions/` container. The Durable Function fans out, answers each, and writes
  `<name>_answered.xlsx` to the `answers/` container. `samples/smoke-questions.xlsx` is a
  two-question sheet for a first end-to-end test:
  ```bash
  az storage blob upload --account-name "$ACC" --auth-mode login \
    -c questions -f samples/smoke-questions.xlsx -n smoke-questions.xlsx
  ```

---

## 8. Verify

```bash
RG=$(azd env get-value AZURE_RESOURCE_GROUP)

# resources exist
az resource list -g "$RG" --query "[].{name:name, type:type}" -o table

# function app is running and has the agent id
az functionapp config appsettings list -g "$RG" -n "$(azd env get-value SERVICE_API_NAME)" \
  --query "[?name=='AGENT_ID'].value" -o tsv

# chat UI health probe (before you enable auth)
curl -s "$(azd env get-value SERVICE_WEB_URI)/healthz"
# -> {"ok": true, "agent_configured": true}

# search index built
az search service show -g "$RG" -n "$(azd env get-value AZURE_SEARCH_ENDPOINT | sed 's|https://||;s|.search.windows.net||')" \
  --query "status" -o tsv
```

In the **Azure AI Foundry portal → Agents**, you should see `landfall-migration-estimator`
with the `microsoft_docs` (MCP) and `search_documents` tools attached. Use the playground
to test.

---

## 9. Update, redeploy, tear down

```bash
azd deploy api            # redeploy only the Function app after editing src/api
azd deploy web            # rebuild + redeploy only the chat UI
azd provision             # re-apply infra changes (infra/*.bicep)
azd up                    # everything

azd down --purge          # delete all resources, including soft-deleted Key Vault + Foundry
```

`azd down --purge` between engagements takes run cost to zero. `azd up` rebuilds in
~15 minutes. Keep the storage account (remove it from `azd down` scope, or back up the
containers first) if you must retain a prior client's data.

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `provision` fails on the SQL database with a free-offer error | The subscription already used its one free SQL database. Edit `infra/resources.bicep` → `sqlDatabase` → remove `useFreeLimit`/`freeLimitExhaustionBehavior` and set `sku` to `{ name: 'GP_S_Gen5_1', tier:'GeneralPurpose', family:'Gen5', capacity:1 }` (~$5/mo serverless), then `azd provision`. |
| `provision` fails creating role assignments (`AuthorizationFailed`) | You lack **User Access Administrator** / **Owner**. Ask an admin to run `azd provision`, or pre-create `rg-landfall` and grant yourself Owner on it. |
| Model deployment fails with a quota error | Lower `azd env set MODEL_CAPACITY 10` (or less) and re-run, or request quota in Foundry → Quota. |
| `postprovision` skips the schema — "sqlcmd not found" | Install go-sqlcmd (step 3), then run `scripts/schema.sql` manually: `sqlcmd -S <AZURE_SQL_SERVER_FQDN> -d <AZURE_SQL_DATABASE> --authentication-method ActiveDirectoryDefault -i scripts/schema.sql`. |
| `sqlcmd` login fails | The Entra admin on the SQL server is the deploying user (set by Bicep). Sign in with that same account: `az login`. Also add your client IP: `az sql server firewall-rule create -g <rg> -s <sql-server> -n me --start-ip-address <ip> --end-ip-address <ip>`. |
| `create_agent.py` warns about the search connection | See [§6.2](#62-if-warned-add-the-foundry--ai-search-connection). |
| Chat UI returns `503 AGENT_ID not set` | postprovision did not finish. Re-run: `azd hooks run postprovision` (reloads env, re-creates the agent, re-pushes `AGENT_ID`). Or by hand: `python scripts/create_agent.py` prints `AGENT_ID=<name>`; then `azd env set AGENT_ID <name>` and `az containerapp update -g <rg> -n <web> --set-env-vars AGENT_ID=<name>`. |
| Batch runner never fires when a workbook lands in `questions/` | The Event Grid subscription is missing (postdeploy skipped or the key wasn't ready). Run `azd hooks run postdeploy`. Check it exists: `az eventgrid system-topic event-subscription list --system-topic-name "$(azd env get-value AZURE_EVENTGRID_SYSTEM_TOPIC)" -g <rg> -o table`. |
| `create_agent.py` fails with `allowProjectManagement` / project-agents API errors | The region or the Foundry account predates the prompt-agents surface. Confirm the account was provisioned with `allowProjectManagement: true` (it is in `infra/resources.bicep`) and that the region supports it; redeploy in `eastus2` if unsure. |
| `azd deploy web` fails to build | Docker Desktop not running, or you are not logged into the registry. `azd` handles registry auth; ensure `docker info` works. |
| First chat request after idle is slow (~10 s) | Container App and SQL free offer both scale/auto-pause. Expected. Set Container App `minReplicas: 1` in `infra/resources.bicep` if you need it warm (small cost). |
| Search index near 50 MB / indexer errors | Free tier cap. Index fewer docs (put the rest in `raw/archive/`), or move to AI Search Basic — change `sku.name` to `basic` in `infra/resources.bicep` (~$75/mo). |
