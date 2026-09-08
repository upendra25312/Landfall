# Landfall — Engagement Workspaces (multi-client, dashboard-driven)

**Status:** IN PROGRESS (C18 live; C19–C25 planned) · **Raised:** 2026-09-08 ·
**Owner panel:** see below · **Method:** PDCA
**Rolls into:** the "Landfall to 5/5" PRD as **Epic E11**. Supersedes the
"one `azd` deployment per engagement" assumption in
[`audits/2026-09-07-production-readiness-review.md`](../audits/2026-09-07-production-readiness-review.md)
(SEC-2 / OPS-1) for the common case.

---

## 1. The ask (verbatim intent)

> The solution uses the **Azure AI Foundry agent** (`landfall-migration-estimator`) to
> generate the artifacts, deliverables, Excel / PPT / Word docs, charts and dashboards —
> **not Claude**. Data in the Azure Data Lake changes **per project and per client**; the
> deliverables must be **for a given project and a given client**, not a generic output.
>
> From the dashboard, an end user should be able to:
> 1. enter a **customer name** and **project name**;
> 2. choose the **target Azure region(s)** the landing zone will be deployed in — at the
>    point of uploading the inventory *(added 2026-09-08)*;
> 3. **upload** the client documents into ADLS — with a **unique folder per project /
>    customer**;
> 4. **start the analysis**;
> 5. use a **chat bot** with **pre-defined prompt cards** to drive the desired outcomes;
> 6. get an **Azure landing-zone + target-workload cost estimate built in the real Azure
>    Pricing Calculator**, shown on the dashboard and **downloadable as the calculator's
>    own Excel** to submit as **Proof of Estimate (POE)** for Microsoft migration funding
>    *(added 2026-09-08)*.
>
> Question: can we use the `docx`, `xlsx`, `presentation-skill` and `ppt-master` skills
> **at the Foundry agent**?

---

## 2. Expert panel (Microsoft-style working group)

| Role | Owns in this plan |
|---|---|
| **Cloud Solution Architect (Migrate)** | narrative fidelity to CAF + Migration Execution Guide; deliverable structure |
| **Data & AI Engineer** | Foundry agent contract, tool signatures, the `engagement` scoping argument |
| **App / Platform Engineer** | `src/web` dashboard UX, upload path, Container Apps |
| **Data Engineer** | ADLS layout, ingestion pipeline, SQL tenancy + migration |
| **Security & Compliance** | per-engagement isolation, access control, path-traversal, data residency |
| **FinOps** | keep it on free / near-free tiers; one deployment, many engagements |
| **Azure Pre-Sales Architect** | target-region choice, landing-zone BoM, the Pricing Calculator line-item spec, POE fidelity |
| **Microsoft Alliance / Partner Lead** | what each funding program (AMM, CAF, ECIF/MAP) accepts as POE; MCA/EA/CSP licensing program in the estimate |
| **Delivery Lead / PMO** | PDCA cadence, acceptance, cut-over from the single-tenant build |

---

## 3. Direct answers

### 3.1 What generates the artifacts — and can the four skills run "at the Foundry agent"?

**No — you cannot load Claude Code skills into a Foundry agent.** Azure AI Foundry Agent
Service gives an agent three things: **instructions** (system prompt), **tools**
(OpenAPI / Azure Functions, MCP, Code Interpreter, File Search, AI Search, Bing), and the
**Responses API**. There is no `SKILL.md` / plugin mechanism — a skill is a package of
instructions + scripts that *Claude Code* reads and executes on a filesystem with bash +
Node + Python. A Foundry `gpt-4o` agent calling OpenAPI tools has none of that.

**The agent orchestrates; it does not author documents.** It runs the estimation tools,
calls `assemble_estimate`, then calls `export_estimate` / `publish_estimate`, and points
the user at the dashboard. The files are produced by **deterministic Python** in
`src/api/deliverable/export.py` (openpyxl / python-docx / python-pptx, native charts).
No LLM writes a spreadsheet or a slide.

**So the four repos are used at three points, none of them "inside the agent":**

| Repo | Role in Landfall | Where it actually runs |
|---|---|---|
| [`anthropics/skills · xlsx`](https://github.com/anthropics/skills/tree/main/skills/xlsx) | **Design reference** for `to_xlsx`: derived cells are **formulas, not Python literals**; Excel-2007 functions only; `$#,##0` / fractions / parens. | Rules coded into `export.py`; a **CI step** runs a headless LibreOffice recalc — 0 formula errors to ship. *(E5.4q)* |
| [`anthropics/skills · docx`](https://github.com/anthropics/skills/tree/main/skills/docx) | **Design reference** for `to_docx`: US-Letter in DXA; dual table widths; numbering defs; authored so architect edits land as Word **tracked changes**, `accept_changes` → clean copy. | Rules coded into `export.py`. *(E5.4q)* |
| [`siril9/presentation-skill`](https://github.com/siril9/presentation-skill) | **Studio deck** (E5.6): `outline.json` from `latest.json` → preset + grammar → **pptxgenjs** → `qa_gate.py`. | A **containerised OpenAPI tool** — its own Container App with the Node toolchain. The agent calls `POST /generate_studio_deck`; it never runs the skill. *(E11.9)* |
| [`hugohe3/ppt-master`](https://github.com/hugohe3/ppt-master) | **Studio deck, design-rich variant**: SVG → native DrawingML, firm template preserved. | Same container. *(E11.9)* |

The in-Function `python-pptx` deck (rebuilt cycle 17 as a 12-slide narrative assessment)
is the always-available default; the studio-deck container is the higher-polish option a
pre-sales lead invokes from a prompt card.

> **Escape hatch:** Foundry **Code Interpreter** can run python-pptx / openpyxl in a
> sandbox, but it cannot run Node and it is non-deterministic. Keep it off the primary
> path; use it only for one-off "reshape this table" asks.

### 3.2 Changes already made (cycles 15–17, on `main`, deployed to `rg-landfall`)

| Change | Commit | Note |
|---|---|---|
| First live deploy of cycles 5–14; E1.1 / E1.5 / E1.6 / E5.4 / E5.5 verified live | `c75e81c` | + 3 deploy-bug fixes (`db_datawriter`, MSYS path-mangling, SQL enum hints) |
| **E8.2** — Function App EasyAuth on; anon `/api/*` → 401; agent calls tools via managed identity | `3d8254e` | Bicep params + DEPLOY recipe |
| SQL serverless-resume retry + malformed-array tolerance in the cost tools | `26fc0d6` | fault harness 30/30 |
| **`to_pptx` rebuilt** — 12-slide narrative "Azure Migration Assessment" deck: native doughnut/bar charts, colour-coded wave table, hub-spoke diagram, CAF/MEG lifecycle chevrons, DRAFT watermark + page number + speaker notes every slide | `2aed956` | deployed + re-published to the live dashboard |
| Docs: generation model clarified (agent orchestrates, does not author); MEG as narrative reference; the four skills' roles pinned | `76c19a7`, `8135326` | audit block, `path-to-5x5` §"Deliverable polish", PRD E5.4 / E5.6 |

**None of the multi-engagement work below is done — it is all net-new (Epic E11).**

### 3.3 The one architecture decision this plan takes

Move from **one deployment per engagement** (the old SEC-2 recommendation) to **one
deployment, many engagements, isolated by an engagement key** — because the ask is a
self-service dashboard where a pre-sales user spins up an engagement in seconds, not a
platform team running `azd up` per deal. Hard isolation (DB-per-engagement, ACL'd
folders) stays available as a `--tier regulated` option.

### 3.4 Proof of Estimate (POE) — the Azure Pricing Calculator is mandatory

**Sponsor requirement (2026-09-08):** for Microsoft migration-funding submissions
(Azure Migrate and Modernize / AMM, Cloud Accelerate Factory, partner-led ECIF / MAP),
the customer cost estimate must be the **Azure Pricing Calculator's own Excel export** —
an API-derived number (Retail Prices API, `estimate_compute_cost`) is *not* accepted as
POE. Landfall's existing cost tools stay the **internal** working estimate; the
calculator export is the **external** POE artifact, and both must agree within tolerance.

So Landfall drives the **real calculator** and captures **its** export. Feasibility was
proven end-to-end on 2026-09-08:

- The calculator is a React SPA whose product-config modules expose **semantically-named,
  long-stable form controls** — `select[name=region]` (values like `sweden-central`),
  `input[name=count]`, `input[name=hours]`, `input[name=size]` (+ a hidden size slug),
  `select[name=operatingSystem]` / `[name=tier]`, radio groups
  `…-computeBillingOption` (`payg` / `one-year` / `three-year` / `sv-one-year` / …) and
  `…-osBillingOption` (`payg` / `ahb`), `select[name=discountLevel]` (licensing program),
  `select[name=currentCurrency]`, and `input[name=estimate-name]`.
- Setting a control with the native value setter + `input`/`change` events drives the
  recompute (verified: region → Sweden Central, count → 40 → estimate recomputed to
  `$5,664.80/mo`).
- `button.export-button` downloads `ExportedEstimate.xlsx` — **single sheet
  `Your Estimate`**, fixed layout:

  | Row | Content |
  |---|---|
  | 1 | `Microsoft Azure Estimate` |
  | 2 | `<estimate name>` (from `input[name=estimate-name]`) |
  | 3 | `Service category | Service type | Custom name | Region | Description | Estimated monthly cost | Estimated upfront cost` |
  | 4…N | one row per configured resource — `Description` e.g. `40 D2 v3 (2 vCPUs, 8 GB RAM) x 730 Hours (Pay as you go)` |
  | | `Support` · `Licensing Program` = `Microsoft Customer Agreement (MCA)` · `Billing Account` · `Billing Profile` |
  | | `Total | | | | | <monthly> | <upfront>` |
  | | `Disclaimer` · `All prices shown are in United States Dollar (USD)…` · `This estimate was created at <ts>` |

- The calculator has **Export only** — no import. Estimates persist **in-memory** (not
  `localStorage`); a live shareable link needs **Log in → Save** (deferred, E11.19).

Because Playwright + Chromium cannot run in the Flex Consumption Function, this lives in a
**scale-to-zero Container App `ca-calc`** — the same side-car pattern as `ca-deckgen`
(E11.9). See §4.6.

---

## 4. PLAN — target architecture

### 4.1 Engagement identity

An **engagement** = `(customer, project)`. Slugged to
`^[a-z0-9][a-z0-9-]{1,40}$` per segment; the pair `<customer>/<project>` is the
**engagement id** used in every path, SQL filter and tool call. A collision appends
`-2`, `-3`. Display names are kept verbatim in `_engagement.json`.

**Target region is chosen by the end user, per engagement.** The New-engagement /
upload flow (§4.5) presents an Azure-region picker — **primary target region** (required)
and an optional **DR region** — and `_engagement.json` records them as
`target_region` / `dr_region` (Azure names, e.g. `swedencentral`). Every downstream step
reads them: `estimate_compute_cost` / `estimate_storage_cost` price in that region,
`design_landing_zone` builds the hub there and pairs the DR region, and the calculator
line-item spec (§4.6) sets `region_default` + each line's `region` so the **Pricing
Calculator POE is generated for the region the customer will actually deploy in**. The
region list is the calculator's own supported set (see §4.6 — `select[name=region]`
values), so a chosen region is always one the calculator can price. Changing the region
later re-runs the estimate + the POE.

`_engagement.json` shape:
`{customer, project, display, created_by, created_at, status, target_region, dr_region, currency, licensing_program, visibility, notes}`.

### 4.2 ADLS Gen2 layout (one deployment, HNS already on)

```
raw/
  engagements/<customer>/<project>/
    inventory/          client uploads — servers/apps/deps/perf/storage (CSV, RVTools .xlsx, CMDB export)
    docs/               narrative docs — compliance, network, DR, NFR
    _mapping.json       optional column-override (E1.7), per engagement
    _engagement.json    {customer, project, display, created_by, created_at, status,
                         target_region, dr_region, currency, licensing_program, visibility, notes}
answers/
  engagements/<customer>/<project>/
    _ingest/            data-quality reports, one per uploaded file
    estimate/           latest.json + latest.{xlsx,docx,pptx}  (+ studio.pptx from E11.9)
                        landing_zone.xlsx   the Azure Pricing Calculator's own export (POE artifact, E11.15+)
                        landing_zone.json   parsed totals + the line-item spec that produced it + calculator_url + created_at
                        landing_zone.png    screenshot of the estimate in the calculator (secondary evidence)
    history/<utc-ts>/    immutable snapshot of every publish (includes landing_zone.*)
```

Event Grid subject filter widens to
`/blobServices/default/containers/raw/blobs/engagements/` and the blob trigger path
becomes `raw/engagements/{customer}/{project}/inventory/{name}`.

### 4.3 SQL tenancy

- **`engagement_id NVARCHAR(120) NOT NULL`** added to `servers`, `applications`,
  `dependencies`, `storage`, `performance`, `ingest_log`; part of the natural key
  alongside `source_file`.
- Loader keys deletes on `(engagement_id, source_file)`.
- `query_inventory` gains a **required `engagement` argument**; the tool wraps the
  model's SQL as `SELECT * FROM (<model sql>) q` is *not* enough — instead it validates
  via `sqlguard`, then **appends / injects `WHERE engagement_id = @eng`** on every base
  table reference (belt-and-braces: the allow-list already blocks writes; this stops one
  engagement reading another's rows even if the model omits the filter).
- `--tier regulated`: a schema or database per engagement instead of a column.

### 4.4 The agent (`landfall-migration-estimator`)

- **System prompt** gains: *"Every request is scoped to one engagement, identified as
  `<customer>/<project>`. Pass the `engagement` argument to every tool call. Never
  combine or compare data across engagements. If the engagement is not given, ask for
  it."*
- **Every OpenAPI tool spec** gains a required `engagement` string parameter.
  `query_inventory`, `ingest`, `assemble_estimate`, `export_estimate`,
  `publish_estimate`, `design_landing_zone`, `score_dispositions`, `plan_waves`,
  `estimate_*` — all scope their SQL / blob I/O by it.
- `publish_estimate` writes to `answers/engagements/<c>/<p>/estimate/` and snapshots to
  `history/<ts>/`.

### 4.5 Dashboard (`src/web`) — what the user asked for

Route model: `/` = engagements home · `/e/<customer>/<project>` = one engagement.

1. **New engagement** — a form: *Customer name*, *Project name*, **Target region**
   (required — an Azure-region `<select>` populated from the calculator's supported set,
   §4.6), optional **DR region**, *Currency* (default USD), *Licensing program*
   (MCA / EA / MOSP / CSP, default MCA), *notes*. `POST /api/engagements` → web app (MSI)
   writes `_engagement.json` (incl. `target_region` / `dr_region` / `currency` /
   `licensing_program`) + creates the folder skeleton → redirects to `/e/<c>/<p>`. The
   Entra user id is recorded as `created_by`.
2. **Upload** — a drag-and-drop panel on the engagement page. The **Target region**
   (and DR region) picker sits **on this panel too**, pre-filled from `_engagement.json`
   and editable while uploading — the sponsor's ask is that the user sets where the
   landing zone will be deployed *at the point they upload the on-prem inventory*.
   Changing it here `PATCH`es `_engagement.json` and marks any existing estimate stale.
   Files `POST` to `/api/engagements/<c>/<p>/upload` (multipart); the web app streams each
   to `raw/engagements/<c>/<p>/inventory/` (or `/docs/` by a toggle). Server-side upload
   keeps auth server-side — no SAS handed to the browser. A manifest panel lists what's
   been uploaded, size, and detected source profile.
3. **Start analysis** — a button → `POST /api/engagements/<c>/<p>/run` → a new Function
   `run_engagement` ingests every file in the folder (detect → map → load, scoped by
   `engagement_id`), writes the DQ reports, then returns a status the page polls. A
   second button, *Produce estimate*, drives the agent through the full tool chain and
   `publish_estimate` for that engagement.
4. **Chat with prompt cards** — the chat UI embedded on the engagement page, every
   message carrying `engagement = <c>/<p>` in `extra_body`. A row of **predefined prompt
   cards**, each a one-click canned instruction:

   | Card | Sends to the agent |
   |---|---|
   | **Full estimate** | "Produce the full estimate for this engagement and publish it to the dashboard." |
   | **Landing zone** | "Design the Azure landing zone for this engagement and walk me through it." |
   | **Landing zone cost (Calculator POE)** | "Build the Azure Pricing Calculator estimate for this engagement's landing zone + target workloads and publish it to the dashboard." → E11.16 `ca-calc` container |
   | **Disposition & waves** | "Score the 6R dispositions and build the migration wave plan." |
   | **Run-rate cost** | "Break down the Azure run-rate cost with the top drivers and the range." |
   | **Client deck (PPT)** | "Assemble the estimate and generate the PowerPoint deck." |
   | **Excel workbook** | "Generate the Excel workbook with the calculation appendix." |
   | **Studio deck** | "Generate the studio-grade client deck." → E11.9 container tool |
   | **What's missing?** | "What data is missing or low-confidence, and what should I ask the client for?" |
   | **Explain a figure** | "Explain figure F… — where did it come from and under what assumptions?" |

   Cards are config (`src/web/prompt_cards.json`) so pre-sales can add their own.

   **Ask & export to Excel (E11.14).** A pre-sales architect asks any free-text question
   in the chat, gets the answer, and clicks **"Download as Excel"** on that answer. The
   chat client keeps the structured tool outputs behind the last response (a
   `query_inventory` result is `{columns, rows, sql}`; the cost / wave / disposition
   tools return structured JSON). "Download as Excel" `POST`s
   `{engagement, question, answer_text, tables:[{title, columns, rows}], provenance:[{tool, sql, run_at}]}`
   to a new Function `POST /api/answer_to_xlsx`, which builds a workbook — a **Question &
   answer** sheet, one sheet per returned table, and a **Provenance** sheet (the SQL /
   tool call, the engagement, timestamp, the DRAFT disclaimer) — and streams it back.
   Same openpyxl standards as E5.4q (formulas where derived, `$#,##0`, recalc-clean).

### 4.6 Azure Pricing Calculator estimate for POE (E11.15–E11.19)

The chain that turns a target-state design into the calculator's own Excel:

```
design_landing_zone  ─┐
estimate_compute_cost ─┼─►  src/api/lz/calculator_spec.py  ──►  calculator line-item spec (JSON)
estimate_storage_cost ─┘        target-state resources, SKUs, regions, quantities — NO prices
                                          │  POST /build_calculator_estimate  (engagement-scoped)
                                          ▼
   ca-calc   Container App · Playwright + Chromium · min-replicas 0
     1. open https://azure.microsoft.com/pricing/calculator/
     2. per line item:  add the product module  →  set fields (native setter + input/change)  →  await recompute
     3. set  estimate-name = "<Customer> — <Project> — Azure Landing Zone (POE)",  currency,  discountLevel (licensing program)
     4. click  button.export-button   →  capture  ExportedEstimate.xlsx
     5. re-parse the sheet  →  { line_items[], monthly_total, upfront_total, currency, created_at }
     6. screenshot the estimate
                                          │
                                          ▼
   answers/engagements/<c>/<p>/estimate/
     landing_zone.xlsx   the calculator's own file — the POE artifact, unmodified
     landing_zone.json   { spec, parsed, calculator_url, created_at, skipped[], internal_vs_poe_delta_pct }
     landing_zone.png
                                          │
                                          ▼
   dashboard card  "Azure landing zone — Pricing Calculator POE"
     $X / mo · $Y / yr · created <ts> · [ Download Excel (POE) ]  [ what's included ▾ ]
```

**The line-item spec** — the contract between Landfall and `ca-calc`:

```jsonc
{
  "engagement": "contoso/dc-exit",
  "estimate_name": "Contoso — DC Exit — Azure Landing Zone (POE)",
  "currency": "USD",
  "licensing_program": "MCA",              // MCA | EA | MOSP | CSP
  "region_default": "sweden-central",
  "line_items": [
    { "service": "virtual-machines", "region": "sweden-central",
      "config": { "operatingSystem":"windows", "tier":"standard", "size":"d4sv5",
                  "count":40, "hours":730, "osBillingOption":"ahb",
                  "computeBillingOption":"three-year" },
      "note": "prod Windows rehost — right-sized (internal figure F4)" },
    { "service": "managed-disks",  "config": { "tier":"prem-ssd", "size":"p20", "count":40 } },
    { "service": "vpn-gateway",    "config": { "tier":"vpngw1", "hours":730 } },
    { "service": "azure-firewall", "config": { "tier":"premium", "hours":730, "data-processed-gb": 4096 } },
    { "service": "azure-bastion",  "config": { "tier":"standard", "hours":730 } },
    { "service": "ddos-protection-plan", "config": { "plans":1 } },
    { "service": "azure-dns",      "config": { "zones":3, "queries-millions": 5 } },
    { "service": "azure-monitor",  "config": { "log-ingestion-gb": 90, "retention-months": 3 } },
    { "service": "key-vault",      "config": { "operations-10k": 20 } },
    { "service": "bandwidth",      "config": { "outbound-data-transfer-gb": 2048 } },
    { "service": "storage-accounts", "config": { "type":"files-premium", "capacity-gb": 8192 } },
    { "service": "sql-managed-instance", "config": { "tier":"general-purpose", "vcores":8, "storage-gb":512 } },
    { "service": "backup",         "config": { "instances":40, "avg-instance-gb": 200 } }
  ]
}
```

**Product coverage v1 (~16 modules)** — the finite set a landing zone + lift-and-shift
needs: `virtual-machines`, `managed-disks`, `storage-accounts`, `bandwidth`,
`vpn-gateway`, `expressroute`, `azure-firewall`, `azure-bastion`,
`ddos-protection-plan`, `azure-dns` (+ Private DNS), `azure-monitor` (Log Analytics),
`key-vault`, `load-balancer`, `application-gateway`, `sql-database`,
`sql-managed-instance`, `backup`. Each is a small **adapter**:
`add()` + `field_map` + `wait_for_recompute()`, in a registry so one product breaking
never blocks the rest.

**Robustness & honesty**
- A **weekly CI Playwright smoke** opens the calculator and asserts every adapter's
  selectors still resolve; a broken adapter drops its line item into `skipped[]` with a
  visible note rather than mispricing it.
- `landing_zone.json` records the full spec, the parsed export, `calculator_url` and
  `created_at` — the POE figure is traceable end to end.
- Landfall never invents a price, never edits the calculator's Excel, and never claims a
  number the calculator didn't produce. `internal_vs_poe_delta_pct` compares the
  calculator total against Landfall's own run-rate; a delta over a threshold is surfaced
  on the dashboard for the architect to reconcile before submitting.

**Login / Save (deferred — E11.19).** A live shareable estimate link is the strongest
POE but needs an authenticated calculator session (service Microsoft account, Key Vault
secret, MFA). Phase 1 ships the **anonymous Excel export** (accepted for Excel-based POE
review); authenticated Save → `landing_zone_url` is added when a specific funding program
demands the live link.

### 4.7 Studio-deck container (E11.9 — makes E5.6 concrete)

A small **Container App** (`ca-deckgen`) running Node + `presentation-skill` +
`ppt-master` + LibreOffice/Poppler. One OpenAPI operation:
`POST /generate_studio_deck { engagement, style? }` → pulls
`answers/engagements/<c>/<p>/estimate/latest.json`, authors `outline.json`, renders via
pptxgenjs, runs `qa_gate.py`, writes `estimate/studio.pptx` back, returns the blob path.
Registered as an agent tool. min-replicas 0 (scale-to-zero — it runs seconds per deck).

`ca-calc` (§4.6) is the **second** side-car on this pattern — a browser/Node runtime the
Function can't host, behind one OpenAPI operation, scale-to-zero. If a third appears,
factor the shared Dockerfile base + blob-IO helper + OpenAPI-tool Bicep into a template.

### 4.8 Security & isolation

- Web app + Function stay behind Entra (EasyAuth, cycle 16). `_engagement.json.created_by`
  + an optional `visibility: {owner | group:<id> | all}`; the engagements list filters by
  it.
- **Path-traversal:** slug regex enforced server-side on every route and tool arg; reject
  `.` / `/` / `..` in a segment.
- ADLS: per-engagement folders under one container for v1; **POSIX ACLs per folder**
  (ADLS Gen2) for `--tier regulated`, set at `create_engagement` time.
- Every `run` / `publish` writes an audit line (`answers/.../history/` + App Insights):
  who, when, which tools, which figures.
- Data residency unchanged — all in the deployment's region; `_engagement.json.region`
  is an *estimate* input, not a data-placement control.

---

## 5. Work breakdown — Epic E11: Engagement Workspaces

| # | Item | P | Acceptance |
|---|---|---|---|
| **E11.1** | Engagement model + provisioning — slug rules, `_engagement.json`, `POST /api/engagements`, `GET /api/engagements` (list, filtered by `created_by`/visibility) | P0 | Creating "Contoso / DC-Exit" makes `raw/engagements/contoso/dc-exit/…` + `answers/…` and returns the id; a second "Contoso / DC-Exit" becomes `dc-exit-2` |
| **E11.2** | Per-engagement ADLS layout for `raw/` + `answers/`; Event Grid subject filter + blob-trigger path updated | P0 | A file dropped under one engagement never triggers ingestion for another |
| **E11.3** | SQL tenancy — `engagement_id` on all 6 tables, loader keying, `apply_sql.py` migration (idempotent, additive) | P0 | Two engagements' rows coexist; `SELECT` without the filter is impossible from `query_inventory` |
| **E11.4** | Ingestion scoped by engagement — `POST /api/ingest` + `run_engagement` take `engagement`; blob trigger derives it from the path | P0 | `run_engagement` ingests only that folder; DQ reports land under that engagement |
| **E11.5** | `engagement` is a **required argument on every OpenAPI tool** + the agent system prompt; `query_inventory` injects `WHERE engagement_id` | P0 | A tool call without `engagement` returns 400; the agent always supplies it; cross-engagement read returns nothing |
| **E11.6** | Dashboard — engagements home, "New engagement" form (**incl. Target region + DR region + currency + licensing-program pickers**), upload panel (**with the region picker repeated, editable at upload time**), "Start analysis" / "Produce estimate" | P0 | A pre-sales user with no CLI creates an engagement, **picks the target Azure region**, uploads RVTools + a CMDB CSV, clicks Start, and sees a data-quality summary — in one session; the region is persisted to `_engagement.json` and flows into the estimate + the POE |
| **E11.7** | Dashboard — embedded engagement-scoped chat + configurable prompt cards (`prompt_cards.json`) | P0 | Clicking "Full estimate" produces and publishes the estimate for the open engagement and only that engagement |
| **E11.8** | `publish_estimate` + dashboard read/write the engagement path; `history/<ts>/` snapshots; a version picker on the dashboard | P1 | Re-publishing keeps the prior version; the dashboard can show any snapshot |
| **E11.9** | Studio-deck container (`ca-deckgen`) — `presentation-skill` + `ppt-master` as an OpenAPI tool; "Studio deck" prompt card | P1 | The agent calls it; a `qa_gate`-passing `studio.pptx` lands in the engagement folder |
| **E11.10** | Access control — `visibility` on `_engagement.json`, list filtering, audit trail of runs/publishes | P1 | A user sees only their own + group-shared engagements; every run is attributable |
| **E11.11** | Migration + back-compat — fold the current single-tenant `raw/inventory/` + `answers/estimate/latest.*` + un-keyed SQL into `_default_/_default_` (or drop, synthetic); one-release shim | P1 | Existing deploy keeps working through the transition; docs updated |
| **E11.12** | E5.4q — `.xlsx` formulas-not-literals + a headless-LibreOffice recalc **CI gate**; `.docx` US-Letter DXA + tracked-changes-ready + `accept_changes` | P1 | Change an input in the workbook → the model re-flows; recalc reports 0 errors; architect edits are Word tracked changes |
| **E11.13** | Evals — golden per-engagement isolation tests (two synthetic estates, assert no bleed); a `run_engagement` end-to-end scenario in the harness | P0 | A regression that leaks one engagement's rows into another fails CI |
| **E11.14** | **Ask & export to Excel** — `POST /api/answer_to_xlsx` (Question&answer + a sheet per table + Provenance), and a "Download as Excel" affordance on chat answers that carry tabular tool output | P0 | An architect asks "how many prod Windows servers and their vCPU?", gets the answer, and downloads a workbook with the rows + the SQL + the engagement + a DRAFT note |
| **E11.15** | `src/api/lz/calculator_spec.py` — turn `design_landing_zone` + `estimate_compute_cost` + `estimate_storage_cost` output into a **calculator line-item spec** (§4.6), **using the engagement's `target_region` / `dr_region`** for `region_default` and every line's `region`. Region-name→calculator-code map (Azure name → `select[name=region]` value), VM-SKU→size-slug map, disk-tier→option map, LZ-platform-component→module map. Pure, fully unit-tested. | P0 | The sample estate + a chosen region produce a spec priced **in that region** with VMs (right-sized, per env, AHB/RI as configured), managed disks, hub networking (VNet/GW/Firewall/Bastion/DDoS/DNS), Log Analytics, Key Vault, egress bandwidth, backup — every item mapping to a real calculator module + field set; an unsupported region is rejected at engagement-create time |
| **E11.16** | **`ca-calc` Container App** — Playwright + Chromium image; `POST /build_calculator_estimate` (engagement-scoped); product-adapter registry (~16 modules); drives the real calculator, sets estimate-name/currency/licensing, clicks Export, captures `ExportedEstimate.xlsx`, re-parses it, screenshots, writes `landing_zone.{xlsx,json,png}` to the engagement folder. Bicep + ACR image + OpenAPI-tool env var. min-replicas 0. | P0 | Given a spec, a genuine calculator `.xlsx` (sheet `Your Estimate`, `Total` row, `created at` line) lands at `answers/engagements/<c>/<p>/estimate/landing_zone.xlsx`; `landing_zone.json` carries the spec + parsed totals + `calculator_url` + `internal_vs_poe_delta_pct` + any `skipped[]` |
| **E11.17** | Dashboard — **"Azure landing zone — Pricing Calculator POE"** card ($X/mo · $Y/yr · created `<ts>`, "what's included" drawer, `internal_vs_poe` delta flag); `GET /dashboard/download/landing-zone-xlsx?e=<eid>` streams `landing_zone.xlsx`; `landing_zone.json` read path with the same fallback chain as `latest.json` | P0 | Opening the dashboard for an engagement shows the calculator monthly total and a working **Download Excel (POE)** button; the file is byte-identical to what `ca-calc` stored |
| **E11.18** | Agent wiring — `build_calculator_estimate` OpenAPI tool (required `engagement`), system-prompt line, the **"Landing zone cost (Calculator POE)"** prompt card; optional `run_engagement` hook after `publish_estimate` | P0 | The card / a chat instruction makes the agent call the container for the open engagement and only that engagement; the dashboard card refreshes |
| **E11.19** | CI **weekly Playwright calculator-adapter smoke** (open the calculator, assert every adapter's selectors resolve, one tiny end-to-end export); **(deferred)** authenticated Save → shared estimate link stored as `landing_zone_url` | P1 | A calculator UI change that breaks an adapter fails the weekly job with the adapter named; a broken adapter degrades to `skipped[]`, never a wrong price |

**Infra deltas (`infra/resources.bicep`):** Event Grid subject filter; a `ca-deckgen`
Container App (E11.9) and a **`ca-calc` Container App** (E11.16, Playwright/Chromium
image) + their ACR images + OpenAPI-tool env vars; no new data stores for v1.

**Not in scope here:** changing the estimation maths, the CAF landing-zone logic, or the
eval-harness gates — E11 is plumbing + UX + tenancy around the existing engine. The
Pricing Calculator work (E11.15–E11.19) **translates** the existing design + cost output
into calculator instructions and captures the calculator's answer; it does not re-derive
sizing or prices.

---

## 6. PDCA cadence

| Cycle | Scope | Exit |
|---|---|---|
| **C18** | E11.1 + E11.2 + E11.3 (engagement model, ADLS layout, SQL `engagement_id` + migration) | `create_engagement` works; two engagements' data is isolated in SQL and blob; tests |
| **C19** | E11.4 + E11.5 + E11.13 (ingestion + every tool scoped; isolation evals) | `run_engagement` ingests one folder; every tool rejects a missing `engagement`; isolation eval green |
| **C20** | E11.6 (dashboard: home, new-engagement, upload, start analysis) | A no-CLI user creates an engagement, uploads, and runs analysis from the browser |
| **C21** | E11.7 + E11.8 + E11.14 (engagement-scoped chat + prompt cards + "ask & export to Excel"; versioned publish) | Prompt cards drive per-engagement outcomes; an architect downloads any chat answer as a workbook; dashboard shows the right engagement's estimate |
| **C22** | E11.9 + E11.12 (studio-deck container; xlsx/docx polish + CI recalc gate) | "Studio deck" card produces a `qa_gate`-passing deck; recalc gate live |
| **C23** | E11.10 + E11.11 (access control, audit, migration + shim, docs) | Visibility enforced; the old single-tenant deploy migrates cleanly |
| **C24** | E11.15 + E11.16 (calculator line-item spec builder; `ca-calc` container end-to-end) | The sample estate's spec → the real Azure Pricing Calculator → a genuine `ExportedEstimate.xlsx` lands in the engagement's `estimate/` folder |
| **C25** | E11.17 + E11.18 + E11.19 (dashboard POE card + download; agent tool + prompt card; weekly adapter smoke) | A pre-sales user opens an engagement, clicks "Landing zone cost (Calculator POE)", and downloads the calculator's own Excel for a Microsoft funding submission |

Each cycle logged in [`pdca-log.md`](pdca-log.md) (Plan / Do / Check / Act).

---

## 7. Sponsor decisions (2026-09-08)

1. **Isolation tier — `engagement_id` column** on one Free-tier DB, enforced by **SQL
   Server Row-Level Security** (a filter predicate + `SECURITY POLICY` on all 6 tables;
   `query_inventory` sets `sp_set_session_context 'engagement_id'` before running the
   model's SQL, so free-form text-to-SQL physically cannot see another engagement's rows).
   DB/schema-per-engagement stays a `--tier regulated` switch for later.
2. **Access — creator + optional group share.** `_engagement.json` records `created_by`
   (Entra user) and `visibility: {owner | group:<id> | all}`; the engagements list
   filters by it (E11.10).
3. **Retention** — documented manual close-out; every publish keeps a `history/<ts>/`
   snapshot. (unchanged from the plan)
4. **Studio deck (`ca-deckgen`) — deferred.** The rebuilt in-Function `python-pptx` deck
   is the default; add the Node side-car in a later cycle when a client needs it. E11.9
   moves to backlog.
5. **POE = Azure Pricing Calculator export, mandatory (2026-09-08).** Microsoft
   migration-funding submissions accept the calculator's own Excel (and/or a shared
   estimate link), not an API-derived number. Landfall drives the real calculator via a
   scale-to-zero Playwright container (`ca-calc`) and stores its `ExportedEstimate.xlsx`
   per engagement; the internal cost tools remain the working estimate and are
   reconciled against the POE (`internal_vs_poe_delta_pct`). Anonymous export ships
   first; authenticated Save → shared link is E11.19 (deferred). New work E11.15–E11.19,
   PDCA C24–C25. See §3.4 + §4.6.
6. **Target region is an end-user choice, set at upload time (2026-09-08).** The
   New-engagement and upload panels carry an Azure-region picker (primary + optional DR)
   from the calculator's supported set; `_engagement.json.target_region` /
   `dr_region` flow into `estimate_*`, `design_landing_zone` and the calculator spec so
   the estimate + POE are for the region the customer will deploy in. Folded into E11.6
   (form) and E11.15 (spec builder reads it).

**Build order:** C18 done (E11.1–E11.3, live). Continue C19 → C25 in order; C24–C25 (the
Pricing Calculator POE) can run in parallel with C20–C21 since `ca-calc` is independent
of the dashboard-UX cycles — sequence by reviewer availability.
