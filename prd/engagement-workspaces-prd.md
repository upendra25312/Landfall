# Landfall — Engagement Workspaces (multi-client, dashboard-driven)

**Status:** PLAN · **Raised:** 2026-09-08 · **Owner panel:** see below · **Method:** PDCA
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
> 2. **upload** the client documents into ADLS — with a **unique folder per project /
>    customer**;
> 3. **start the analysis**;
> 4. use a **chat bot** with **pre-defined prompt cards** to drive the desired outcomes.
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

---

## 4. PLAN — target architecture

### 4.1 Engagement identity

An **engagement** = `(customer, project)`. Slugged to
`^[a-z0-9][a-z0-9-]{1,40}$` per segment; the pair `<customer>/<project>` is the
**engagement id** used in every path, SQL filter and tool call. A collision appends
`-2`, `-3`. Display names are kept verbatim in `_engagement.json`.

### 4.2 ADLS Gen2 layout (one deployment, HNS already on)

```
raw/
  engagements/<customer>/<project>/
    inventory/          client uploads — servers/apps/deps/perf/storage (CSV, RVTools .xlsx, CMDB export)
    docs/               narrative docs — compliance, network, DR, NFR
    _mapping.json       optional column-override (E1.7), per engagement
    _engagement.json    {customer, project, display, created_by, created_at, status, region}
answers/
  engagements/<customer>/<project>/
    _ingest/            data-quality reports, one per uploaded file
    estimate/           latest.json + latest.{xlsx,docx,pptx}  (+ studio.pptx from E11.9)
    history/<utc-ts>/    immutable snapshot of every publish
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

### 4.5 Dashboard (`src/web`) — the four things the user asked for

Route model: `/` = engagements home · `/e/<customer>/<project>` = one engagement.

1. **New engagement** — a form: *Customer name*, *Project name*, optional *Primary
   region* / *notes*. `POST /api/engagements` → web app (MSI) writes `_engagement.json`
   + creates the folder skeleton → redirects to `/e/<c>/<p>`. The Entra user id is
   recorded as `created_by`.
2. **Upload** — a drag-and-drop panel on the engagement page. Files `POST` to
   `/api/engagements/<c>/<p>/upload` (multipart); the web app streams each to
   `raw/engagements/<c>/<p>/inventory/` (or `/docs/` by a toggle). Server-side upload
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
   | **Disposition & waves** | "Score the 6R dispositions and build the migration wave plan." |
   | **Run-rate cost** | "Break down the Azure run-rate cost with the top drivers and the range." |
   | **Client deck (PPT)** | "Assemble the estimate and generate the PowerPoint deck." |
   | **Excel workbook** | "Generate the Excel workbook with the calculation appendix." |
   | **Studio deck** | "Generate the studio-grade client deck." → E11.9 container tool |
   | **What's missing?** | "What data is missing or low-confidence, and what should I ask the client for?" |
   | **Explain a figure** | "Explain figure F… — where did it come from and under what assumptions?" |

   Cards are config (`src/web/prompt_cards.json`) so pre-sales can add their own.

### 4.6 Studio-deck container (E11.9 — makes E5.6 concrete)

A small **Container App** (`ca-deckgen`) running Node + `presentation-skill` +
`ppt-master` + LibreOffice/Poppler. One OpenAPI operation:
`POST /generate_studio_deck { engagement, style? }` → pulls
`answers/engagements/<c>/<p>/estimate/latest.json`, authors `outline.json`, renders via
pptxgenjs, runs `qa_gate.py`, writes `estimate/studio.pptx` back, returns the blob path.
Registered as an agent tool. min-replicas 0 (scale-to-zero — it runs seconds per deck).

### 4.7 Security & isolation

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
| **E11.6** | Dashboard — engagements home, "New engagement" form, upload panel, "Start analysis" / "Produce estimate" | P0 | A pre-sales user with no CLI creates an engagement, uploads RVTools + a CMDB CSV, clicks Start, and sees a data-quality summary — in one session |
| **E11.7** | Dashboard — embedded engagement-scoped chat + configurable prompt cards (`prompt_cards.json`) | P0 | Clicking "Full estimate" produces and publishes the estimate for the open engagement and only that engagement |
| **E11.8** | `publish_estimate` + dashboard read/write the engagement path; `history/<ts>/` snapshots; a version picker on the dashboard | P1 | Re-publishing keeps the prior version; the dashboard can show any snapshot |
| **E11.9** | Studio-deck container (`ca-deckgen`) — `presentation-skill` + `ppt-master` as an OpenAPI tool; "Studio deck" prompt card | P1 | The agent calls it; a `qa_gate`-passing `studio.pptx` lands in the engagement folder |
| **E11.10** | Access control — `visibility` on `_engagement.json`, list filtering, audit trail of runs/publishes | P1 | A user sees only their own + group-shared engagements; every run is attributable |
| **E11.11** | Migration + back-compat — fold the current single-tenant `raw/inventory/` + `answers/estimate/latest.*` + un-keyed SQL into `_default_/_default_` (or drop, synthetic); one-release shim | P1 | Existing deploy keeps working through the transition; docs updated |
| **E11.12** | E5.4q — `.xlsx` formulas-not-literals + a headless-LibreOffice recalc **CI gate**; `.docx` US-Letter DXA + tracked-changes-ready + `accept_changes` | P1 | Change an input in the workbook → the model re-flows; recalc reports 0 errors; architect edits are Word tracked changes |
| **E11.13** | Evals — golden per-engagement isolation tests (two synthetic estates, assert no bleed); a `run_engagement` end-to-end scenario in the harness | P0 | A regression that leaks one engagement's rows into another fails CI |

**Infra deltas (`infra/resources.bicep`):** Event Grid subject filter; a `ca-deckgen`
Container App + its ACR image + an OpenAPI tool env var; no new data stores for v1.

**Not in scope here:** changing the estimation maths, the CAF landing-zone logic, or the
eval-harness gates — E11 is plumbing + UX + tenancy around the existing engine.

---

## 6. PDCA cadence

| Cycle | Scope | Exit |
|---|---|---|
| **C18** | E11.1 + E11.2 + E11.3 (engagement model, ADLS layout, SQL `engagement_id` + migration) | `create_engagement` works; two engagements' data is isolated in SQL and blob; tests |
| **C19** | E11.4 + E11.5 + E11.13 (ingestion + every tool scoped; isolation evals) | `run_engagement` ingests one folder; every tool rejects a missing `engagement`; isolation eval green |
| **C20** | E11.6 (dashboard: home, new-engagement, upload, start analysis) | A no-CLI user creates an engagement, uploads, and runs analysis from the browser |
| **C21** | E11.7 + E11.8 (engagement-scoped chat + prompt cards; versioned publish) | Prompt cards drive per-engagement outcomes; dashboard shows the right engagement's estimate |
| **C22** | E11.9 + E11.12 (studio-deck container; xlsx/docx polish + CI recalc gate) | "Studio deck" card produces a `qa_gate`-passing deck; recalc gate live |
| **C23** | E11.10 + E11.11 (access control, audit, migration + shim, docs) | Visibility enforced; the old single-tenant deploy migrates cleanly |

Each cycle logged in [`pdca-log.md`](pdca-log.md) (Plan / Do / Check / Act).

---

## 7. Open questions for the sponsor

1. **Isolation tier** — single DB + `engagement_id` column for all (cheapest), or
   DB-per-engagement for regulated clients (the `--tier regulated` switch)? Plan assumes
   the column, switch available.
2. **Who may create engagements / see them** — any authenticated user, or a named
   pre-sales group? Plan assumes creator + optional group share.
3. **Retention** — how long do closed engagements' data and deliverables stay before
   `azd`-independent cleanup? Plan assumes a documented manual close-out + a
   `history/` snapshot kept.
4. **Studio deck** — is the Node side-car (`ca-deckgen`) acceptable operationally, or
   should E5.6 stay "architect runs it locally" for now? Plan builds the container in C22
   but it can be deferred.
