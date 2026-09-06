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
Client inventory exports ──► ADLS Gen2 ──► Normalize (Durable Function) ──► Azure SQL (Free)
   (RVTools, CMDB, app portfolio, docs)          │                              servers / applications
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
| Models | `gpt-4o-mini` + `text-embedding-3-small` |
| Agent host | Azure AI Foundry Agent Service |
| Agent tools | AI Search · Azure SQL text-to-SQL · Azure Retail Prices API · VM right-size heuristic · Microsoft Learn MCP |
| Chat UI | Azure Container Apps (scale-to-zero) |
| Batch runner | Azure Durable Functions (Consumption) |

Typical cost: **$3–10/month**, almost entirely Azure OpenAI tokens for the runs you actually do.

## Repository contents

| Path | What |
|---|---|
| [`docs/build-spec.html`](docs/build-spec.html) | **Solution build specification** — architecture, SQL model, agent tools, estimation methodology, phased build plan, cost table, risk register |
| [`docs/effort-and-resource-loading.html`](docs/effort-and-resource-loading.html) | **Pre-sales estimation pack** — parametric effort model, reference-estate roll-up, 6-month resource-loading plan, commercial roll-up, Microsoft funding levers, assumptions & risks |
| [`docs/discovery-questionnaire.html`](docs/discovery-questionnaire.html) | **Client discovery questionnaire** — data pack request + ~100 questions across 15 domains, working assumptions register (AS-01…14), risk register (RK-01…12) |
| [`src/function_app.py`](src/function_app.py) | Durable Functions batch runner for the RFP question sheet (Python v2 model, fan-out / fan-in) |

Open the `docs/*.html` files in a browser — they are self-contained, theme-aware pages.

## Deploying `src/function_app.py`

Python v2 Azure Functions app. Pair with:

**`host.json`**
```json
{
  "version": "2.0",
  "extensions": {
    "durableTask": {
      "maxConcurrentActivityFunctions": 3,
      "maxConcurrentOrchestratorFunctions": 1
    }
  }
}
```

**`requirements.txt`**
```
azure-functions
azure-functions-durable
azure-identity
azure-ai-projects
azure-storage-blob
pandas
openpyxl
```

**App settings**

| Setting | Value |
|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | `https://<proj>.services.ai.azure.com/api/projects/<name>` |
| `AGENT_ID` | the Migration Estimator agent id |
| `STORAGE_URL` | `https://<account>.blob.core.windows.net` |
| `STORAGE_CONN` | connection config for the blob trigger |

The Function app's managed identity needs **Storage Blob Data Contributor** on the storage
account and **Azure AI Developer** on the Foundry project.

## Before you run

Create an `estimation_config.json` with **your firm's** numbers — the agent applies these
rather than inventing rates:

- S / M / L / XL migration effort-hour bands
- reserved-instance term assumption (1yr / 3yr / none)
- non-prod + DR compute uplift %
- PM / testing / cutover overhead %

## Between engagements

Nothing runs continuously. Leave it idle (cost is already ~$0) or delete the resource group
and redeploy from a Bicep template + `schema.sql` next time (~10 min). Keep the ADLS account
and Key Vault only if you need to retain prior clients' data.
