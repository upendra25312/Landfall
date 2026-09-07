# sample-estate — synthetic client estate for demos & testing

A fabricated "client estate" the Landfall Migration Estimator can run against when you
have no real client data yet. **Not real** — seeded random data (`seed 42`) for a
fictional retailer, **Meridian Retail Group**.

## Contents

### Structured inventory (load into Azure SQL)

| File | Rows | Loads into |
|---|---|---|
| `servers.csv` | 250 VMware VMs — **150 Windows, 100 Linux** | `dbo.servers` |
| `applications.csv` | 31 applications (30 business + 1 infra bucket) | `dbo.applications` |
| `dependencies.csv` | ~490 network edges (web→app→db, plus AD / DNS / internet) | `dbo.dependencies` |
| `storage.csv` | ~570 volumes (OS + data disks, DB volumes, file shares) | `dbo.storage` |

Columns match `scripts/schema.sql` exactly.

### Narrative documents (upload to `raw/docs/` for the AI Search index)

| File | What |
|---|---|
| `discovery-answers.md` | The discovery questionnaire (`docs/discovery-questionnaire.html`) completed for this estate — every question B1–M6 answered, plus the assumptions (AS-01…14) and risk (RK-01…12) registers, all consistent with the CSVs. |
| `effort-inputs.md` | The parametric effort model (`docs/effort-and-resource-loading.html`) populated with this estate's actuals — reference-estate counts, disposition mix, 7-wave plan, effort roll-up (~775 PD), 6-month resource loading, commercial roll-up. |

`search_documents` on the agent retrieves from these once they're indexed (see below).

## What's in it (so an assessment has something to chew on)

- **OS spread with real EOL exposure** — Windows Server 2012 R2 / 2016 / 2019 / 2022;
  RHEL 7.9 / 8.8 / 9.3, Ubuntu 18.04 / 20.04 / 22.04, SLES 15. ~80 servers are already
  past OS end-of-support.
- **Sizing + utilisation** — vCPU 2–64, RAM 8–512 GB, provisioned vs used disk. ~25% of
  servers have **no performance history** (`cpu_avg_pct` etc. blank) to exercise the
  low-confidence right-sizing path.
- **Placement** — 3 datacentres (Ashburn, Dallas, DR-Reno), vSphere clusters per env,
  `prod` / `nonprod` / `dev` / `dr`, ~6% powered off.
- **Applications** — 3-tier apps (web/app/db) mapped to their servers via `servers.app_id`;
  criticality 1–4, user counts, tech stacks, `db_engine`, `internet_facing`,
  compliance scope (PCI-DSS / SOX / HIPAA / GDPR). `disposition` / `complexity` / `wave`
  left blank for the agent to fill.
- **Dependencies** — tier-to-tier edges with ports/protocols, every server to AD + DNS,
  inbound `internet → web` edges for internet-facing apps.

## Regenerate

```bash
python sample-estate/generate_estate.py      # rewrites the 4 CSVs deterministically
```

Edit `APP_DEFS` / `INFRA_ROLES` / the OS weight tables at the top to reshape it.

## Load into Azure SQL

**Option A — the ingestion pipeline (same path a real client dump takes):** upload the
CSVs to `raw/inventory/` and the Normalize function detects, maps, and loads them, then
writes a data-quality report to `answers/_ingest/`.

```bash
ACC=$(azd env get-value AZURE_STORAGE_ACCOUNT)
az storage blob upload-batch --account-name "$ACC" --auth-mode login \
  -d raw/inventory -s sample-estate --pattern "*.csv"
```

**Option B — the direct loader (no deploy needed, for local iteration):**

```bash
# env-driven (AZURE_SQL_SERVER_FQDN / AZURE_SQL_DATABASE from .azure/<env>/.env)
python sample-estate/load_estate.py                 # truncate + load
python sample-estate/load_estate.py --append        # keep existing rows
python sample-estate/load_estate.py --server sql-x.database.windows.net --database sqldb-landfall
```

Entra auth via `DefaultAzureCredential`. The loader drops `dependencies` edges whose
endpoints aren't real servers (e.g. `internet`) so the FKs resolve. The Free-offer DB
is serverless and auto-pauses — the first connect may take ~30–60 s while it resumes.

## Index the narrative docs

```bash
ACC=$(azd env get-value AZURE_STORAGE_ACCOUNT)
az storage blob upload-batch --account-name "$ACC" --auth-mode login \
  -d raw/docs -s sample-estate --pattern "*.md"
# then run the indexer now (or wait for its 6-hour schedule)
az rest --method post --resource https://search.azure.com \
  --url "$(azd env get-value AZURE_SEARCH_ENDPOINT)/indexers/landfall-docs-ixr/run?api-version=2024-07-01"
```

