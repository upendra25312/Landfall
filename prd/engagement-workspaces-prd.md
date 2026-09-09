# Landfall — Engagement Workspaces (multi-client, dashboard-driven)

**Status:** IN PROGRESS (C18/C24/C25/C25b/C26 done & live — POE pipeline, upload panel,
per-engagement conversation memory + export/import deployed; **C25b** rebuilt the
calculator adapters from the live DOM + weekly smoke — full 55-line POE run verified live,
reconciliation −73% → +27.9% (calc list vs internal RI/AHB); **C19** done & live
(`run_engagement` bulk-ingest + hard engagement scoping); **C20** core done
(Start analysis + data-quality summary; E11.25 questionnaire → C20b); **C21** done
(versioned publish + engagement-aware dashboard + ask-&-export to Excel); **C22** done
(live-model workbook + LibreOffice recalc CI gate; E11.9 deck-container deferred); C23 + C27–C28 planned) ·
**Raised:** 2026-09-08 · **Last updated:** 2026-09-09 · **Owner panel:** see below · **Method:** PDCA
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
>    *(added 2026-09-08)*;
> 7. get a **target Azure landing-zone architecture diagram** for the engagement's chosen
>    region, on the dashboard and in the deck *(added 2026-09-08)*.
>
> Questions: can we use the `docx`, `xlsx`, `presentation-skill`, `ppt-master` and
> `drawio-mcp-diagramming` skills **at the Foundry agent**? And how does the user get the
> `<customer>/<project>` engagement id?

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
| **UX / Practice Director** | chat-page information architecture, engagement-first layout, the §4.9 findings |
| **Full-stack Web Engineer** | `src/web` implementation — picker, prompt cards, Markdown rendering, the engagement rail |
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
| [Azure **ALZ / AI-LZ design checklist**](https://azure.github.io/AI-Landing-Zones/architecture/design-checklist/) | **Design reference** for `design_landing_zone`: the 10 domains + each item; the AI-LZ specifics (Foundry hub/project, private AI Search + Content Safety, APIM gen-AI gateway, PTU+PAYG, Responsible-AI dashboard). | Vendored to `docs/lz-design/`; `design.py` emits `checklist_conformance[]` (met/partial/gap + evidence + recommendation) + an AI-LZ overlay when the estate has AI/ML workloads; deliverable + dashboard + agent surface it. *(E11.23, §4.11)* |
| [`drawio-mcp-diagramming`](https://github.com/thomast1906/github-copilot-agent-skills/tree/main/.github/skills/drawio-mcp-diagramming) | **Rules** (`xml-authoring-rules`, `azure.md` — palette, swimlane nesting, cross-container edges, `search_shapes`-first, no hand-routed edges) coded into `src/api/lz/diagram.py`; its **engine** (`simonkurtz-MSFT/drawio-mcp-server` — HTTP, browserless, 700+ offline Azure icons) deployed as the `ca-drawio` Container App. | `build_landing_zone_diagram` Function replays a deterministic MCP-call plan against `ca-drawio`; `.drawio → .svg/.png` render in the same container. Agent calls one OpenAPI tool, does **not** free-draw. *(E11.22, §4.10)* |

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

### 3.5 Where the engagement id comes from — the end user never types it

**Problem raised (2026-09-08):** users kept being asked by the agent for an
`<customer>/<project>` id they had no way to know, and "hard to remember" is a fair
complaint — a slug is an implementation detail, not something a pre-sales architect
should carry in their head.

**Principle:** the engagement id is **always** `slug(customer)/slug(project)`, and it is
computed by **one function** — `engagement.make_engagement_id()`
(`re.sub(r"[^a-z0-9]+","-", v.lower()).strip("-")[:40]` per segment) — shared verbatim by
the dashboard, the API, the SQL row filter and the ADLS folder layout. Because there is
exactly one slugging rule, the id the UI computes is **byte-identical** to the folder the
inventory was uploaded into and the `engagement_id` on the SQL rows. The user supplies
**names**; the id is derived, never entered.

Two entry paths, both deployed as of 2026-09-08 (`458d400`):

| Path | How the id is set | Component |
|---|---|---|
| **Dashboard (primary)** | The chat header carries an **engagement `<select>`** (populated from `GET /api/engagements`) and a **"＋ New engagement"** inline form (Customer, Project, Target region, DR, licensing, currency). Creating one provisions the folders and auto-selects it; the choice is kept in `localStorage` (`landfall.eng`). Every chat message and prompt-card click sends `engagement=<id>` in the body; `/api/chat` prepends `[Active engagement: <id>. Use exactly this value …]` to the agent input. **The user picks or types names — never the slug.** | `src/web/app.py` `GET`/`POST /api/engagements`, `GET /api/calc_regions`; `src/web/index()` header + `#engform` |
| **Agent (fallback / conversational)** | If no `[Active engagement: …]` bracket is present and the user names a customer + project in chat, the agent calls **`resolve_engagement`** (`customer`, `project` → canonical id). It fuzzy-matches on slug-token overlap against every `_engagement.json`, so "contoso" / "dc exit" still finds `contoso-ltd/dc-exit-2027` and returns it as a `candidates[]` entry with a `match_score`. The agent confirms the match with the user; on a confirmed new engagement it calls again with `create: true` to provision the skeleton. The system prompt **forbids the agent from inventing a slug**. | `src/api/engagements.py` `resolve_engagement`; `src/api/openapi/resolve_engagement.json`; `scripts/create_agent.py` system prompt + tool list |

**Net effect:** the only thing a user ever names is the customer and the project (as
free text). The slug, the folder, the SQL scope and the POE file path are all the same
derived string, computed once.

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
2. **Upload** — a drag-and-drop panel on the engagement page (**E11.6 — not built yet**;
   today the chat page only has "+ New engagement", no upload). The **Target region**
   (and DR region) picker sits **on this panel too**, pre-filled from `_engagement.json`
   and editable while uploading — the sponsor's ask is that the user sets where the
   landing zone will be deployed *at the point they upload the on-prem inventory*.
   Changing it here `PATCH`es `_engagement.json` and marks any existing estimate stale.
   Files `POST` to `/api/engagements/<c>/<p>/upload` (multipart); the web app (its MSI)
   streams each to `raw/engagements/<c>/<p>/inventory/` (data) or `/docs/` (narrative), a
   per-file toggle. **No SAS to the browser** — the upload is server-side. See §4.5a for
   accepted types, size caps, folder isolation and the upload-confirmation UX.
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

### 4.5a Upload — accepted files, size, folder isolation, confirmation (E11.6 + E11.24)

**Where the user uploads (today vs target).** *Today:* the chat page has only
**"+ New engagement"**, which creates the customer/project and its ADLS skeleton — there
is **no upload control yet**. *Target (E11.6):* on the engagement page, an **Upload**
panel directly under the engagement header: drag-and-drop or file-picker, a
**Data / Documents** toggle, the region pickers, and a live file manifest.

**How a customer's files reach their own dedicated folder.** The engagement id is
`slug(customer)/slug(project)` (§3.5) — one function, shared by UI, API, SQL and ADLS.
The upload route is `POST /api/engagements/<customer>/<project>/upload`; the web app
resolves that pair through the **same** `make_engagement_id()`, checks the caller may
write to it (`created_by` / `visibility`, §4.8), and streams each file to
**`raw/engagements/<customer>/<project>/inventory/<filename>`** (or `/docs/`). The
customer/project segments are slug-validated on every request (`^[a-z0-9][a-z0-9-]{0,39}$`,
reject `.` `/` `..`), so a file physically cannot be written outside that engagement's
prefix. Filenames are sanitised (basename only, collision-suffixed). The blob path *is*
the isolation boundary — Event Grid's subject filter and the loader's `engagement_id`
key both derive from it, and SQL Row-Level Security (§7.1) fails closed on it.

**Inputs vs outputs are separate containers, already.** Inputs → `raw/…`; everything the
solution produces for that same customer/project → **`answers/engagements/<customer>/<project>/`**
— `estimate/` (`latest.{json,xlsx,docx,pptx}`, `landing_zone.{xlsx,json,png}`),
`_ingest/` (data-quality reports), `history/<utc-ts>/` (immutable publish snapshots).
The dashboard's **Downloads** section and the agent's `publish_estimate` /
`build_calculator_estimate` only ever read/write under that `answers/…/` prefix. `raw` is
never written by the generation path; `answers` is never the upload target.

**Accepted file types (expert-panel recommendation).** The importer already fingerprints
RVTools / CMDB / native-schema content, so accept the formats those actually arrive in:

| Group | Types | Lands in | Notes |
|---|---|---|---|
| **Inventory data** (required) | `.csv`, `.xlsx` (`.xls` converted), `.tsv`, `.json` | `inventory/` | RVTools export, Azure Migrate assessment export, CMDB/ServiceNow extract, `az`/`Get-VM` dumps, hand-filled templates |
| **Inventory data** (nice-to-have) | `.zip` of the above | `inventory/` | server-side unzip, each member validated; RVTools is often zipped |
| **Narrative / evidence** | `.pdf`, `.docx`, `.md`, `.txt`, `.png` / `.jpg` (diagrams) | `docs/` | network diagrams, DR runbooks, compliance scope, NFRs, the filled discovery questionnaire (§4.5b) |
| **Rejected** | executables, archives other than `.zip`, Office files with macros (`.xlsm`/`.docm`), anything > the size cap | — | 415 with the reason; macro-Office is re-saved by the user as `.xlsx`/`.docx` |

Validation is **content-sniffed, not extension-trusted** (magic bytes + a structural
probe: a "data" file must parse as a table with ≥1 recognised column; a `.pdf` must start
`%PDF`). A file that passes type-check but matches no importer profile is still stored and
listed as **"unrecognised — will be skipped by analysis"** rather than rejected.

**Size limits.** Per file **100 MB** (RVTools for ~10k VMs is < 20 MB; this is generous),
per upload request **250 MB**, per engagement **2 GB** soft cap (dashboard warns, support
can raise). Enforced at three points: an HTML `accept` + client-side pre-check for instant
feedback, a `Content-Length` gate on the route (413 before the body is read), and a
hard byte-ceiling on the stream copy. Uploads are **streamed** to blob in 4 MB blocks —
never buffered whole in the web container (which has ~1 GB RAM).

**Visual confirmation of upload (E11.24 — the sponsor's explicit ask).** Each file shows
its own row with a state that changes as it goes:

```
  network-inventory.xlsx    ⟳ uploading… 40%        (determinate bar from the fetch upload-progress)
  network-inventory.xlsx    · 152 KB · checking…      (server validating type + profile)
  network-inventory.xlsx    ✓ uploaded · RVTools vInfo · 412 rows        [remove]
  macro-sheet.xlsm          ✗ not accepted — re-save as .xlsx           [dismiss]
```

- Optimistic row appears the instant a file is chosen; a determinate progress bar tracks
  the actual PUT.
- On the server's `201` the row flips to **✓ uploaded** with a green check, the detected
  **source profile** and **row/record count**, and a toast *"network-inventory.xlsx added
  to Contoso / DC-Exit"*.
- The **manifest panel** (persisted — it re-lists `raw/…/inventory/` + `/docs/` on load)
  is the durable proof: filename, size, uploaded-at, uploader, detected profile, and an
  **"analysis will use this / will skip this"** badge.
- After **Start analysis**, each manifest row gains an ingest badge (rows loaded, DQ
  findings) linking to that file's `_ingest/` report — so "did my file land and get
  used?" is answerable at a glance.

### 4.5b Discovery questionnaire — delivered through the solution (E11.25)

`docs/discovery-questionnaire.html` is currently a static file with no route. Make it
first-class in the pre-sales flow:

1. **Serve it** at `GET /questionnaire` (also linked from the engagement page and the
   chat welcome card) — a pre-sales architect sends the client that URL, or exports it.
2. **Export to fill offline** — a button renders the questionnaire to **`.docx`** and
   **`.xlsx`** (the same `export.py` toolchain) so the client can complete it in Word /
   Excel and email it back.
3. **Upload the answers** — the completed questionnaire (`.docx` / `.xlsx` / `.pdf`) goes
   through the **same upload panel** into `docs/`; the importer recognises the
   questionnaire template and writes the structured answers to
   `raw/engagements/<c>/<p>/_discovery.json`.
4. **Feed the estimate** — `_discovery.json` supplies the assumptions the inventory can't:
   compliance scope, DR RTO/RPO, licensing program, growth, change-freeze windows,
   internet-facing lists, data-residency constraints. `assemble_estimate` reads it into
   the assumptions register (each answer cited), and `design_landing_zone` uses the
   compliance + DR answers instead of its defaults.
5. **Gap list** — unanswered questions surface on the dashboard as
   *"Ask the client: …"* and in the agent's **"What's missing?"** card.

New work: **E11.24** (upload confirmation UX — folds into E11.6), **E11.25** (questionnaire
as a served + round-trippable artifact). PDCA: with **C20** (E11.6) and **C21**.

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

**Execution model — MUST be async (finding, C25 2026-09-08).** Driving ~55 calculator
line items through Playwright takes **many minutes**; a synchronous
`Function → ca-calc → wait` call **fails** — Azure Functions' HTTP front end cuts the
response at ~230 s and returns **502** to the Foundry OpenAPI tool (observed live: agent
called `build_calculator_estimate` correctly, Function 502'd while `ca-calc` was still
cold-starting + driving). So E11.16 is **fire-and-forget + poll**:
- `build_calculator_estimate` writes `landing_zone.json` with `{"status":"building",
  "started_at":…}`, kicks `ca-calc` **asynchronously** (a queue message, or an
  un-awaited request with a short connect timeout), and returns **202** immediately with
  a `poll` hint.
- **`ca-calc` itself writes the outputs** — on success it uploads
  `landing_zone.{xlsx,json,png}` (status `ready`) straight to the engagement's
  `estimate/` prefix using its own managed identity; on failure it writes
  `landing_zone.json` status `failed` + the error. (`ca-calc` gets **Storage Blob Data
  Contributor** on the answers container.)
- The agent tool description tells the agent the POE builds in the background and to
  tell the user to watch the dashboard card; the dashboard card polls
  `GET /dashboard/landing-zone` and shows `building / ready / failed`.
- A `GET /build_calculator_estimate?engagement=…` status route returns the current
  `landing_zone.json` for the agent / dashboard to poll.

**Robustness & honesty**
- A **weekly CI Playwright smoke** (`src/calc/smoke.py`, `.github/workflows/calc-adapter-smoke.yml`)
  adds every adapter's product to a real estimate and applies its fields; a broken
  *verified* adapter fails the job with the control named, and at run time drops its line
  item into `skipped[]` / `fields_not_set[]` rather than mispricing it.
- Adapter controls that **rename per tier / OS** are the recurring drift: Linux VM modules
  take a *distro* `type` (not `os-only`) and render no Azure-Hybrid-Benefit radio; Azure
  NetApp Files and premium (SSD) Azure Files prefix their capacity controls with the tier
  (`premiumUnits`, `ssdProvisionedV2StorageUnits`). `tests/test_calc_adapters.py` locks these
  offline; the live smoke re-checks. `azure-bastion` / `azure-monitor` / `load-balancer` /
  `application-gateway` stay `verified: False` and degrade to calculator defaults.
- **`ca-calc` runs one always-on replica** (`minReplicas 1`, `worker.py consume_forever()`
  draining `calc-jobs`) at **2 vCPU / 4 GiB** — Chromium's renderer OOM-crashed rendering a
  full-page screenshot of a 50+ module estimate at 2 GiB. `driver.build_estimate` now exports
  the xlsx (the POE) **before** the screenshot and the screenshot is viewport-only + best-effort,
  so a renderer crash can never fail a completed run. True scale-to-zero was tried in C25b — a
  KEDA `azure-queue` rule with workload-identity auth (`identity: uami.id`, no account key) —
  but KEDA never scaled the replica up on a queued job (the scaler's MI-auth path isn't wired
  through in this Container Apps / KEDA version), so it was reverted; the queue rule stays only
  to burst to 2 under load. Real scale-to-zero needs the worker to hold the queue metric > 0
  while it drives the calculator, or a different trigger.
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

### 4.9 Chat UX — expert-panel findings + the engagement-first redesign

The chat page (`src/web/index()`) got the engagement picker, prompt cards, an agent
greeting and a "the estimator is working" indicator in C24 (`1003f55`, `458d400`). A
panel review (AI architect / Python / pre-sales / cloud architect / practice director /
UX / full-stack) found the page is still **chat-first with an engagement bolted on**, and
the real fix is an engagement-first layout (E11.21):

| # | Finding | Severity | Fix | Item |
|---|---|---|---|---|
| 1 | **No engagement context on screen** — you can't tell which client you're working on; the picker is one small `<select>` in a crowded header | High | Persistent engagement rail with the active customer/project shown as a title, not a dropdown value | E11.21 |
| 2 | Agent still asks for "customer/project name" as free text when no engagement is active — brittle, undiscoverable | High | `resolve_engagement` + picker (done, §3.5); rail makes "no engagement selected" a blocking empty-state, not a chat message | E11.20 / E11.21 |
| 3 | **Prompt cards + greeting vanish after the first message** and never come back; huge dark dead-space either side of a narrow chat column | Med | Cards live in the rail / a collapsible tray, always reachable; chat column widened; dashboard content shares the view | E11.21 |
| 4 | **Agent answers render as `white-space: pre-wrap` plain text** — tables, bullet lists, headings and code from the agent look broken | High | Render assistant messages as Markdown (small, dependency-light renderer; tables + code + lists) | E11.21 |
| 5 | No per-message affordances — no copy button, no "which tools ran", no timestamp, no way to re-run | Med | Message toolbar: copy, expand tool calls, "download this answer as Excel" (E11.14) inline | E11.21 / E11.14 |
| 6 | Chat and `/dashboard` are **disconnected** — the dashboard isn't engagement-scoped and opens in a new page with no shared state | High | Thread `?e=<eid>` through every dashboard route + link; ideally the dashboard is a tab of the engagement view | E11.17 / E11.21 |
| 7 | Header wraps badly on a narrow viewport — engagement `<select>` + "＋ New engagement" + "＋ New chat" + dashboard link on one line, no responsive treatment | Med | Move engagement + "new" actions into the rail; header keeps only chat-session actions | E11.21 |
| 8 | **No visibility of engagement state** — has inventory been uploaded? has analysis run? is an estimate published? is the POE built? | High | Engagement status strip in the rail: Uploads · Analysis · Published estimate · Calculator POE, each with a state chip and a link | E11.21 |
| 9 | Errors dead-end at `Error: …` in a chat bubble with no retry and no detail | Med | Inline error card with a Retry action and an expandable detail | E11.21 |
| 10 | Two adjacent "＋ New…" actions ("New engagement" vs "New chat") are easy to confuse | Low | Separate by placement (engagement action in the rail, chat action in the header) + distinct icons | E11.21 |

**Recommendation (panel consensus):** stop patching the header. Ship **E11.21 — an
engagement-first chat view**: a left rail with the active engagement (customer / project
as a heading), its status strip (§ finding 8), the region + licensing summary, and the
prompt cards / "new engagement" action; the chat thread and a dashboard tab share the
main pane, both scoped to the rail's engagement; Markdown-rendered answers; per-message
toolbar. The current single-page chat becomes the "no engagement selected" empty state
that routes the user into pick-or-create. This is a C26 build — **do not start it without
sponsor sign-off** given the volume of C24 changes still settling.

### 4.10 Target landing-zone diagram — `drawio-mcp-diagramming` in Azure (E11.22)

**Ask (2026-09-08):** use the
[`drawio-mcp-diagramming`](https://github.com/thomast1906/github-copilot-agent-skills/tree/main/.github/skills/drawio-mcp-diagramming)
skill inside Microsoft Foundry / Azure to draw the target Azure landing-zone diagram.

**The SKILL.md file cannot load into a Foundry agent** (no skill loader — §3.1); it is
instructions + reference docs + a `drawio/search_shapes`-first workflow a *coding* agent
runs. **But the skill's *engine* is deployable in Azure**, and that is what we use.

**The three "draw.io MCP" projects are not equivalent** — only one works server-side:

| Server | Transport | Browser? | Azure icons | Fit |
|---|---|---|---|---|
| `jgraph/drawio-mcp` (Tool Server) | stdio only | **yes** — signals a live draw.io tab | via search | unusable server-side |
| `lgazo/drawio-mcp-server` | stdio; operates on a **connected draw.io browser tab** | **yes** | via search | unusable server-side |
| **`simonkurtz-MSFT/drawio-mcp-server`** | **stdio + streamable HTTP** (`/mcp`, :8080) | **no** — stateless XML generator | **700+ official Azure icons, embedded, fully offline** | **✅ deployable** — ~20 MB distroless image, non-root, Docker Hub `simonkurtzmsft/drawio-mcp-server` |

Foundry Agent Service **does support remote / custom MCP servers as agent tools** (out of
preview during 2026; the Azure DevOps remote MCP server is the reference). So the engine
can attach to `landfall-migration-estimator`. **We still do not let the agent free-draw**
— a 40-node landing zone authored through dozens of MCP round-trips is slow, token-heavy
and non-repeatable, unacceptable on a funding artifact.

**Design — hybrid: a deterministic driver over the real MCP engine.**

```
design_landing_zone  (JSON: hub VNet, spoke VNets, subnets, shared svcs, ER/VPN, DR pair)
        │
        ▼
build_landing_zone_diagram          ← ONE OpenAPI tool the agent calls (like build_calculator_estimate)
  Function · deterministic mapping in src/api/lz/diagram.py — NOT agent reasoning:
    • hub / spoke VNets, subnets        → MCP  create-group      (swimlane containers, startSize=24)
    • each component (Firewall, Bastion, GW, KV, Log Analytics, AD DC, VMs …)
                                        → MCP  browse-azure-icons + add-cell-of-shape
    • peerings, ExpressRoute/VPN, DR     → MCP  add-edge          (colours per skill: #0078D4 / #00897B / …)
    • layout                            → MCP  routing: libavoid  (no hand-written waypoints)
    • MCP  export-xml                    → landing_zone.drawio
        │
        ▼
  render (same container, POST /render):  .drawio → landing_zone.svg + .png   (headless Chromium via drawio-export)
        │
        ▼
  answers/engagements/<c>/<p>/estimate/  landing_zone.{drawio,svg,png}
        │
        ▼
  dashboard landing-zone card (SVG inline + "Download .drawio")   ·   to_pptx / to_docx embed the SVG
```

| Piece | Usable from Foundry / Azure? | How Landfall uses it |
|---|---|---|
| **`simonkurtz-MSFT/drawio-mcp-server` as the engine** — HTTP transport, browserless, offline Azure icon catalog, VNet/subnet group primitives, `export-xml` | **Yes.** Deploy as a scale-to-zero Container App `ca-drawio` (internal ingress, `minReplicas: 0`) — the **third** side-car on the `ca-calc` / `ca-deckgen` pattern. Optionally also register it as a **raw MCP tool** on the agent (tool allow-list) for ad-hoc "tweak the diagram" chat asks — low-stakes, off the main path. | engine for `build_landing_zone_diagram` |
| **The skill's rules** — `xml-authoring-rules.md`, `azure.md` (colour palette, swimlane nesting, `parent="1"` cross-container edges, `search_shapes`-first, no hand-routed edges, layout-pass choice) | **Yes — vendored as our ruleset.** | coded into `src/api/lz/diagram.py`'s mapping + a one-line agent system-prompt note |
| **The render step** — `.drawio → svg/png` always needs headless Chromium/Electron somewhere | **Yes.** Bake `drawio-export` (or draw.io desktop `--export`) into the `ca-drawio` image, expose `POST /render`. One container, two jobs. Fallback: a `/render` endpoint on `ca-calc` (already has Chromium); last resort: ship `.drawio` only + render client-side with the draw.io viewer lib. | producing the SVG/PNG the dashboard + deck show |

**Components to build (E11.22):**
- `ca-drawio` Container App — `simonkurtzmsft/drawio-mcp-server` image mirrored to our ACR,
  started `--transport http`, port 8080, internal ingress, `minReplicas: 0`; `drawio-export`
  layered in for `POST /render`. Bicep in `infra/resources.bicep`; `DRAWIO_MCP_URL` app
  setting on the Function.
- `src/api/lz/diagram.py` — pure `design_landing_zone` JSON → ordered MCP-call plan
  (groups, cells with Azure icon keys, edges). Fully unit-tested, no network. Mirrors
  `calculator_spec.py`.
- `build_landing_zone_diagram` Function + `src/api/openapi/build_landing_zone_diagram.json`
  (required `engagement`). Opens an MCP session to `ca-drawio`, replays the plan,
  `export-xml`, `POST /render`, writes the 3 blobs. Mirrors `build_calculator_estimate`.
- Agent — new tool in `_OPENAPI_TOOLS`; system-prompt line ("after `design_landing_zone`,
  call `build_landing_zone_diagram`"); **"Landing-zone diagram"** prompt card. Optionally
  the `ca-drawio` MCP connection registered as a Foundry MCP tool.
- `docs/diagram-authoring/{xml-authoring-rules,azure,layout-antipatterns}.md` — the skill's
  reference docs vendored, same as the xlsx/docx references in §3.1.

**Output & wiring:**
- `answers/engagements/<c>/<p>/estimate/landing_zone.{drawio,svg,png}`, regenerated
  whenever `design_landing_zone` / the target region changes.
- Dashboard: SVG inline on the landing-zone card; "Download .drawio" so an architect edits
  it in draw.io desktop.
- `to_pptx` swaps its current hand-drawn hub-spoke slide for the rendered diagram;
  `to_docx` embeds the SVG.
- The diagram is **labelled with the engagement's `target_region` / `dr_region`** and the
  hub components from the actual design — not a generic template.

### 4.11 `design_landing_zone` grounded in the Azure ALZ / AI-LZ design checklists (E11.23)

**Ask (2026-09-08):** use the
[Azure AI Landing Zone **design checklist**](https://azure.github.io/AI-Landing-Zones/architecture/design-checklist/)
to design the target landing zone from the Foundry agent.

**Same pattern as MEG and the two diagram skills — a vendored *design reference* the
deterministic tool applies; the agent does not re-derive architecture.** `design_landing_zone`
(`src/api/lz/design.py`, E3.1–E3.3) already produces the MG hierarchy, spokes, IP plan,
policy baseline, identity and DR pairing. E11.23 makes it **check its output against the
published checklists** and emit a **conformance section**:

- **Vendor the checklist** to `docs/lz-design/{alz-checklist,ai-lz-checklist}.md` — the 10
  domains (Compute · Cost · Data · Governance · Identity · Monitoring · Reliability ·
  Resource Organization · Security · Networking) and each item, as the coded-in ruleset.
- **`design.py` emits `checklist_conformance[]`** — one row per checklist item:
  `{domain, item, status: met | partial | gap | n/a, evidence, recommendation}`. Deterministic:
  e.g. *Networking → "private endpoints for all PaaS"* → `met` if the design's policy
  baseline includes the private-endpoint initiative; *Identity → "Entra ID, not API keys"*
  → `met` (baseline); *Reliability → "≥2 regions"* → `met` if `dr_region` set, else `gap`.
- **AI-LZ overlay** — when the inventory shows **AI / ML / analytics workloads** (app
  `workload_type`, or servers running ML runtimes), `design.py` adds the AI-LZ specifics:
  Azure AI Foundry hub + project per engagement, AI Search + Content Safety behind private
  endpoints, **APIM as the generative-AI gateway**, PTU + PAYG spillover for cost, the
  Responsible-AI dashboard for governance. Otherwise the AI-LZ rows are `n/a`.
- **Deliverables** — `assemble_estimate` gets a **"Landing-zone design conformance"**
  section (met / partial / gap counts + the gap list with recommendations); `to_docx` /
  `to_pptx` render it; the dashboard landing-zone card shows a conformance chip
  (`27/30 checklist items met`).
- **Agent** — system-prompt line: *"the landing-zone design is checked against the Azure
  (AI) Landing Zone design checklist; surface any `gap` rows when the user asks about the
  target architecture."* No new tool — it rides on `design_landing_zone` /
  `assemble_estimate` output. The **"Landing zone"** prompt card's answer includes the
  conformance summary.

Net: the target LZ is **provably aligned to Microsoft's own ALZ / AI-LZ guidance**, and
the gaps are explicit — stronger in a funding / architecture review than an unattributed
design.

### 4.12 Conversation memory + engagement portability (E11.26)

**Ask (2026-09-08):** *"memory should be under the Foundry agent"* — the chat only
remembers the current browser tab (lost on New chat, close, second device; not tied to
the customer/project). And: the solution is `azd up` / `azd down` on demand to save cost,
so it must be **portable**.

**Decision — persist the conversation server-side per engagement; do NOT adopt the
managed Memory feature.** The panel (AI architect / cloud architect / FinOps / director)
rejected [Foundry Agent Service Memory (preview)](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage):
it needs the **Standard agent setup backed by Cosmos DB** — Landfall runs a **low-code
prompt agent** on purpose; Cosmos carries a 24/7 RU floor (breaks near-free), it's preview
(API churn hurts a redeploy-months-later story), and it's the wrong model — a **funding
POE must be deterministic**, so the agent's context should come from *tools reading the
uploaded inventory + `_discovery.json` + the published estimate*, not from an LLM
"remembering."

**What ships instead:**

- The Responses API already stores the conversation chain in the Foundry project
  (`store=true`). Landfall keeps only the **pointer + a transcript** in
  **`answers/engagements/<c>/<p>/_chat.json`** — `{current_response_id, started_at,
  turns[], archived[]}`. `/api/chat` reads the pointer from there (not the browser),
  chains `previous_response_id`, appends both turns. **Zero new Azure resources.**
- `GET /api/engagements/<c>/<p>/chat` — the transcript; the page renders it on load /
  engagement switch, so nothing is lost on a browser close and the conversation is
  **scoped to the customer/project**.
- `POST …/chat/new` — "New chat" **archives** the current thread (summary + last response
  id) into `archived[]` and starts fresh; the old Foundry chain stays retrievable.
- **Engagement export / import** — `GET …/export` streams one `.zip` (manifest + every
  upload + every produced artifact + `_chat.json` + `export.json`); `POST
  /api/engagements/import` restores it (validates `export.json`, slug-checks the id,
  blocks path traversal, **409 unless `overwrite=true`**). So an engagement is a
  **portable unit** — archive it before `azd down`, restore it after `azd up`, or move it
  between deployments. 250 MB cap, empties + HNS directory markers skipped.
- Chat page: header gains **↓ export** (when an engagement is active) and **↑ import**;
  the `localStorage` thread id is dropped (the engagement id still persists so the page
  reopens where you left off).

**`ca-calc` has no ingress (2026-09-08).** Since §4.6 made it queue-driven, nothing calls
its HTTP endpoint in Azure — the internal ingress only rendered "Error 404 — Container
App stopped" to anyone who opened the URL. Removed; `ca-calc` is a pure `calc-jobs`
queue worker (`minReplicas: 1`). `/healthz` + `/build` stay in `app.py` for local dev.

---

## 5. Work breakdown — Epic E11: Engagement Workspaces

| # | Item | P | Acceptance |
|---|---|---|---|
| **E11.1** | Engagement model + provisioning — slug rules, `_engagement.json`, `POST /api/engagements`, `GET /api/engagements` (list, filtered by `created_by`/visibility) | P0 | Creating "Contoso / DC-Exit" makes `raw/engagements/contoso/dc-exit/…` + `answers/…` and returns the id; a second "Contoso / DC-Exit" becomes `dc-exit-2` |
| **E11.2** | Per-engagement ADLS layout for `raw/` + `answers/`; Event Grid subject filter + blob-trigger path updated | P0 | A file dropped under one engagement never triggers ingestion for another |
| **E11.3** | SQL tenancy — `engagement_id` on all 6 tables, loader keying, `apply_sql.py` migration (idempotent, additive) | P0 | Two engagements' rows coexist; `SELECT` without the filter is impossible from `query_inventory` |
| **E11.4** | Ingestion scoped by engagement — `POST /api/ingest` + `run_engagement` take `engagement`; blob trigger derives it from the path | P0 | `run_engagement` ingests only that folder; DQ reports land under that engagement. **Done (2026-09-09, C19):** `POST /api/run_engagement` lists `raw/…/inventory/`, ingests every non-`_` file, appends a `_runs.jsonl` audit line, returns per-file + total summary; OpenAPI tool + agent prompt line added |
| **E11.5** | `engagement` is a **required argument on every OpenAPI tool** + the agent system prompt; `query_inventory` injects `WHERE engagement_id` | P0 | A tool call without `engagement` returns 400; the agent always supplies it; cross-engagement read returns nothing. **Done (2026-09-09, C19):** the `_default_/_default_` fallback removed from `query_inventory`, `assemble_estimate`, `publish_estimate` (400 if absent); `build_calculator_estimate` / `ingest` / `run_engagement` already required it; pure-compute tools (`vm_rightsize`, `estimate_*`, `design_landing_zone`, `score_dispositions`, `plan_waves`) stay unscoped by design |
| **E11.6** | Dashboard — engagements home, "New engagement" form (**incl. Target region + DR region + currency + licensing-program pickers**), upload panel (**with the region picker repeated, editable at upload time**), "Start analysis" / "Produce estimate" | P0 | A pre-sales user with no CLI creates an engagement, **picks the target Azure region**, uploads RVTools + a CMDB CSV, clicks Start, and sees a data-quality summary — in one session; the region is persisted to `_engagement.json` and flows into the estimate + the POE. **Done (2026-09-09, C20):** engagement `<select>` + "New engagement" form (region/DR/currency/licensing) + upload panel were built in C25/C26; C20 added the **"Start analysis"** button → `POST …/analyze` (catch-up ingest via the agent's `run_engagement`, `run_engagement` being idempotent) → renders a data-quality summary card (files/rows/tables/confidence/findings) + per-file ingest badges |
| **E11.7** | Dashboard — embedded engagement-scoped chat + configurable prompt cards (`prompt_cards.json`) | P0 | Clicking "Full estimate" produces and publishes the estimate for the open engagement and only that engagement. **Done (C21):** `/api/prompt_cards` serves the editable `prompt_cards.json`; the welcome view renders the cards; a click sends the card prompt through `/api/chat`, which prepends `[Active engagement: <eid>]` so every tool call is scoped |
| **E11.8** | `publish_estimate` + dashboard read/write the engagement path; `history/<ts>/` snapshots; a version picker on the dashboard | P1 | Re-publishing keeps the prior version; the dashboard can show any snapshot. **Done (C21):** `publish_estimate` snapshots the version it replaces into `history/<its-published_at>/` (best-effort) + stamps `meta.published_at`; `GET /api/engagements/<c>/<p>/history` lists versions; the dashboard is engagement-aware (`?e=`) with a version `<select>` that reloads `/dashboard/data` + the downloads with `&snapshot=<ts>` |
| **E11.9** | Studio-deck container (`ca-deckgen`) — `presentation-skill` + `ppt-master` as an OpenAPI tool; "Studio deck" prompt card | P1 | The agent calls it; a `qa_gate`-passing `studio.pptx` lands in the engagement folder. **DEFERRED** (see §4 decision 4): the rebuilt in-Function `python-pptx` deck (12-slide narrative, E5.6) is the default; add the Node side-car + its own Container App + infra when a client needs the design-rich variant |
| **E11.10** | Access control — `visibility` on `_engagement.json`, list filtering, audit trail of runs/publishes | P1 | A user sees only their own + group-shared engagements; every run is attributable. **Done (2026-09-09, C23):** `visibility` canonicalised to `owner` / `group:<id>` / `all` (`engagement.normalize_visibility`); `engagement.can_view(manifest, viewer, groups)` + `principal_from_easyauth` (decodes the base64 `x-ms-client-principal` incl. `groups` claims) — mirrored web-side in `src/web/access.py`. The Function `_list` + web `engagements_list` filter by it; `engagement_one` 403s; every engagement-scoped web read (`_engagement(…, request)` — files/analysis/analyze/history/chat/export) and the `/dashboard/*` routes (`_guard_eid`) return 404/403 when the caller can't see the engagement. Audit trail: `src/api/audit.py` (`record`/`read` → `answers/engagements/<c>/<p>/_audit.jsonl`) wired into engagement-create, `run_engagement`, `publish_estimate`; `GET /api/engagements/<c>/<p>/audit` (Function + web), newest-first. `tests/test_access_control.py` + `tests/test_audit.py` |
| **E11.11** | Migration + back-compat — fold the current single-tenant `raw/inventory/` + `answers/estimate/latest.*` + un-keyed SQL into `_default_/_default_` (or drop, synthetic); one-release shim | P1 | Existing deploy keeps working through the transition; docs updated. **Done (2026-09-09, C23):** `scripts/migrate_to_default_engagement.py` — **dry-run by default**, `--apply` moves the flat `raw/inventory/`+`raw/docs/`+`answers/estimate/` blobs under `engagements/_default_/_default_/…`, writes that engagement's `_engagement.json` (`visibility: all`) if missing, and backfills un-keyed SQL rows across all 6 tables (toggles the RLS policy off around the `UPDATE`); idempotent. One-release shim: the web app still resolves the pre-E11 flat `estimate/` path and logs a deprecation warning when it does (`_read_estimate_blob`). `docs/operating-sop.html` gains an "Access control & audit" ref section + an operator migration step. `tests/test_migration.py` |
| **E11.12** | E5.4q — `.xlsx` formulas-not-literals + a headless-LibreOffice recalc **CI gate**; `.docx` US-Letter DXA + tracked-changes-ready + `accept_changes` | P1 | Change an input in the workbook → the model re-flows; recalc reports 0 errors; architect edits are Word tracked changes. **Done (2026-09-09, C22):** `src/api/deliverable/xlsx_model.py` adds a **Model** sheet where each appendix figure whose `inputs` reproduce its `result` (sum / product / constant multiple — a prose-free numeric check) becomes an Excel formula over grey editable input cells; where an input equals another figure's result it references that figure's cell, so the run-rate roll-up F8 = F5+F6+F7 and the annualisation F9 = F8×12 reflow. `tests/test_xlsx_recalc.py`: formulas are Excel-2007-safe, each modelled figure reproduces its stated result, `{F8,F9}` always modelled; a **LibreOffice recalc gate** (`RECALC=1` + `soffice`, wired into `evals.yml`) opens the workbook, forces a recalc, asserts 0 error cells and that the recalculated totals match. `to_docx` now sets explicit US-Letter + 1" margins |
| **E11.13** | Evals — golden per-engagement isolation tests (two synthetic estates, assert no bleed); a `run_engagement` end-to-end scenario in the harness | P0 | A regression that leaks one engagement's rows into another fails CI. **Done (2026-09-09, C19):** `tests/test_run_engagement.py` (bulk-ingest stamps only its own engagement, DQ + audit land under it, a second engagement's folder is untouched) + `tests/test_engagement_required.py` (400s + `query_inventory` sets the RLS session context to the normalized caller engagement before any SQL) — on top of the existing loader-scoping tests |
| **E11.14** | **Ask & export to Excel** — `POST /api/answer_to_xlsx` (Question&answer + a sheet per table + Provenance), and a "Download as Excel" affordance on chat answers that carry tabular tool output | P0 | An architect asks "how many prod Windows servers and their vCPU?", gets the answer, and downloads a workbook with the rows + the SQL + the engagement + a DRAFT note. **Done (C21):** `src/web/answer_xlsx.py` (`build_answer_workbook` — Answer / sheet-per-table / Provenance, 5000-row + 12-sheet caps, sanitised sheet names; `tables_from_response` best-effort extract of `query_inventory` output from the Responses API result); `POST /api/answer_to_xlsx`; `/api/chat` stashes `tables`+`sql` on the assistant turn; the chat UI shows "⭳ Download as Excel" on answers that carried tabular output |
| **E11.15** | `src/api/lz/calculator_spec.py` — turn `design_landing_zone` + `estimate_compute_cost` + `estimate_storage_cost` output into a **calculator line-item spec** (§4.6), **using the engagement's `target_region` / `dr_region`** for `region_default` and every line's `region`. Region-name→calculator-code map (Azure name → `select[name=region]` value), VM-SKU→size-slug map, disk-tier→option map, LZ-platform-component→module map. Pure, fully unit-tested. | P0 | The sample estate + a chosen region produce a spec priced **in that region** with VMs (right-sized, per env, AHB/RI as configured), managed disks, hub networking (VNet/GW/Firewall/Bastion/DDoS/DNS), Log Analytics, Key Vault, egress bandwidth, backup — every item mapping to a real calculator module + field set; an unsupported region is rejected at engagement-create time |
| **E11.16** | **`ca-calc` Container App** — Playwright + Chromium image; product-adapter registry (~16 modules); drives the real calculator, sets estimate-name/currency/licensing, clicks Export, captures `ExportedEstimate.xlsx`, re-parses it, screenshots. **Async execution (C25 finding):** `build_calculator_estimate` Function writes `landing_zone.json` status `building`, kicks `ca-calc` fire-and-forget, returns **202**; `ca-calc` writes `landing_zone.{xlsx,json,png}` (status `ready`/`failed`) to the engagement folder **with its own MSI** (Storage Blob Data Contributor). `GET` status route. Bicep + ACR image + `CALC_URL` + RBAC. min-replicas 0. | P0 | Agent calls the tool, gets 202; within a few minutes a genuine calculator `.xlsx` (sheet `Your Estimate`, `Total` row, `created at` line) lands at `answers/engagements/<c>/<p>/estimate/landing_zone.xlsx`; `landing_zone.json` goes `building → ready` and carries the spec + parsed totals + `calculator_url` + `internal_vs_poe_delta_pct` + any `skipped[]`; a sync call never 502s because there is no sync call. **Container + infra DEPLOYED 2026-09-08 (`3c44b5e` infra); async redesign + RBAC OUTSTANDING** |
| **E11.17** | Dashboard — **"Azure landing zone — Pricing Calculator POE"** card ($X/mo · $Y/yr · created `<ts>`, "what's included" drawer, `internal_vs_poe` delta flag); `GET /dashboard/download/landing-zone-xlsx?e=<eid>` streams `landing_zone.xlsx`; `landing_zone.json` read path with the same fallback chain as `latest.json` | P0 | Opening the dashboard for an engagement shows the calculator monthly total and a working **Download Excel (POE)** button; the file is byte-identical to what `ca-calc` stored |
| **E11.18** | Agent wiring — `build_calculator_estimate` OpenAPI tool (required `engagement`), system-prompt line, the **"Landing zone cost (Calculator POE)"** prompt card; **`publish_estimate` auto-kick hook** (`build_poe=true` stages the POE run in the same call via the shared `lz.functions.stage_calc_run`, best-effort) | P0 | The card / a chat instruction makes the agent call the container for the open engagement and only that engagement; the dashboard card refreshes. **Auto-kick added 2026-09-09 (C25b)** — `publish_estimate {build_poe:true}` publishes *and* queues the calculator run |
| **E11.19** | CI **weekly Playwright calculator-adapter smoke** (open the calculator, add every adapter's product, apply its fields, assert the controls resolve); **(deferred)** authenticated Save → shared estimate link stored as `landing_zone_url` | P1 | A calculator UI change that breaks an adapter fails the weekly job with the adapter named; a broken adapter degrades to `skipped[]`, never a wrong price. **Built + run live 2026-09-09 (C25b):** `src/calc/smoke.py` + `.github/workflows/calc-adapter-smoke.yml` (Mon 06:17 UTC + dispatch) + `tests/test_calc_adapter_smoke.py` (gated `CALC_SMOKE=1`). Drove the smoke against the live calculator repeatedly to rebuild the adapter registry — see C25b |
| **E11.20** | **Engagement-id resolution — the user never types the slug** (§3.5). One shared `make_engagement_id()`; dashboard engagement `<select>` + inline "New engagement" form (names + region/licensing, not the id); `/api/chat` prepends `[Active engagement: …]`; `resolve_engagement` OpenAPI tool with fuzzy candidate matching; agent system prompt reworked to forbid inventing a slug | P0 | A user only ever enters a customer name and a project name; the id used for the ADLS folder, the SQL filter and every tool call is the same derived string; naming "contoso / dc exit" in chat resolves to the existing `contoso-ltd/dc-exit-2027` without the user knowing the slug. **Built + deployed 2026-09-08 (`458d400`); verify picker after hard refresh** |
| **E11.21** | **Engagement-first chat view** (§4.9) — left rail with the active engagement (customer/project heading), a status strip (Uploads · Analysis · Published estimate · Calculator POE), region + licensing summary, prompt cards / "new engagement"; chat thread + a dashboard tab share the main pane, both scoped to the rail; **Markdown-rendered assistant messages**; per-message toolbar (copy, expand tool calls, "download as Excel"); inline error card with Retry; responsive header. The current single-page chat becomes the "no engagement selected" empty state | P1 | The 10 panel findings in §4.9 are closed; a reviewer can tell which client is active at a glance, see its pipeline state, read a table in an answer without it looking broken, and reach the dashboard for that engagement without losing context. **Needs sponsor sign-off before start** |
| **E11.24** | **Upload panel + visual upload confirmation** (§4.5, §4.5a) — the engagement-page Upload panel (drag-drop, data/docs toggle, region pickers), `POST /api/engagements/<c>/<p>/upload` (server-side streamed to `raw/…/inventory` or `/docs`, slug-checked, 4 MB blocks), content-sniffed type + size gates (100 MB/file, 250 MB/request, 2 GB/engagement), per-file progress → ✓ uploaded row with detected profile + row count + toast, a persisted manifest panel that re-lists the folder and shows an analysis-will-use badge, ingest badges after Start analysis | P0 | A pre-sales user with no CLI drops `RVTools.xlsx` + a CMDB `.csv` on the Contoso/DC-Exit page, watches each file go uploading → ✓ uploaded (RVTools vInfo · 412 rows), sees them in the manifest, and the files are in `raw/engagements/contoso/dc-exit/inventory/` and nowhere else; a `.xlsm` is rejected with a clear reason. **Done:** streamed upload + magic-byte classify + `peek` profile/row-count + manifest (C25); **C20 (2026-09-09)** added `GET …/analysis` (reads the `_ingest/*.dq.json` reports the per-file Event Grid ingest trigger produces), the ingest badges (`✓ N rows → <table>` / `M rejected` / `not analysed`), and the pending-file poll |
| **E11.26** | **Per-engagement conversation memory + engagement export/import** (§4.12) — `_chat.json` per engagement (pointer + transcript + archived threads), `/api/chat` reads/chains it server-side, `GET …/chat`, `POST …/chat/new` (archive not destroy); `GET …/export` (one `.zip`: manifest + uploads + artifacts + chat) and `POST /api/engagements/import` (409 unless overwrite). Chat page renders the saved transcript on select; header ↓ export / ↑ import. **Not** the managed Foundry Memory feature. `ca-calc` ingress removed (queue worker). No new Azure resources | P0 | Closing the browser and reopening keeps the engagement's conversation; a follow-up ("their vCPU?") resolves against the stored chain; an engagement exports to a `.zip` that re-imports into a fresh `azd up` with its files + estimate + chat intact. **Done + deployed 2026-09-08 (Cycle 26)** |
| **E11.25** | **Discovery questionnaire as a served, round-trippable artifact** (§4.5b) — `GET /questionnaire`; export to `.docx`/`.xlsx`; the completed file uploads through E11.24 into `docs/`, the importer recognises the template → `raw/…/_discovery.json`; `assemble_estimate` cites its answers in the assumptions register, `design_landing_zone` uses its compliance + DR answers; unanswered items become dashboard "ask the client" + the agent's "What's missing?" | P1 | A pre-sales architect opens `/questionnaire`, exports the Word version for the client, uploads the returned file, and its answers drive the estimate's assumptions with per-answer citations; blank answers show as client-ask items. **Done (2026-09-09, C20b):** `scripts/gen_discovery_catalog.py` projects `docs/discovery-questionnaire.html` (92 questions, 14 sections) → `src/web/discovery_catalog.json` + a byte copy `src/web/questionnaire.html` (drift-gated by `tests/test_discovery.py`). `src/web/discovery.py`: `render_xlsx`/`render_docx` (blank or `?e=`-prefilled), `parse_upload` (xlsx + docx, matches on question codes, ≥3 = the template), `gaps` (unanswered MUST/SHOULD), `discovery_record`. Web: `GET /questionnaire`, `GET /questionnaire.{xlsx,docx}`, `GET /api/engagements/<c>/<p>/discovery`; the upload route recognises a completed questionnaire in `docs/` → writes `raw/…/_discovery.json`. API: `deliverable/functions.py::_discovery_for` reads `_discovery.json` and injects it into `assemble_estimate`/`publish_estimate`; `assemble.py` folds each answer into the register as a cited `discovery:<id>` assumption and the top-12 unanswered MUST questions as `discovery:*` data-gaps; `register.discovery` headline. Dashboard register card + `create_agent.py` "what's missing" prompt line + prompt-card. `python-docx` added to `src/web/requirements.txt`. `tests/test_discovery.py` (15). 315 pass |
| **E11.23** | **`design_landing_zone` checklist conformance** (§4.11) — vendor the Azure ALZ + [AI-LZ design checklist](https://azure.github.io/AI-Landing-Zones/architecture/design-checklist/) to `docs/lz-design/`; `src/api/lz/design.py` emits `checklist_conformance[]` (10 domains, `met`/`partial`/`gap`/`n/a` + evidence + recommendation) deterministically from the existing design output; AI-LZ overlay (Foundry hub/project, AI Search + Content Safety private, APIM gen-AI gateway, PTU+PAYG, Responsible-AI dashboard) when the inventory has AI/ML workloads; `assemble_estimate` + `to_docx`/`to_pptx` + dashboard card get a "design conformance" section; agent system-prompt line. No new tool | P1 | The landing-zone deliverable for an engagement lists every ALZ/AI-LZ checklist item as met/partial/gap with evidence + a recommendation for each gap; the dashboard shows `N/M items met`; the agent surfaces gaps when asked about the target architecture. **Done (2026-09-09, C28):** `docs/lz-design/{alz-checklist,ai-lz-checklist}.md` vendored (source URLs + retrieval date); `src/api/lz/conformance.py` (pure) — ~34 ALZ items across 10 domains + a 10-item AI-LZ overlay, each a deterministic rule over the design's *structured* output (never prose); `design_landing_zone` returns `checklist_conformance[]` + `checklist_summary` (`{met,partial,gap,na,total,met_pct,headline}`) + `checklist_gaps[]` + `ai_lz_applicable`. AI overlay is `n/a` (excluded from the ratio) unless an app's `workload_type`/name/stack signals AI/ML/analytics. `assemble.py` `_body_lz` carries `design_conformance` + a `lz_conformance` figure; `export.py` renders the headline + gap list in docx/pptx; `dashboard.html` LZ card shows the headline pill + a "gaps to close" `<details>`. Agent system-prompt line added (re-run `create_agent.py`). `tests/test_lz_conformance.py` (13). 300 pass |
| **E11.22** | **Target landing-zone diagram — `drawio-mcp-diagramming` engine in Azure** (§4.10). `ca-drawio` Container App (`simonkurtz-MSFT/drawio-mcp-server`, HTTP transport, browserless, 700+ offline Azure icons, `minReplicas: 0`) + `drawio-export` for `POST /render`. `src/api/lz/diagram.py` (pure, unit-tested) maps `design_landing_zone` JSON → an ordered MCP-call plan (groups, Azure-icon cells, edges, `libavoid`) using the skill's `xml-authoring-rules` + `azure.md` as the coded-in ruleset. `build_landing_zone_diagram` Function (required `engagement`) replays the plan against `ca-drawio`, `export-xml` → `.drawio`, renders `.svg`/`.png`, writes all 3 to `estimate/`. Agent tool + "Landing-zone diagram" prompt card; optional `ca-drawio` MCP tool on the agent for chat tweaks. Dashboard SVG + "Download .drawio"; `to_pptx` / `to_docx` embed the SVG. Skill refs vendored to `docs/diagram-authoring/`. **Deterministic driver — the agent does not free-draw** | P1 | Producing a landing zone for an engagement yields `landing_zone.{drawio,svg,png}` showing the hub, spokes, shared services and DR pairing for that engagement's chosen region, with correct Azure icons, editable in draw.io desktop; the same design always produces the same diagram; the PPT hub-spoke slide is the rendered diagram, not the hand-drawn one |

**Infra deltas (`infra/resources.bicep`):** Event Grid subject filter; a `ca-deckgen`
Container App (E11.9), a **`ca-calc` Container App** (E11.16, Playwright/Chromium image)
and a **`ca-drawio` Container App** (E11.22, `simonkurtz-MSFT/drawio-mcp-server` +
`drawio-export`, internal ingress, `minReplicas: 0`) + their ACR images + OpenAPI-tool
env vars (`CALC_URL`, `DRAWIO_MCP_URL`); optionally a Foundry MCP-tool connection to
`ca-drawio`; no new data stores for v1.

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
| **C19** | E11.4 + E11.5 + E11.13 (ingestion + every tool scoped; isolation evals) | **Done (2026-09-09):** `POST /api/run_engagement` bulk-ingests one folder (+ `_runs.jsonl` audit, OpenAPI tool, agent prompt line); `query_inventory` / `assemble_estimate` / `publish_estimate` 400 without `engagement` (no `_default_` fallback); `tests/test_run_engagement.py` (6) + `tests/test_engagement_required.py` (6) green, full suite 230 pass, SCORECARD unchanged. **Deployed + verified live 2026-09-09** (`azd deploy api` + `create_agent.py`): agent-driven end-to-end (upload servers.csv → run_engagement ingests → query_inventory RLS-scoped returns exactly those rows; `_default_` still 250) |
| **C20** | E11.6 + E11.24 + E11.25 (dashboard: home, new-engagement, **upload panel + visual upload confirmation**, start analysis; discovery questionnaire served + round-trippable) | **Core done (2026-09-09):** engagement create/select + upload panel (C25/C26) + **"Start analysis"** → `POST …/analyze` (agent `run_engagement` catch-up) → data-quality summary card + per-file ingest badges + pending poll (`GET …/analysis`); web tier needs no Function credentials. Full suite 235 pass. **E11.25 (discovery questionnaire — served + round-trippable) deferred to C20b** — independent P1, not on the upload→analysis critical path. **Not yet deployed** (`azd deploy web`) |
| **C20b** | E11.25 (discovery questionnaire — served, exported to Word/Excel, re-imported → `_discovery.json`, folded into `assemble_estimate` with per-answer citations) | **Done (2026-09-09):** `scripts/gen_discovery_catalog.py` → `src/web/discovery_catalog.json` (92 Q) + `questionnaire.html` (drift-gated); `src/web/discovery.py` (render/parse xlsx+docx, gaps); `GET /questionnaire`, `/questionnaire.{xlsx,docx}`, `GET …/discovery`; upload route recognises a completed questionnaire → `_discovery.json`; `assemble_estimate` cites answers as `discovery:<id>` + top-12 unanswered MUST as data-gaps; dashboard + agent "what's missing" + prompt card. 315 pass. Deploy: `azd deploy api` + `web` + re-run `create_agent.py` |
| **C21** | E11.7 + E11.8 + E11.14 (engagement-scoped chat + prompt cards + "ask & export to Excel"; versioned publish) | **Done (2026-09-09):** E11.7 already wired (prompt cards → scoped `/api/chat`); E11.8 — `publish_estimate` history snapshots + `GET …/history` + engagement-aware dashboard with a version `<select>`; E11.14 — `answer_xlsx.py` + `POST /api/answer_to_xlsx` + "⭳ Download as Excel" on tabular chat answers. Full suite 248 pass, evals PASS. **Not yet deployed** (`azd deploy api` + `azd deploy web`) |
| **C22** | E11.9 + E11.12 (studio-deck container; xlsx/docx polish + CI recalc gate) | **Done (2026-09-09):** E11.12 — the workbook is a live model (Model sheet, formula roll-up F8=F5+F6+F7, F9=F8×12) + a LibreOffice recalc CI gate in `evals.yml` + US-Letter docx. E11.9 (`ca-deckgen`) stays **deferred** per §4 decision 4 — the in-Function `python-pptx` deck is the default. Full suite 252 pass, evals PASS |
| **C23** | E11.10 + E11.11 (access control, audit, migration + shim, docs) | **Done (2026-09-09):** `visibility` (`owner`/`group:<id>`/`all`) enforced on the engagements list + every engagement-scoped read (Function + web); Easy Auth principal + group claims decoded from `x-ms-client-principal`; per-engagement `_audit.jsonl` + `GET …/audit` (create / run_engagement / publish attributable). `scripts/migrate_to_default_engagement.py` (dry-run default, idempotent) folds the pre-E11 flat blobs + un-keyed SQL into `_default_/_default_`; web keeps a one-release flat-path shim. Docs updated. Suite 287 pass, evals PASS |
| **C24** | E11.15 + E11.16(build) + E11.20 (calculator line-item spec builder; `ca-calc` container; engagement-id resolution + chat picker + prompt cards + "working" indicator) | **Done (2026-09-08, `3c44b5e`):** `calculator_spec.py` (pure, 21 tests; **verified against real `_default_/_default_` data → 55 line items, internal ~$97.6k/mo**) + `calculator_export.py` + `build_calculator_estimate` Function + `ca-calc` scaffold + Bicep + dashboard POE card + E11.20 built, committed, api+agent deployed |
| **C25** | E11.16 **async redesign** + deploy + E11.17 + E11.18 | **Async DONE + verified live end-to-end (2026-09-08).** `ca-calc` Container App deployed; the sync `Function → ca-calc` call was found to 502 (no shared VNet to the internal ingress **and** the ~230 s Functions HTTP limit), so it's now **queue-decoupled**: `build_calculator_estimate` stages the spec + drops a `calc-jobs` message + returns 202; `ca-calc` (minReplicas 1, background consumer) drains it, drives the real calculator, and writes `landing_zone.{xlsx,json,png}` with the workload identity. Proven: agent → 202 in 10 s → 55-line calculator run → genuine `ExportedEstimate.xlsx` stored. `get_calculator_estimate` poll tool + dashboard `building/ready/failed` card shipped. **Remaining → C25b (DONE 2026-09-09):** the −73 % delta was the driver skipping the first (VMs) line item + writing every field to module 0 — adapters rebuilt from the live DOM, delta now +56 % (list-price reconciliation); `publish_estimate` POE auto-kick also landed. KEDA scale-to-zero for `ca-calc` was tried and reverted (KEDA didn't scale up on a queued job — MI-auth path). Deployed live 2026-09-09 (`azd provision` + `azd deploy calc api` + `create_agent.py`) |
| **C25b** | E11.19 — adapter accuracy: verify every `ca-calc` adapter against the live calculator, add the weekly smoke | **Done (2026-09-09):** the calculator DOM had drifted — `Managed Disks` / `Azure Files` are their own products now (not Storage-Account sub-types), and Firewall/Bastion/DNS/Bandwidth controls are renamed per tier/type selection. Rebuilt `src/calc/adapters.py` from the live DOM (16 of 20 adapters `verified: True`, real control names + option maps); fixed the driver's module-scoping bug (every field was landing on module 0), the "first add fills the empty placeholder module" bug (the first — always VMs — line item was silently skipped → the −73%), and added `accordion`/retry/2-pass-settle handling. `src/calc/smoke.py` + weekly workflow + gated pytest. **Live end-to-end verified:** 17-line sample spec → genuine `ExportedEstimate.xlsx`, all 17 lines priced, reconciliation **−73% → +56%** (POE now above internal — a list-price-vs-RI/AHB reconciliation question, not a broken-adapter one). Known `verified: False`: `azure-files` (provisioned-v2 storage field), `azure-bastion` (outbound-transfer field), `azure-monitor`, `load-balancer`, `application-gateway` — each degrades to calculator defaults, never a wrong-but-confident price. **Also in C25b:** `publish_estimate {build_poe:true}` auto-kicks the POE run (shared `lz.functions.stage_calc_run`); a KEDA `azure-queue` scale rule on `ca-calc` was added but KEDA did not scale the replica up on a queued job (MI-auth path not wired in this Container Apps/KEDA version) so `minReplicas` stays 1 (always-on poller); the `apply_sql.py` `GO`-splitter regex that hung `azd` postprovision at 100% CPU was fixed. **Deployed + verified live 2026-09-09.** **Follow-ups also done live 2026-09-09:** a full-page-screenshot renderer OOM in the 2 GiB `ca-calc` was losing completed runs → export the xlsx before the (now viewport-only, best-effort) screenshot + `ca-calc` → 2 vCPU/4 GiB; the residual per-tier/per-OS field-misses closed (Linux VM distro `type` + no AHB radio; `_anf_fields`/`_files_fields` tier-prefixed capacity controls; `azure-files` → `verified:True`). 2nd live 55-line run: `fields_not_set` 18 → 1 (Bastion outbound only), POE $117k → $124.8k, reconciliation +19.9% → **+27.9%** (premium ANF/Files now price real capacity, not the calculator's 1-unit default). Real `run_engagement` bulk-ingest Function is C19 (done in code 2026-09-09) |
| **C26** | E11.26 (per-engagement conversation memory + engagement export/import; `ca-calc` ingress removed) | **Done (2026-09-08):** conversation persists per engagement server-side; an engagement `.zip`-exports and re-imports across `azd down`/`up`; live-verified |
| **C26b** | E11.21 (engagement-first chat view — rail, status strip, Markdown answers, per-message toolbar, dashboard tab, responsive header) — **sponsor sign-off required first** | The §4.9 panel findings are closed; the chat page is engagement-first, not chat-first |
| **C27** | E11.22 (`ca-drawio` Container App — `simonkurtz-MSFT/drawio-mcp-server` + `drawio-export`; `lz/diagram.py` deterministic MCP-call plan; `build_landing_zone_diagram` Function + agent tool + prompt card; dashboard + deck + doc embed; skill refs vendored) | Producing a landing zone yields an engagement-specific `.drawio` + rendered SVG for the chosen region with correct Azure icons; same design → same diagram; the deck uses it |
| **C28** | E11.23 (`design_landing_zone` checklist conformance — vendor the ALZ + AI-LZ design checklist; `checklist_conformance[]` + AI-LZ overlay; deliverable section + dashboard chip + agent prompt line) | **Done (2026-09-09):** checklists vendored to `docs/lz-design/`; `src/api/lz/conformance.py` scores the design (34 ALZ + 10 AI-LZ items, deterministic rules over structured output) → `checklist_summary`/`checklist_gaps` on `design_landing_zone`; assembled into the LZ section + `lz_conformance` figure; docx/pptx render the gaps; dashboard LZ card shows `N/M met` + a gaps drawer; agent prompt line. AI-LZ overlay `n/a` unless AI/ML workloads. 300 pass, evals PASS. Deploy: `azd deploy api` + `web` + re-run `create_agent.py` |

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
7. **The end user never types the engagement id (2026-09-08).** One shared slugging
   function backs the dashboard, the API, the SQL filter and the ADLS folders; the UI
   collects **names** (customer, project) via a picker + inline form and the agent
   resolves names → id via the `resolve_engagement` tool with fuzzy matching. The agent
   must not invent a slug. New work E11.20, in C24. See §3.5.
8. **Chat page moves engagement-first, but as a gated cycle (2026-09-08).** The C24
   picker/cards/greeting land now; the fuller redesign (rail, status strip, Markdown
   answers, dashboard tab — §4.9) is **E11.21 / C26 and needs sponsor sign-off** before
   it starts, to let the C24 changes settle.
9. **Landing-zone diagram — the `drawio-mcp-diagramming` engine in Azure, driven
   deterministically (2026-09-08).** `simonkurtz-MSFT/drawio-mcp-server` (HTTP transport,
   browserless, 700+ offline Azure icons) is deployed as a scale-to-zero Container App
   `ca-drawio`; `src/api/lz/diagram.py` maps `design_landing_zone` output to a fixed
   MCP-call plan and `build_landing_zone_diagram` replays it, so the same design always
   yields the same diagram. The skill's XML/Azure rules are vendored to
   `docs/diagram-authoring/`. The agent calls one OpenAPI tool; it does **not** free-draw
   via MCP (slow, non-repeatable, on the funding path) — though `ca-drawio` may also be
   registered as a raw MCP tool for low-stakes chat tweaks. New work E11.22, PDCA C27.
   See §4.10.
10. **`ca-calc` is queue-decoupled, not called directly (2026-09-08 C25 finding).** The
    Flex Consumption Function App shares no VNet with the Container Apps Environment, so
    it can't reach `ca-calc`'s internal ingress at all; and a multi-minute Playwright
    drive overruns the ~230 s Functions HTTP limit regardless. So
    `build_calculator_estimate` stages the spec to blob + drops a `calc-jobs` storage
    queue message + returns **202**; `ca-calc` runs a background queue consumer
    (`minReplicas: 1` for now; KEDA queue-scale-to-zero is the follow-up) that drains the
    message, drives the calculator, and writes `landing_zone.{xlsx,json,png}` with the
    shared workload identity. The dashboard card + `get_calculator_estimate` poll the
    `building/ready/failed` status. Verified live end-to-end. See §4.6.
11. **`design_landing_zone` is checked against Microsoft's ALZ / AI-LZ design checklist
    (2026-09-08).** The checklist is vendored as a design reference; `design.py` emits a
    deterministic `checklist_conformance[]` + an AI-LZ overlay for AI/ML estates; the
    deliverable, dashboard and agent surface met/partial/gap. New work E11.23, PDCA C28.
    See §4.11.
12. **Upload: server-side, content-sniffed, per-engagement-isolated, with visible
    confirmation (2026-09-08).** The engagement page gets an Upload panel (E11.6/E11.24):
    `.csv/.xlsx/.tsv/.json`(+`.zip`) → `raw/…/inventory/`, `.pdf/.docx/.md/.txt/.png` →
    `raw/…/docs/`; types are magic-byte + structure checked, not extension-trusted;
    macro-Office and executables rejected. Caps: 100 MB/file, 250 MB/request, 2 GB/
    engagement; streamed in 4 MB blocks, never a browser SAS. The customer/project slug
    (one shared function) is the isolation boundary — a file cannot be written outside its
    engagement prefix; **outputs stay in the separate `answers/engagements/<c>/<p>/`
    tree.** Every file shows uploading → ✓ uploaded (detected profile + row count) + a
    toast, and a persisted manifest panel is the durable proof. See §4.5a.
14. **Conversation memory is the Responses API's own store, per engagement — not the
    managed Memory feature (2026-09-08).** `_chat.json` per engagement holds the pointer
    + transcript; `/api/chat` chains it server-side. The preview managed Memory feature
    was rejected (needs Cosmos DB / Standard agent setup — wrong cost + portability for a
    tear-down-friendly prompt-agent tool; a funding POE must stay deterministic).
    Engagement **export/import** (`.zip`) makes an engagement portable across
    `azd down`/`azd up`. `ca-calc` ingress removed (it's a queue worker). New work
    E11.26, PDCA C26. See §4.12.
13. **The discovery questionnaire is delivered through the solution (2026-09-08).**
    `docs/discovery-questionnaire.html` becomes `GET /questionnaire` + a Word/Excel export
    the client fills offline + an upload that the importer parses to
    `raw/…/_discovery.json`, which feeds `assemble_estimate`'s assumptions register and
    `design_landing_zone`. New work E11.25, PDCA C20. See §4.5b.

**Build order:** C18 done (E11.1–E11.3, live). C24 done. **C25 in progress** — `ca-calc`
deployed; **next concrete step = the E11.16 async redesign** (Function 202 + `ca-calc`
self-writes the blobs + status polling), then verify the unverified adapters live and
wire the dashboard card + agent tool end-to-end. C19–C23 (tenancy hardening + dashboard
UX) continue in parallel by reviewer availability. C26 (E11.21) is gated on sponsor
sign-off; C27 (E11.22) and C28 (E11.23) follow.
