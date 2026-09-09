# Landfall 5/5 — PDCA delivery log

Operating model: [`landfall-5x5-prd.md` §7](landfall-5x5-prd.md). Tracker:
[`tracker.md`](tracker.md). Newest cycle first.

---

## Cycle 27 — target landing-zone diagram, deterministic (E11.22, core — no new infra)

**Date:** 2026-09-09 · **Owner:** Azure AI Architect + App Eng ·
**Tracker:** E11.22 (core done; C27b = the `ca-drawio` container) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.10 + decision 9 —
a deterministic driver over the diagram engine; the agent does not free-draw.

### Plan

`design_landing_zone` produces the whole topology as JSON but the deliverable had no
picture of it — the deck's hub-spoke slide is hand-drawn and generic. §4.10's design is
a deterministic `design → draw.io` mapping (the skill's rules coded in `lz/diagram.py`)
feeding a `ca-drawio` container that renders `.svg`/`.png`. The container needs
`azd provision` (new Container App) which runs the schema-drop postprovision hook — so
this cycle ships **the deterministic core with zero new infra**: emit the `.drawio` XML
directly and render it in the browser with the draw.io viewer. The container (server-side
raster + deck embed) becomes C27b, gated on a safe provision.

### Do

- **`src/api/lz/diagram.py`** (pure, no network) — `build_drawio(design)` → a valid
  `<mxfile>` document: the hub VNet + every spoke as a swimlane group, hub components and
  a per-spoke workload cell inside, `orthogonalEdgeStyle` edges for peering /
  ExpressRoute-VPN (on-prem) / DR (dashed), labelled with the real `region` / `dr_region`
  and the actual hub components. Palette + swimlane nesting + "no hand-routed edges" from
  the vendored rules. `_esc` escapes `& < > " '`. Also `mcp_plan(design)` (the ordered
  create-group / add-cell-of-shape / add-edge / export-xml plan for the engine) +
  `_shape_for()` (component → `mxgraph.azure.*` key) + `diagram_meta()`.
- **`build_landing_zone_diagram` Function** (`lz/functions.py`, sync — no queue): reads
  the design from the body (`design` / `applications`) or the engagement's
  `tools_raw.json`; writes `estimate/landing_zone.drawio` + `landing_zone_diagram.json`;
  409 if there's no design. `GET ?engagement=` returns the meta. `src/api/openapi/
  build_landing_zone_diagram.json`; `_OPENAPI_TOOLS` entry + a system-prompt line
  ("after design_landing_zone, call build_landing_zone_diagram") + a "Landing-zone
  diagram" prompt card. `publish_estimate` regenerates the diagram from
  `body["landing_zone"]` (best-effort).
- **Web** — `GET /dashboard/landing-zone-diagram?e=` serves the XML (`?download=1` →
  file); the dashboard LZ card `renderLZDiagram()` embeds it in an
  `viewer.diagrams.net/?...#R<xml>` iframe (client-side, no container) + a Download
  .drawio link.
- **`docs/diagram-authoring/`** — `xml-authoring-rules.md`, `azure.md` (palette + shape
  map), `layout-antipatterns.md`, vendored with source + retrieval date.
- **`tests/test_lz_diagram.py`** (13) — valid XML + structure (base layer, swimlanes,
  edges, every cell parented), determinism, no-DR, thin design, regulated colour, XML
  escaping, `mcp_plan` + `meta`; the Function route (inline / stored / 409 / design-from-
  apps / GET meta), `publish_estimate` regenerates it, and the web serves + embeds it.

### Study

| # | Result |
|---|---|
| sample estate | `build_drawio` → 37 cells, 7 edges, hub + 5 spoke swimlanes, `swedencentral` / `westeurope` labelled; parses as well-formed XML; opens in draw.io desktop |
| determinism | same design → byte-identical XML |
| wiring | `publish_estimate` writes `landing_zone.drawio`; `GET /dashboard/landing-zone-diagram` serves it; the card renders it in the viewer iframe |
| suite | **328 pytest** (+13 −0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c27-landing-zone-diagram`, merged to `main`, pushed, deployed
  (api 1m47s + web 1m38s + `create_agent.py`); CI `evals #49` green; **live-verified** —
  the agent called `build_landing_zone_diagram` for `_default_/_default_` and stored the
  `.drawio` (swedencentral, 9 spokes).
- **Follow-up landed same day (`c27-svg`):** `diagram.py::build_svg(design)` — a
  deterministic **self-contained SVG** (swimlane boxes, component rows, peering / hybrid /
  DR edges, region label; no external refs). `build_landing_zone_diagram` + `publish_estimate`
  now store `landing_zone.svg` too; `GET /dashboard/landing-zone-diagram` serves it by
  default (`?fmt=drawio` for the source) and the dashboard renders it **inline** — the
  `viewer.diagrams.net` iframe drops to a fallback. `tests/test_lz_diagram.py` → 15; 330 pass.
- **C27b landed same day (`c27b-drawio-container`) — imperatively, no `azd provision`:**
  `src/drawio/` is a ~30 MB FastAPI + **CairoSVG** container — one endpoint, `POST /render`
  (SVG bytes → PNG), key-guarded, **external ingress** (the Function App shares no VNet with
  the Container Apps environment — the C25 finding). Stood up with `az acr build` +
  `az containerapp create` (`ca-drawio-*`, minReplicas 0) so a schema-dropping `azd provision`
  was avoided entirely. `src/api/lz/render.py::rasterize(svg)` is best-effort — a no-op when
  `DRAWIO_RENDER_URL` is unset, so nothing changes for local/CI. `build_landing_zone_diagram`
  + `publish_estimate` store `landing_zone.png`; `export.py` `to_pptx` swaps its hand-drawn
  hub-spoke slide for the render and `to_docx` embeds it under the landing-zone section
  (`_diagram_png` decodes the b64 payload `publish_estimate` attaches to the package); web
  serves `?fmt=png`. `infra/resources.bicep` gains a param-gated `drawioApp`
  (`deployDrawio=false` — imperative today, flip to reconcile into IaC) + `azure.yaml` a
  `drawio` service. `tests/test_lz_render.py` (7). **337 pass**, evals PASS, no drift.
- **C27b (deferred, needs `azd provision`):** the `ca-drawio` Container App
  (`simonkurtzmsft/drawio-mcp-server` mirrored to ACR + `drawio-export`) for server-side
  `.svg`/`.png`, the `to_pptx` / `to_docx` SVG embed (replacing the hand-drawn slide),
  the full `mxgraph.azure.*` icon set via the engine, and the optional raw MCP tool.
  Bicep + `DRAWIO_MCP_URL`. Do the provision with `postprovision:` commented out in
  `azure.yaml` (schema DROP), then `git checkout azure.yaml`.

---

## Cycle 20b — discovery questionnaire, served and round-trippable (E11.25)

**Date:** 2026-09-09 · **Owner:** App Eng + Pre-sales Architect ·
**Tracker:** E11.25 (done) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.5b + decision 13 —
the questionnaire is delivered *through the solution*: served, exported for offline
completion, re-imported, and its answers feed the estimate's assumptions.

### Plan

`docs/discovery-questionnaire.html` was a static file with no route. It carries the
inputs the inventory can't — compliance scope, RPO/RTO, licensing, cutover windows —
so it needs to be a first-class artifact: a URL to send the client, a Word/Excel
export they fill offline, and an importer that turns the returned file into structured
answers the estimate cites.

### Do

- **`scripts/gen_discovery_catalog.py`** — parses the HTML (92 questions, 14 sections)
  into `src/web/discovery_catalog.json` and copies the HTML byte-for-byte to
  `src/web/questionnaire.html` (the web container ships only `src/web/`). A hand-kept
  `FEEDS` map marks the ~15 questions that ground a model input. `tests/test_discovery.py`
  fails on drift — same pattern as `evals/SCORECARD.md`.
- **`src/web/discovery.py`** — `render_xlsx` / `render_docx` (blank, or pre-filled from a
  saved `_discovery.json`); `parse_upload` (xlsx via openpyxl, docx via python-docx —
  matches rows/paragraphs on the question codes, ≥3 hits = the template, skips headings
  and the "…" placeholder); `gaps` (unanswered MUST/SHOULD by section); `discovery_record`
  (the `_discovery.json` payload). `python-docx` added to `src/web/requirements.txt`.
- **Web routes** — `GET /questionnaire` (serves the HTML), `GET /questionnaire.{xlsx,docx}`
  (`?e=` pre-fills), `GET /api/engagements/<c>/<p>/discovery` (answers + gap list). The
  **upload route** now recognises a completed questionnaire dropped into `docs/` and
  writes `raw/engagements/<c>/<p>/_discovery.json`, returning `discovery: {answered, gaps}`.
- **API** — `deliverable/functions.py::_discovery_for(engagement)` reads `_discovery.json`
  and injects it into `assemble_estimate` / `publish_estimate`. `assemble.py` folds each
  answer into the register as a **cited `discovery:<id>` assumption** and the top-12
  unanswered MUST questions as `discovery:*` data-gaps (`+N more` line past 12);
  `register.discovery` carries the headline. `export.py` renders the headline in the
  register section.
- **Surfacing** — dashboard register card shows the discovery headline + an "ask the
  client" link; `create_agent.py` gains a prompt line (read `register.discovery` +
  `discovery:*` gaps for "what's missing?"); the "What's missing?" prompt card + the
  intro capability list mention `/questionnaire`.
- **`tests/test_discovery.py`** (15) — catalog drift gate, catalog shape, xlsx + docx
  round-trip, blank-export sanity, non-questionnaire rejection, `gaps`, `discovery_record`,
  assemble folds it (cited + capped) / is unchanged without it, and the web routes
  (serve, export both formats, upload → `_discovery.json` → `GET …/discovery`).

### Study

| # | Result |
|---|---|
| round-trip | fill 4 answers → export .docx → re-upload → `_discovery.json.answer_map` identical; same for .xlsx |
| template detection | a `servers.csv` / a blank export / a fake `.pdf` are all correctly *not* the template |
| estimate wiring | `assemble_estimate` → `register.assumptions` has `A1 discovery:SC1`, `A2 discovery:R1`; 12 `discovery:*` "Ask the client" gaps + a "+N more"; `register.discovery.headline` = "4/92 answered · 34 required questions still open" |
| exports | docx / xlsx / pptx all render with the discovery lines |
| suite | **315 pytest** (+15 −0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c20b-discovery-questionnaire`, merged to `main`, pushed. Deploy:
  `azd deploy api` + `azd deploy web` + re-run `create_agent.py` (prompt changed).
- **Carry:** `design_landing_zone` doesn't yet *consume* the compliance/DR answers
  (it only lands them as cited assumptions via `assemble`) — a follow-up could have
  `SC1` seed a regulated spoke and `R1`/`R3` drive the DR block. PDF questionnaires
  aren't parsed (the route says so). The `_discovery.json` write is last-write-wins.

---

## Cycle 28 — `design_landing_zone` scored against the Azure (AI) Landing Zone design checklist (E11.23)

**Date:** 2026-09-09 · **Owner:** Azure AI Architect + Cloud Architect ·
**Tracker:** E11.23 (done) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.11 + decision 11 —
the checklist is a *vendored design reference* the deterministic tool applies; the
agent does not re-derive architecture.

### Plan

`design_landing_zone` already derives the whole topology from the portfolio (MG
hierarchy, spokes, IP plan, policy baseline, identity, DR). The gap for a funding /
architecture review is *attribution*: nothing said the design conforms to Microsoft's
own guidance, and nothing surfaced what it deliberately leaves for the build phase.
Same pattern as MEG and the two diagram skills — vendor the checklist, code the rules,
emit a conformance section.

### Do

- **`docs/lz-design/{alz-checklist,ai-lz-checklist}.md`** — the Azure Landing Zone
  design checklist (10 domains: Identity · Resource Organization · Networking ·
  Security · Governance · Management · Monitoring · Reliability · Cost · Data) and the
  AI-LZ overlay, distilled with source URLs + a 2026-09-09 retrieval date. A reference,
  not a live doc.
- **`src/api/lz/conformance.py`** (pure) — ~34 ALZ rules + a 10-item AI-LZ overlay.
  Each rule reads the design's *structured* output (`management_groups`, `hub.components`,
  `policy.baseline/regulated_overlay`, `dr`, `subscriptions`, `connectivity`, …) — never
  prose — and returns `met` / `partial` / `gap` / `n/a` + evidence + a recommendation.
  `n/a` (no regulated scope → SEC-2/3, GOV-3; no AI workloads → the whole overlay) is
  excluded from the met/total ratio. `ai_workloads_present()` sniffs app
  `workload_type` / name / tech-stack for AI/ML/analytics tokens.
- **`design_landing_zone`** returns `checklist_conformance[]`, `checklist_summary`
  (`{met, partial, gap, na, total, met_pct, headline}`), `checklist_gaps[]`,
  `ai_lz_applicable`. Wrapped in try/except — a rule error never breaks the design.
- **`assemble.py`** — `_body_lz` carries a `design_conformance` block (headline +
  gap list); a new `lz_conformance` headline figure ("N met of M checklist items").
- **`export.py`** — the LZ section body lines and the pptx LZ slide render the headline
  + the top gaps with recommendations.
- **`dashboard.html`** — the Landing zone card shows a `N/M checklist items met` pill,
  an `AI-LZ overlay` pill when applicable, and a "gaps to close" `<details>` drawer.
- **`scripts/create_agent.py`** — system-prompt line: quote `checklist_summary.headline`
  and list `gap` rows when the user asks about the target architecture.
- **`tests/test_lz_conformance.py`** (13) — well-formed items, met↔no-recommendation,
  determinism, baseline meets identity/resource-org, no-DR → REL-1 gap, regulated rows
  n/a without a scope, AI overlay only with AI workloads (AILZ-4 met from the baseline
  managed identity), n/a excluded from the ratio, thin-design robustness, assemble +
  all three exports surface it, checklists vendored.

### Study

| # | Result |
|---|---|
| sample estate (PCI app, no AI) | `17/30 checklist items met · 7 gaps`; gaps are the build-time items — central Log Analytics workspace, diagnostic-settings policy, Update Manager, platform alerting, budgets/cost-alerts |
| + an ML workload | `ai_lz_applicable: true`, 10 AI-LZ rows scored (AILZ-4 met, 9 gaps — Foundry hub, PTU plan, private endpoints for AI, APIM gen-AI gateway, Content Safety, …) |
| determinism | same input → byte-identical `checklist_conformance` |
| deliverables | docx / pptx / xlsx all render; dashboard card shows the pill + drawer |
| suite | **300 pytest** (+13 −0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c28-lz-checklist-conformance`, merged to `main`, pushed. Deploy:
  `azd deploy api` + `azd deploy web` + re-run `create_agent.py` (prompt changed).
- **Carry:** COST-1 and the monitoring rows are advisory (`partial`/`gap` with a
  recommendation) — they could go `met` if `conformance.evaluate` also read the
  `compute_cost` / a monitoring config; keep design-only for now. Re-vendor the
  checklists when CAF / AI-LZ guidance changes (they carry a retrieval date).

---

## Cycle 23 — engagement access control + audit + pre-E11 migration (E11.10, E11.11)

**Date:** 2026-09-09 · **Owner:** App Eng + Azure AI Architect ·
**Tracker:** E11.10, E11.11 (done) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §7 decision 2 —
creator + optional group share, recorded on `_engagement.json`.

### Plan

C18–C22 built per-engagement tenancy (ADLS layout, SQL RLS, hard `engagement`
scoping) but nothing yet stopped one signed-in user from *listing* or *opening*
another user's engagement, and there was no attributable record of who ran or
published what. Two gaps to close: (E11.10) visibility filtering + an audit trail;
(E11.11) a clean path for a deployment that predates the engagement layout.

### Do

- **`src/api/engagement.py`** — `normalize_visibility` (`owner` | `group:<id>` |
  `all`, fail-closed), `can_view(manifest, viewer, groups)`, `principal_from_easyauth`
  (decodes the base64 `x-ms-client-principal`, incl. `groups` claims). Mirrored, self-
  contained, in **`src/web/access.py`** (the web container doesn't ship `src/api`).
- **`src/api/audit.py`** — `record` / `read` over
  `answers/engagements/<c>/<p>/_audit.jsonl` (append-only, best-effort). Wired into
  engagement-create, `run_engagement`, `publish_estimate`. `GET …/audit` on both the
  Function (`engagements.py`) and the web app, newest-first.
- **Enforcement** — Function `_list` + `engagement_one` (403); web `engagements_list`,
  every engagement-scoped read via `_engagement(customer, project, request)` (404 —
  indistinguishable from absent), and the `/dashboard/*` routes via `_guard_eid`.
- **`scripts/migrate_to_default_engagement.py`** — dry-run by default; `--apply` moves
  the flat `raw/inventory/` + `raw/docs/` + `answers/estimate/` blobs under
  `engagements/_default_/_default_/…`, writes the seed `_engagement.json`
  (`visibility: all`), and backfills un-keyed rows across the 6 SQL tables (RLS policy
  toggled off around the `UPDATE`). Idempotent.
- **Shim** — `_read_estimate_blob` still resolves the pre-E11 flat `estimate/` path for
  one release and logs a deprecation warning when it does.
- **Docs** — `operating-sop.html` gains an "Access control & audit" ref section + an
  operator migration step (v1.1).
- **Tests** — `tests/test_access_control.py` (can_view matrix ×2 modules, principal
  decode, Function list filtering + groups, 403; web list + 404 guard + dashboard 403 +
  audit route), `tests/test_audit.py` (record/read roundtrip, resilience, publish wires
  it), `tests/test_migration.py` (dry-run is a no-op, apply moves + seeds, idempotent).

### Study

| # | Result |
|---|---|
| visibility matrix | `owner` → creator only; `group:<id>` → creator + members; `all` → anyone; unknown value → fail-closed to `owner`; no Easy Auth header → filtering off (local deploy sees all) |
| enforcement | Function `_list` returns own + public + matched-group only; `engagement_one` 403; web engagement-scoped reads + `/dashboard/data` 404/403 for a non-viewer |
| audit | create / `run_engagement` / `publish_estimate` each append an `{at, actor, event, …}` line; `GET …/audit` returns them newest-first |
| migration | dry-run prints the plan and changes nothing; `--apply` moves 4 blobs + writes the manifest; second `--apply` is a no-op |
| suite | **287 pytest** (+30 -0), evals **PASS**, scorecard no drift |

### Act

- Committed on `c23-access-control-migration`, merged to `main`, pushed. Deploy: `azd
  deploy api` + `azd deploy web` + re-run `create_agent.py` (no agent-prompt change this
  cycle — the audit route is not an agent tool).
- **Carry:** `_audit.jsonl` is last-write-wins (fine for the pre-sales single-writer
  case; add an append lease if it goes concurrent); `group:` needs the app registration
  to emit `groups` claims — document in DEPLOY.md; a dashboard "audit" tab; run the
  migration script live against `rg-landfall` (SQL side is a no-op there — C18 already
  re-loaded the sample estate as `_default_/_default_`).

---

## Cycle 26 — per-engagement conversation memory + engagement export / import (E11.26)

**Date:** 2026-09-08 · **Owner:** Azure AI Architect + FinOps + App Eng ·
**Tracker:** E11.26 (done, deployed) · **Decisions:**
[`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.12 + decision 14 —
conversation memory is the Responses API's own server-side store, keyed per
engagement in blob; **not** the preview managed Memory feature.

### Plan

Sponsor: *"memory should be under the Foundry agent"* — the chat only remembers the
current browser tab today (lost on New chat / close / second device, not tied to the
customer/project). Also: the solution is deployed with `azd up` and **torn down with
`azd down` to save cost**, so it must be **portable** — an engagement should survive a
teardown/redeploy or move between deployments.

Panel verdict (AI architect / cloud architect / FinOps / director):

- **Not** the new managed Foundry Memory feature — it needs the **Standard agent setup
  backed by Cosmos DB**; Landfall runs a **low-code prompt agent** on purpose. Cosmos
  carries a 24/7 RU floor (breaks near-free), it's preview (API churn hurts a
  redeploy-months-later story), and it's the wrong model: a **funding POE must be
  deterministic** — the agent's context is the uploaded inventory + `_discovery.json` +
  the published estimate, which it already reads through tools. Don't make the LLM
  *remember* a compliance scope; make it *look it up*.
- **Do** persist the conversation server-side per engagement. The Responses API already
  stores the chain in the Foundry project (`store=true`); keep the **pointer + a
  transcript** in the engagement's own blob. Zero new resources.
- **Do** add engagement **export / import** — the real portability piece for a
  tear-down-friendly tool.

### Do

- **`src/web/app.py`**
  - `answers/engagements/<c>/<p>/_chat.json` = `{current_response_id, started_at,
    turns[], archived[]}`. `/api/chat` reads the pointer from there (not the browser
    body), chains `previous_response_id`, appends the user + assistant turns, saves.
    Falls back to a body `thread_id` only when unscoped.
  - `GET  /api/engagements/<c>/<p>/chat` — the transcript (page renders it on load /
    engagement switch).
  - `POST /api/engagements/<c>/<p>/chat/new` — archive the current thread into
    `archived[]` (summary + last response id — the Foundry chain stays retrievable),
    start fresh.
  - `GET  /api/engagements/<c>/<p>/export` — one `.zip`: `raw/_engagement.json` + every
    `raw/inventory|docs/*` + every `answers/estimate/*` + `answers/_chat.json` +
    `export.json`. 250 MB cap; skips empties + HNS directory markers.
  - `POST /api/engagements/import` — restore a `.zip` (validates `export.json`, slug-
    checks the id, blocks `..`/absolute paths); **409 unless `overwrite=true`**.
  - `_SEG_RE` relaxed to allow the `_default_` sentinel's underscores (it was 404-ing).
- **Chat page** — loads + renders the engagement's saved transcript on select; "New
  chat" archives server-side; header gains **↓ export** (when an engagement is active)
  and **↑ import** (hidden file input); dropped the `localStorage` thread id (the
  engagement id still persists locally so the page reopens where you left off).
- **`tests/test_engagement_memory.py`** (6) — chain continuity, transcript GET, archive-
  not-destroy, export/import round-trip, 409-on-existing, non-zip rejection.

### Study

| # | Result |
|---|---|
| conversation continuity (live, real agent) | turn 1 "how many prod servers?" → *173*; turn 2 "**their** total vCPU?" → *1,436* — the agent resolved "their" from the stored chain, i.e. memory works |
| persistence | `_chat.json` written to `answers/engagements/_default_/_default_/_chat.json`, 4 turns + pointer; a `GET …/chat` reload returns them |
| New chat | archives to `archived[]` with the last response id; next turn starts a fresh chain (no `previous_response_id`) |
| export | live: 2.54 MB `.zip`, 12 members — `raw/_engagement.json`, `answers/_chat.json`, `answers/estimate/{latest.*, landing_zone.*, tools_raw.json}` |
| import | round-tripped a re-keyed engagement; imported `_chat.json` had all 4 turns; existing id → **409**, `overwrite=true` → 201 |
| tests | **208 pytest** (+6) + 32/8/30 evals green |
| cost | **no new Azure resources**; nothing added to the `azd up` path |

### Act

- Committed + pushed; deployed `web`. PDCA log + PRD §4.12 + decision 14 + work item
  E11.26 + `INSTALL.md` note ("export engagements before `azd down`, import after
  `azd up`") — *INSTALL note still to write*.
- **Carry:** last-write-wins on `_chat.json` (fine for one pre-sales user; add an ETag
  check if it ever goes multi-user); an "archived threads" viewer on the dashboard;
  re-key on import (import under a *new* customer/project, not just the original id);
  a one-click "export all engagements" before teardown.

---

## Cycle 25 — POE pipeline live (async) + engagement upload panel (E11.16, E11.6 part, E11.24)

**Date:** 2026-09-08 · **Owner:** App Eng + Azure Pre-Sales Architect + Platform Eng ·
**Tracker:** E11.16 (async — done, live), E11.20 (done), E11.6 (upload panel — done),
E11.24 (upload confirmation — done); E11.19 (adapter accuracy — open) ·
**Decisions:** [`engagement-workspaces-prd.md`](engagement-workspaces-prd.md) §4.5a
(upload: server-side, content-sniffed, per-engagement-isolated, visible confirmation),
§4.6 + decision 10 (ca-calc is queue-decoupled), decision 12 (upload).

### Plan

Two things. **(1)** Get the Pricing Calculator POE actually working: C24 built the
pieces but a live smoke showed the agent's `build_calculator_estimate` call returning
502. **(2)** A pre-sales architect with no CLI must be able to upload the client's
server + application inventory (`.csv`, `.xlsx`, …) from the dashboard into a **dedicated
per-customer/project ADLS folder**, with a **visual indication** each file landed, and
outputs kept in a separate folder for the same engagement.

### Do

**POE async (E11.16).** Root cause of the 502: the Flex Consumption Function App shares
no VNet with the Container Apps Environment, so it can't reach `ca-calc`'s internal
ingress at all — *and* a ~55-line Playwright drive overruns the ~230 s Functions HTTP
limit regardless. Rebuilt around a **storage queue**:

- new `calc-jobs` queue (Bicep). `build_calculator_estimate` POST now stages the spec
  to `{prefix}/_calc_spec.json`, writes `landing_zone.json` status `building`, drops one
  `calc-jobs` message, and returns **202**. New `GET ?engagement=` status route +
  `get_calculator_estimate` OpenAPI tool for polling; agent system-prompt reworked
  ("the POE builds in the background — watch the dashboard").
- `src/calc/worker.py` — `consume_forever()`: `DefaultAzureCredential(uami)` +
  `QueueClient`, drains a message, reads the spec, `build_estimate`, parse + reconcile,
  writes `landing_zone.{xlsx,json,png}` (ready|failed) to the engagement folder itself,
  deletes the message either way. `asyncio.wait_for(..., 1500 s)` budget. `app.py`
  lifespan starts it; `minReplicas: 1` (KEDA queue-scale-to-zero deferred — the MI
  scale-rule auth shape isn't in this Bicep type version and shared-key auth is off).
- Dashboard POE card renders `building` (auto-refresh) / `failed` / `ready`.
- `azure` SDK HTTP logging → WARNING (it was drowning the worker's own logs).

**Upload panel (E11.6 / E11.24).**

- `src/web/uploads.py` (pure, 5 tests) — `classify(name, head)` checks type by **magic
  bytes + structure**, not extension: `.csv/.tsv/.json/.xlsx/.xls/.zip` → `inventory/`,
  `.pdf/.docx/.md/.txt/.png/.jpg` → `docs/`; rejects `.xlsm/.docm`/exe/other archives
  with a reason. `peek(name, data)` — best-effort header + row count + a profile hint
  (RVTools vInfo / CMDB / server inventory / …). Caps: 100 MB/file, 250 MB/request,
  2 GB/engagement.
- `src/web/app.py` — `POST /api/engagements/{customer}/{project}/upload` (multipart,
  **streamed in 4 MB blocks** via `stage_block`/`commit_block_list`, slug-validated so a
  file can't be written outside its engagement prefix, magic-byte checked on the first
  8 KB before any block is committed, `peek` metadata stamped on the blob),
  `GET …/files` (manifest: name, kind, size, uploaded-at/by, profile, rows),
  `DELETE …/files/{name}`. New deps `python-multipart`, `openpyxl`.
- Chat page — an **Upload panel** appears whenever an engagement is selected: drag-drop
  or browse, auto/data/docs toggle, per-file rows that go
  `uploading NN%` → `checking…` → **✓ inventory · RVTools vInfo · 412 rows · 152 KB**
  (or `✗ <reason>`), a toast, and a **persisted manifest** that re-lists the folder on
  load with a remove button. Welcome copy points the user at it.
- Wrote the missing `_engagement.json` for the seed `_default_/_default_` engagement
  (`Sample Estate — Reference Migration`, `visibility: all`) so it shows in the picker.

### Check

| # | Result |
|---|---|
| POE end-to-end, live | agent → **202 in 10 s** → `calc-jobs` → `ca-calc` drove the real calculator (55 products) → genuine `ExportedEstimate.xlsx` (56 KB) + `.png` + `.json` at `answers/engagements/_default_/_default_/estimate/landing_zone.*` |
| POE reconciliation | **−73 %** ($26,314 calc vs $97,624 internal) — the ~14 unverified adapters added the products but didn't set quantities, so the calculator used defaults. Flagged `within_tolerance: false`. → **E11.19 is the open work** |
| queue consumer auth | `ca-calc` polls `calc-jobs` with the workload identity, HTTP 200, no shared key |
| upload — isolation | test: `servers.csv` → only `raw/engagements/contoso-ltd/dc-exit/inventory/servers.csv`, nowhere else; `../../etc/passwd` path → 404 |
| upload — validation | `.xlsm` → 415 "re-save as .xlsx"; `<html>` renamed `.xlsx` → 415 "doesn't look like a real .xlsx"; binary `.csv` → 415 |
| upload — confirmation | `peek` returns `RVTools vInfo · 412 rows` from a real vInfo header; xlsx row count via openpyxl |
| tests | **202 pytest** (+10 new: `test_upload.py`, `test_calc_service.py`, rewritten `test_build_calculator_estimate.py`) + 32/8/30 evals green |

### Act

- Committed + pushed: `c96be46` (queue decouple) → `3bc6ff7` (PRD) → this cycle's web
  upload commit. Deployed: `azd provision` + `azd deploy calc` + `azd deploy api` +
  `azd deploy web` + `create_agent.py` (16 OpenAPI tools).
- **Carry to C25b / next:** **E11.19** — verify every `ca-calc` product adapter against
  the live calculator so the reconciliation delta closes (the POE isn't submittable until
  it does). Then KEDA queue-scale-to-zero for `ca-calc`, the weekly adapter smoke, and
  `run_engagement` → `build_calculator_estimate` hook.
- **Carry:** wire the upload panel's manifest to a **"Start analysis"** button
  (`run_engagement`, E11.4) so uploaded files get ingested + DQ-reported per file;
  `.zip` expansion; the discovery questionnaire round-trip (E11.25).
- No maths, CAF logic or eval-gate changes — plumbing + UX only.

---

## Cycle 24 — Azure Pricing Calculator POE + chat engagement scoping (E11.15–E11.18, part E11.6/E11.7)

**Date:** 2026-09-08 · **Owner:** Azure Pre-Sales Architect + App Eng ·
**Tracker:** E11.15 (done), E11.16 (code done, deploy pending), E11.17 (done),
E11.18 (done), E11.6/E11.7 (chat engagement picker done) · **Decisions:**
[`engagement-workspaces-prd.md` §3.4 / §4.6](engagement-workspaces-prd.md) —
Microsoft migration-funding POE accepts only the calculator's own Excel; the end
user picks the target region.

### Plan

Sponsor: the landing-zone + workload cost estimate for a Microsoft funding
submission must be the **Azure Pricing Calculator's own Excel export**, per
engagement, on the dashboard, downloadable. Also: the user must not have to type
the `<customer>/<project>` engagement id, and needs a working-indicator + new-chat
+ prompt cards + a greeting in the chat UI.

### Do

- **`src/api/lz/calculator_spec.py`** (E11.15, pure, 21 tests) — `design_landing_zone`
  + `estimate_compute_cost` + `estimate_storage_cost` (+ `run_rate`) → a calculator
  **line-item spec with no prices**. Azure-region→calculator-code map (61 regions;
  an unsupported region raises at build), VM SKU→size slug, disk tier→module,
  storage category→module (incl. ANF), LZ platform components→modules (Bastion /
  Firewall / DDoS / DNS / ExpressRoute / VPN GW / 2× AD DCs / Log Analytics /
  Key Vault / egress Bandwidth), ASR for tier-1/2 → DR region. Unpriceable items
  (Oracle, DR compute, no-module storage) → `spec["skipped"]` with a reason.
  `internal_monthly_estimate` kept for reconciliation.
- **`src/api/lz/calculator_export.py`** (E11.16, 4 tests vs the real fixture) —
  parse `ExportedEstimate.xlsx` → `{estimate_name, line_items[], total_monthly,
  licensing_program, created_at, …}`; `reconcile()` flags a >15% delta.
- **`src/calc/`** (E11.16) — **`ca-calc` Container App**: `mcr.microsoft.com/playwright/python`
  image, `POST /build` takes the spec, drives the live calculator (native value
  setter + `input`/`change` events — verified), sets estimate-name / currency /
  `discountLevel`, clicks `button.export-button`, returns `{xlsx_b64, screenshot_b64,
  applied[], skipped[]}`. **`adapters.py`** — 20 product adapters; VM + managed-disks
  verified end-to-end, the rest built from the observed module shape and marked
  `verified: false` (the E11.19 weekly smoke fills them in; an adapter that can't
  set a field records it, an adapter that errors → the line goes to `skipped`).
- **`src/api/lz/functions.build_calculator_estimate_route`** (E11.16/E11.18) —
  `POST /api/build_calculator_estimate {engagement}` → read `latest.json` +
  `tools_raw.json` + `_engagement.json` → `build_calculator_spec` → `POST CALC_URL/build`
  → parse + `reconcile` → write `answers/engagements/<c>/<p>/estimate/landing_zone.{xlsx,json,png}`.
  `publish_estimate` now also writes `tools_raw.json` (the raw tool outputs). 3 tests
  (fake blob + fake ca-calc).
- **OpenAPI** `build_calculator_estimate.json` + `create_agent.py` tool #13 + a
  system-prompt line ("for a Microsoft migration-funding POE, call
  `build_calculator_estimate` AFTER `publish_estimate`…").
- **Dashboard** (E11.17) — `src/web/app.py` `GET /dashboard/landing-zone` +
  `GET /dashboard/download/landing-zone-xlsx`; `dashboard.html` "Azure landing
  zone — Pricing Calculator POE" card ($X/mo, reconciliation delta chip, "not in
  the calculator estimate" drawer, Download Excel (POE), Open calculator ↗).
- **Chat engagement scoping** (E11.6/E11.7) — header **engagement `<select>`** +
  inline **"New engagement"** form (customer, project, **target region** from
  `/api/calc_regions` = the calculator's supported set, DR region, licensing
  program, currency). `src/web/app.py` lists/creates engagements **directly in
  blob** (`GET/POST /api/engagements`) — no Function-to-Function token.
  `/api/chat` takes `engagement` and **prepends a scoping instruction** to the
  input so the agent uses it for every tool call and never asks the user for the
  id. Selected engagement persists in `localStorage`. `_engagement.json` gains
  `target_region` / `dr_region` / `currency` / `licensing_program` /
  `target_region_calculator_supported`.
- **Chat UX** — "+ New chat" (clear + fresh session), animated "The estimator is
  working… (Ns)" bubble with the input disabled, a greeting (agent intro +
  capability list), clickable prompt cards from `src/web/prompt_cards.json`
  (`GET /api/prompt_cards`).
- **infra** — `ca-calc` Container App (internal ingress, scale-to-zero, 1 vCPU /
  2 GiB); `CALC_URL` on the Function; `azure.yaml` `calc` service;
  `main.bicep` / `main.parameters.json` param threading.

### Check

| # | Result |
|---|---|
| C1 | `build_calculator_spec` on the sample estate: 54 line items (31 VM groups, 8 disk tiers, DB storage, 11 platform lines, ASR), region `sweden-central`, `internal_monthly_estimate` ~$97.6k; Oracle + ANF + DR-compute in `skipped` |
| C2 | `parse_calculator_export` on the real `ExportedEstimate.xlsx`: name, 1 line item, `total_monthly` 5664.8, `created_at`; bytes + no-total-row fallback covered |
| C3 | `build_calculator_estimate_route` (mocked): spec is region-correct + price-free, calls ca-calc, stores `landing_zone.{xlsx,json,png}`, reconciliation delta computed |
| C4 | Chat page: engagement picker + New-engagement form present; `/api/chat` prepends `[Active engagement: …]`; `/api/calc_regions` returns 61 supported regions |
| C5 | **183 pytest + 32/8/30 evals green**; `az bicep build` clean |

### Act

- **Deployed 2026-09-08:** `azd deploy web` + `azd deploy api` + `create_agent.py`
  re-run (tool #13 attached). Chat picker + POE card live.
- **`ca-calc` NOT deployed yet** — needs `azd provision` (new Container App) +
  `azd deploy calc` (Playwright image build ~5–10 min). Until then
  `build_calculator_estimate` returns 503 ("CALC_URL not configured"). **C24 tail.**
- **C25:** E11.19 weekly Playwright adapter smoke; verify/complete the ~14
  unverified product adapters against the live calculator; wire the
  `run_engagement` → `build_calculator_estimate` hook; authenticated Save →
  `landing_zone_url` (deferred).
- **Known:** the `ca-calc` adapters beyond VM/disk are best-effort; a real POE run
  will surface which need field-map fixes. The spec builder's platform quantities
  (egress GB, LA GB, DNS zones) are heuristic — an architect reviews before submit.

---

## Cycle 18 — engagement tenancy foundation (E11.1 / E11.2 / E11.3)

**Date:** 2026-09-08 · **Owner:** App + Data Eng · **Tracker:** E11.1–E11.3 (done, live),
E11.4 / E11.5 (partial) · **Decisions:** [`engagement-workspaces-prd.md` §7](engagement-workspaces-prd.md)
(engagement_id column + RLS; creator+group visibility; studio-deck container deferred).

### Do

- **`src/api/engagement.py`** — engagement identity: `slug()`, `make_engagement_id()`,
  `normalize_engagement()` (`^[a-z0-9][a-z0-9-]{0,39}$` per segment), the per-engagement
  ADLS prefixes (`inventory_prefix` / `answers_prefix` / `estimate_prefix` /
  `ingest_report_prefix` / `history_prefix`), and `parse_inventory_blob()` (bare path or
  full Event Grid subject → `(engagement, filename)`). Pure, no Azure imports.
  `DEFAULT_ENGAGEMENT = "_default_/_default_"` folds the pre-E11 single estate.
- **`src/api/engagement_sql.py`** — `set_engagement(cursor, id)` → `sp_set_session_context`.
- **`scripts/schema.sql`** — `engagement_id NVARCHAR(120) NOT NULL` on all 6 tables;
  composite PKs `(engagement_id, <id>)` for servers/applications/storage; indexes on the
  IDENTITY tables; **Row-Level Security** — `dbo.fn_engagement_predicate` +
  `dbo.EngagementFilter` `SECURITY POLICY` filtering every table by
  `SESSION_CONTEXT('engagement_id')`. **No context set → no rows** (fail closed); every
  reader sets it first. INSERTs unaffected (loader writes `engagement_id` explicitly).
- **`src/api/ingest/loader.py`** — `engagement_id` first in every `TABLE_COLS` list;
  `load(table, rows, engagement, conn=None)` validates the id up front, sets the session
  context, keys the DELETE on `(engagement_id, source_file)`; `existing_keys(engagement)`
  and `write_log` scoped too.
- **`src/api/ingest/functions.py`** — blob trigger path
  `raw/engagements/{customer}/{project}/inventory/{name}`, engagement derived via
  `parse_inventory_blob`; `POST /api/ingest` takes `engagement`; DQ reports written to
  `answers/engagements/<c>/<p>/_ingest/`.
- **`src/api/engagements.py`** (new blueprint) — `POST /api/engagements`
  (slug + uniqueness → `_engagement.json` + folder skeleton; records `created_by` from
  the EasyAuth principal + `visibility`), `GET /api/engagements` (list, filtered by
  creator/visibility), `GET /api/engagements/{customer}/{project}`.
- **`src/api/tools.py`** — `query_inventory` takes `engagement` (defaults to
  `_default_/_default_`), sets the RLS context before running the model's SQL — this is
  what makes free-form text-to-SQL tenant-safe regardless of what the model writes.
- **`src/api/deliverable/functions.py`** — `assemble_estimate` / `export_estimate` /
  `publish_estimate` take `engagement`; `publish_estimate` writes to
  `answers/engagements/<c>/<p>/estimate/`; the package `meta.engagement` is stamped.
- **`src/web/app.py`** — `/dashboard/data` + `/dashboard/download/{fmt}` accept `?e=`;
  `_read_estimate_blob` tries the engagement path, then `_default_`, then the legacy
  `estimate/` path (back-compat for cycles 1–17).
- **OpenAPI specs** (`query_inventory`, `assemble_estimate`, `export_estimate`,
  `publish_estimate`) + `create_agent.py` SYSTEM_PROMPT gain the `engagement` argument /
  the ENGAGEMENT SCOPE rule.
- **`eventgrid.{sh,ps1}`** — inventory subscription subject → `/blobs/engagements/`.
- **Tests** — `tests/test_engagement.py` (22 cases: slugs, ids, prefixes, blob parsing,
  loader scoping); `test_dashboard.py` + `test_smoke_imports.py` updated. **150 pytest +
  32/8/30 evals green.**

### Check

| # | Result |
|---|---|
| C1 | `make_engagement_id("Contoso Ltd", "DC Exit 2027")` → `contoso-ltd/dc-exit-2027`; a duplicate becomes `…-2` |
| C2 | `loader.load` stamps `engagement_id`, sets the session context, keys the delete on `(engagement_id, source_file)`; a bad id raises before any DB call |
| C3 | `publish_estimate` with `engagement=contoso-ltd/dc-exit` writes only under that prefix; `meta.engagement` set |
| C4 | dashboard still reads the legacy `estimate/` path when nothing is published to an engagement |
| C5 | 150 pytest, evals 32/32 · 8/8 · 30/30 |

### Act

- **Deployed & verified live in rg-landfall (2026-09-08).**
  1. `azd deploy api` — new `query_inventory` / `publish_estimate` code live on `func-tmglwfatwcsa2`.
  2. `schema.sql` applied direct (mssql-python + `AzureCliCredential`) — the DROP+CREATE
     wiped the RLS-free tables and rebuilt all 6 with `engagement_id`, composite PKs, the
     `dbo.fn_engagement_predicate` TVF and the `dbo.EngagementFilter` `SECURITY POLICY`
     (`STATE = ON`); `id-landfall-tmglwfatwcsa2` re-granted `db_datareader + db_datawriter`.
     (`apply_sql.py` via `azd` hung on the serverless resume; ran the batches directly instead.)
  3. Sample estate re-loaded as `_default_/_default_` — servers 250 / applications 31 /
     dependencies 461 / storage 566 / performance 5190, every row stamped `engagement_id`.
  4. Estimate re-published to `answers/engagements/_default_/_default_/estimate/latest.{json,xlsx,docx,pptx}`.
  5. `azd deploy web` — dashboard now reads the engagement-scoped prefix (was pre-C18 code).
  6. Event Grid `landfall-inventory` subscription recreated with subject
     `/blobServices/default/containers/raw/blobs/engagements/`.
  7. `create_agent.py` re-run (managed auth) — agent picks up the ENGAGEMENT SCOPE prompt
     + the `engagement` arg on the 4 specs.
- **Live checks:**
  - RLS fail-closed: no session context → 0 rows; `acme/other` → 0 rows; `_default_/_default_` → 250 servers.
  - Live agent, `engagement=_default_/_default_`: "173 prod servers, 1,436 vCPU" (matches the local repro).
  - Live agent, `engagement=acme-corp/pilot`: "0 servers" — same `dbo.servers` table, isolated by context.
  - First agent call 502'd (Function cold start, 23 s); the retry and all subsequent calls succeed.
- **`schema.sql` still DROPs+recreates on every apply** — fine for `_default_` today, unacceptable
  once real engagements hold data. Tracked for C23 (migration + additive-only schema changes).
- **C19:** `run_engagement` bulk-ingest Function; tighten `engagement` to required + a
  run/publish audit line; `test_evals` per-engagement isolation cases (E11.13).
- **C20:** the dashboard UX (engagements home, new-engagement form, upload panel, start
  analysis).

---

## Plan note — 2026-09-08 — Epic E11 Engagement Workspaces raised

Sponsor: the solution must produce **per-customer / per-project** deliverables, driven
from the dashboard — enter customer + project, upload docs to a **unique ADLS folder per
engagement**, start the analysis, and use a **chat bot with predefined prompt cards**.
Also asked: can the four skills run "at the Foundry agent"?

**Decision & answer** (full write-up: [`engagement-workspaces-prd.md`](engagement-workspaces-prd.md)):

- **Skills cannot be loaded into a Foundry agent** — it has instructions + tools
  (OpenAPI/MCP/Code Interpreter/File Search) + the Responses API, no `SKILL.md` mechanism.
  `docx`/`xlsx` → design references baked into `export.py` (+ a CI recalc gate);
  `presentation-skill`/`ppt-master` → a **containerised OpenAPI tool** (`ca-deckgen`, Node
  toolchain) the agent calls. The agent orchestrates; `export.py` authors the files.
- **Move from "one deployment per engagement" to "one deployment, many engagements,
  isolated by an `<customer>/<project>` key"** — ADLS `raw|answers/engagements/<c>/<p>/…`,
  `engagement_id` column on all 6 SQL tables, `engagement` a required argument on every
  OpenAPI tool + the agent prompt. Hard isolation stays a `--tier regulated` option.
- New epic **E11** (13 items) added to `tracker.md`; scheduled as **PDCA cycles 18–23**.
  E11 is plumbing + UX + tenancy around the existing engine — no maths changes.

**Changes already on `main`** relevant to the sponsor's framing: cycles 15–17 (live
deploy + verification, E8.2 auth, `to_pptx` rebuilt as a narrative deck, generation-model
docs). Nothing multi-engagement is built yet.

---

## Cycle 17 — PowerPoint export rebuilt as a narrative assessment deck (E5.4 / E5.4q)

**Date:** 2026-09-08 · **Owner:** SWE + Writer · **Tracker:** E5.4 (pptx done),
E5.4q (in-progress) · **Trigger:** sponsor — "make the ppt highly professional with the
right visuals, icons, narrative, data, story; refer to Microsoft PPT and `Azure/migration`."

### Plan

`to_pptx` was a text dump on the stock template (11 slides, one big textbox each, no
charts, DRAFT on 1 slide). Rebuild it as a client-facing deck whose *narrative* follows
the Microsoft **Migration Execution Guide** lifecycle, with native charts and a design
system — still pure Python in `export.py` (the tool the Foundry agent calls; **no LLM
authors the file**).

### Do

- **`src/api/deliverable/export.py` — `to_pptx` fully rewritten** (~450 lines). 12 slides:
  cover · executive summary · approach (Assess→Optimise chevron flow) · current state ·
  landing zone · 6R disposition · wave plan · run-rate cost · effort · risk register ·
  next steps · traceability.
- Design system: Segoe UI, Azure palette (`0078D4` / `1B2A4A` / semantic green-amber-red),
  KPI tiles, section rules, a one-line takeaway band per slide.
- **Native charts from package data:** 2 doughnut (6R mix, cost drivers with an "Other"
  slice to 100%), 2 horizontal bar (servers-by-env, effort-by-workstream); a
  colour-coded wave table; a hub-and-spoke landing-zone diagram; numbered next-steps.
- **DRAFT watermark + page number + "Confidential" on every slide** (was 1 of 11);
  speaker notes on every content slide; every figure keeps its `F#` ref.
- `tests/test_export.py` — `test_pptx_opens_and_has_narrative_deck` rewritten (12 slides,
  ≥3 charts, a table, watermark on ≥11 slides). **127 pytest + 32/8/30 evals green.**
- Deployed (`azd deploy api`) and re-published to the live dashboard — the PowerPoint
  button on `/dashboard` now serves the 97 KB narrative deck.

### Check

| # | Result |
|---|---|
| C1 | `to_pptx` renders from the live package: 12 slides, 0 off-slide shapes, 4 charts + 2 tables |
| C2 | degraded package (failed compute tool) still exports all 3 formats |
| C3 | narrative reads end-to-end (exec summary sentence is generated from figures) |
| C4 | 127 pytest green; eval harness 32/32 · 8/8 · 30/30 |

### Act

- E5.4 `.pptx` **done**. **E5.4q** now covers the `.xlsx` (formulas-not-literals +
  LibreOffice-recalc CI gate) and `.docx` (US-Letter DXA + tracked-changes) polish — the
  `docx`/`xlsx` skill rules implemented in `export.py`, plus a CI recalc step.
- **E5.6** (studio deck via `presentation-skill` / `ppt-master`) stays a Phase-2 side-car —
  clarified in the docs that the Foundry agent is never in the generation path.
- Docs updated: audit block, `path-to-5x5` §"Deliverable polish" (generation model +
  role table), PRD E5.4 / E5.6, tracker.

---

## Cycle 16 — Function App EasyAuth, live (E8.2)

**Date:** 2026-09-08 · **Owner:** Security · **Tracker:** E8.2 (done) · **Trigger:**
sponsor said "yes" to the E8.2 follow-up from cycle 15.

### Plan

Turn on the Function App's built-in auth so no `/api/*` route answers anonymously, and
have the agent call every tool with its managed-identity token.

### Do

- **App registration** `landfall-func-tmglwfatwcsa2` (`920abc3e-35f7-4eac-a2e9-b11da46eecb5`),
  identifier URI `api://<guid>`, SP created.
- **Bicep** (`resources.bicep`): `allowedAudiences` now `[<guid>, api://<guid>]`;
  new `functionAuthAllowedClientIds` param → `defaultAuthorizationPolicy.allowedApplications`
  (empty = any tenant token for the audience); `excludedPaths` corrected (see Check).
  Threaded through `main.bicep`.
- **`create_agent.py`**: `AGENT_TOOL_AUTH=managed` now applies `OpenApiManagedAuthDetails`
  to **all 12** OpenAPI tools, not just `query_inventory` — EasyAuth is app-global, so
  it's all-or-nothing. Audience from `FUNC_AUTH_AUDIENCE`.
- `azd env set ENABLE_FUNCTION_AUTH true` / `FUNCTION_AUTH_CLIENT_ID` / `FUNC_AUTH_AUDIENCE`
  / `AGENT_TOOL_AUTH=managed`; `azd provision` (×2 — see Check).
- **DEPLOY.md** step 3 rewritten ("Harden the Function App").

### Check

| # | Result |
|---|---|
| C1 | Anonymous `curl` → **401** on `/api/vm_rightsize`, `/api/query_inventory`, `/api/azure_retail_prices`, `/api/publish_estimate` |
| C2 | Agent (Responses API, MSI) → calls `query_inventory` ×4 + `estimate_compute_cost` ×2, `status: completed`, sourced answer |
| C3 | Event Grid ingestion still fires — re-uploaded `raw/inventory/*`, DQ reports refreshed, 250 servers in SQL |
| C4 | Durable `start` unaffected (same `/runtime/webhooks/blobs` exclusion) |

**Bug found:** EasyAuth matches `excludedPaths` as **literal prefixes** — `"/runtime"`
alone did **not** exclude `/runtime/webhooks/blobs`, so the first provision broke the
Event Grid webhook (validation → 401). Fixed to
`["/runtime/webhooks/blobs", "/runtime/webhooks/durabletask"]`.
**Also:** a hand `az rest PUT` of `authsettingsV2` with only `globalValidation` wiped
`identityProviders` (PUT replaces the whole resource) → re-ran `azd provision` to
restore it declaratively. Lesson: only change `authsettingsV2` through Bicep.

### Act

- E8.2 **done and verified live.** E8 security epic now: E8.1/E8.3/E8.4 done, E8.2 done;
  E8.5–8.7 (private endpoints, thread-principal binding, signed data-handling statement)
  remain in Phase 2.
- **Follow-ups:** (1) set `functionAuthAllowedClientIds` to the Foundry MSI client id to
  restrict callers (Stage 2). (2) `schema.sql` drops+recreates every table on each
  `azd provision` — wipes loaded inventory; needs idempotent `IF NOT EXISTS` + a real
  migration path. (3) move `create_agent.py` to the postdeploy hook.

---

## Cycle 15 — first live deployment + verification pass (E1.6, E5.5, E5.4)

**Date:** 2026-09-08 · **Owner:** SWE · **Tracker:** E1.6 (done), E5.5 (verified),
E5.4 (verified) · **Trigger:** sponsor gave subscription access
(`f609eb5b…`, `rg-landfall`, swedencentral) — deploy cycles 5–14 and verify live.

### Plan

- `azd provision` + `azd deploy` to lift the running environment from ~cycle 11 to
  cycle 14 (SQL guard, Office exports, `publish_estimate`, dashboard, 12-tool agent).
- Verify the three items that need a real subscription: **E1.6** ingestion end-to-end
  (Event Grid + operator HTTP), **E5.5** `publish_estimate` → `/dashboard`, **E5.4**
  Office exports generated server-side.

### Do

- `azd provision` — Bicep idempotent; postprovision re-applied schema (7 batches via
  `apply_sql.py` — no sqlcmd), rebuilt the search index, recreated the agent.
- `azd deploy` — `src/api` (20 functions incl. the 8 new tool routes) + `src/web`
  (dashboard) live.
- Re-ran `create_agent.py` → agent **v4**, 14 tools (2 built-in + 12 OpenAPI), active.
- Recreated the `landfall-inventory` Event Grid subscription.
- Ingested the sample estate (`raw/inventory/*` → SQL): 250 servers / 31 apps /
  484 deps / 566 storage / 5190 perf rows; DQ reports in `answers/_ingest/`.
- `publish_estimate` (live) wrote `answers/estimate/latest.{json,xlsx,docx,pptx}`.
- Ran the web app against live storage: `/dashboard` 200, `/dashboard/data` returns the
  package, `/dashboard/download/{xlsx,docx}` stream with the right mime, bad fmt → 400.
- Agent smoke test (Responses API): "servers by env + rough 3yr-RI compute cost" →
  calls `query_inventory` then `estimate_compute_cost`, returns the
  Answer/Basis/Assumptions/Data-gaps/Confidence block. Numbers match direct SQL
  (250 / 1940 vCPU / 10 528 GB).

### Check — three bugs found and fixed

| # | Bug | Fix |
|---|---|---|
| B1 | `apply_sql.py` granted the workload identity `db_datareader` only; the ingestion loader needs INSERT/DELETE → every load failed `DELETE permission was denied`. | Grant `db_datareader` **+ `db_datawriter`**. `query_inventory` stays SELECT-only via `sqlguard.py` (code, not DB perm). Identity split tracked under E8. |
| B2 | `eventgrid.sh` run under Git Bash: MSYS rewrote `--subject-begins-with "/blobServices/…"` to `C:/Program Files/Git/blobServices/…`, so the inventory subscription matched nothing. | `export MSYS_NO_PATHCONV=1` / `MSYS2_ARG_CONV_EXCL="*"` + a post-create filter assertion in the script. |
| B3 | Text-to-SQL `SCHEMA_HINT` had no enum note for `powerstate`; agent guessed `= 'on'` (data is `poweredOn`/`poweredOff`) → "no servers". | Add value hints for `powerstate`, `dependencies.direction`, `dependencies.confidence`, `compliance_scope`. Redeployed; agent smoke test then correct. |

Serverless SQL auto-pause: first connection after idle returns "database is not
currently available"; a retry wakes it (~40 s). Expected, not a bug — noted for the SOP.

### Act

- **Verified live:** E1.6 (both ingestion paths), E5.4 (server-side Office export),
  E5.5 (dashboard reads the published package + downloads).
- **Still open:** **E8.2** — Function App EasyAuth (needs an Entra app registration +
  `AGENT_TOOL_AUTH=managed` re-run of `create_agent.py`); the func routes are anonymous
  today, guarded only by `sqlguard`. Next deliberate step.
- **Follow-ups:** `create_agent.py` should move to a **postdeploy** hook (on a first-ever
  `azd up`, `SERVICE_API_NAME` isn't set at postprovision time, so the OpenAPI tools are
  skipped — the WARN path — and need a manual re-run). Phase 1 tail unchanged
  (E4.3 / E6.2 / E1.7).

---

## Cycle 14 — assessment dashboard web app (E5.5)

**Date:** 2026-09-08 · **Owner:** SWE · **Tracker:** E5.5 (done) · **Sponsor ask:** an
Azure Migrate–style interactive dashboard on the Container App with in-page export.

### Plan

- **`publish_estimate`** (Function) — assemble → write `answers/estimate/latest.json` +
  `latest.{xlsx,docx,pptx}` to blob.
- **`src/web`** — the FastAPI Container App gains `/dashboard` (static page),
  `/dashboard/data` (the package JSON from blob, 404 if unpublished),
  `/dashboard/download/{fmt}` (streams the export blob). Chat client lazy-init'd so the
  container starts without Foundry.
- **`src/web/dashboard.html`** — a self-contained page (no CDN): header with DRAFT
  badge + confidence pill + Excel/Word/PPT buttons; a strip of headline tiles; a panel
  grid (inventory & readiness with a by-env bar chart; run-rate cost with a donut +
  driver table; landing zone with spoke chips; 6R as a stacked bar; the wave table with
  per-wave risk bars; effort with a workstream bar chart); a collapsible calculation
  appendix and the register. Every figure shows its `F*` id. Light + dark.
- **Bicep** — `STORAGE_URL` env on the container app.

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | `publish_estimate` writes exactly `latest.json` + 3 exports; the JSON round-trips | `test_dashboard` |
| C2 | `publish_estimate` rejects an empty body | `test_dashboard` |
| C3 | `/dashboard` serves the page and wires `/dashboard/data` + the 3 download links | `test_dashboard` |
| C4 | `/dashboard/data` → 404 when nothing published; returns the package when it is | `test_dashboard` |
| C5 | `/dashboard/download/{fmt}` streams with the right mime + attachment header; bad fmt → 400 | `test_dashboard` |
| C6 | `/healthz` reports `estimate_published` | `test_dashboard` |
| C7 | renders correctly against a real package (visual check) | Playwright screenshot |

### Do

- `src/api/deliverable/functions.py` — `_container_client` + `POST /api/publish_estimate`.
  `src/api/openapi/publish_estimate.json` + `create_agent.py` tool #12.
- `src/web/app.py` — lazy OpenAI client, `_read_estimate_blob`, 3 dashboard routes,
  `/healthz` extended, chat header links `/dashboard`. `src/web/dashboard.html` — new.
  `src/web/requirements.txt` — `azure-storage-blob`. `infra/resources.bicep` — container
  `STORAGE_URL`.
- `tests/test_dashboard.py` — 7 cases (127 total); `fastapi` + `httpx` added to
  `tests/requirements-dev.txt`. `DEPLOY.md`, `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **127 passed**. Visual: rendered the dashboard against the full
sample package (Playwright) — headline tiles, the by-env bars, the cost donut (with an
"Other" slice to 100%), the spoke chips, the 6R stacked bar, the 7-wave risk table, the
workstream bars, the collapsible appendix — all correct, Azure-portal-like, light+dark.

### Act

- **E5.5 done.** The estimate is now (a) a JSON package, (b) a markdown render, (c)
  Excel / Word / PowerPoint files, and (d) an interactive dashboard the client opens by
  URL and exports from.
- **Watch:** the dashboard needs `publish_estimate` to have been called (shows a
  friendly "nothing published yet" state otherwise). The container-app routes are
  behind the same Easy Auth as the chat page (manual, per DEPLOY step 1). A live `azd
  deploy web` is the real confirmation (same bucket as E1.6 / E8.2).
- **Phase 1 backlog left:** E1.7 (mapping override), E4.3 (duration model), full E6.2
  resource loading. **Phase 1 engine is otherwise complete.**
- **Next:** E1.6 / E8.2 / E5.5 live verification via `azd`, then Phase 2 (evidence pack).

---

## Cycle 13 — client-ready exports: Excel / Word / PowerPoint

**Date:** 2026-09-08 · **Owner:** SWE + Staff Writer · **Tracker:** E5.4 (done) ·
**New scope** from the sponsor: the deliverable must ship as `.xlsx` / `.docx` / `.pptx`.

### Plan

`deliverable/export.py` — `export(package, fmt) -> (bytes, filename, mime)`:
- **xlsx** (openpyxl): Cover, Headline, a sheet per section, Calculation appendix,
  Register — styled headers, frozen panes, auto widths.
- **docx** (python-docx): title page + DRAFT watermark, headline table, every section,
  the appendix table, the register lists.
- **pptx** (python-pptx): title, headline numbers, one slide per section, assumptions.

Every figure keeps its `F*` ref; all three carry the watermark. `POST /api/export_estimate`
(`{format, package}` or the assemble inputs). Deterministic from the package.

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | unknown format → ValueError / 400 | `test_export` |
| C2 | xlsx opens; one sheet per section + Cover + Appendix + Register; every `F*` in the appendix | `test_export` |
| C3 | docx opens; carries "DRAFT"; has the appendix; every register id present | `test_export` |
| C4 | pptx opens; title + headline + one slide per section + assumptions | `test_export` |
| C5 | content is deterministic (parsed, ignoring the zip timestamp) | `test_export` |
| C6 | a degraded package (a failed tool) still exports all three | `test_export` |

### Do

- `src/api/deliverable/export.py` — new. `deliverable/functions.py` —
  `POST /api/export_estimate`. `__init__.py` exports `export`.
- `src/api/requirements.txt` + `tests/requirements-dev.txt` — `python-docx`,
  `python-pptx`. `src/api/openapi/export_estimate.json` + `create_agent.py` tool #11.
- `tests/test_export.py` — 6 cases (120 total). `DEPLOY.md`, `README.md`,
  `tests/README.md` updated.

### Check

`pytest tests -q` → **120 passed**. Sample pipeline → `landfall-estimate.xlsx` (18 KB,
12 sheets), `.docx` (41 KB, 85 paras / 3 tables), `.pptx` (40 KB, 11 slides); all three
re-open cleanly and every figure id appears in the workbook's appendix.

### Act

- **E5.4 done.** The estimate is now downloadable in the three Office formats.
- **Next — Cycle 14:** E5.5 — the Azure Migrate–style assessment dashboard on the
  `src/web` Container App: read the assembled package (written to blob by the assemble
  step), render the interactive panels, wire the "Download Excel / Word / PPT" buttons
  to `export_estimate`. Needs an assemble→blob "publish" step + the dashboard page +
  vendoring or an API call for the render.

---

## Cycle 12 — security & isolation, self-contained hooks (Phase 1 close)

**Date:** 2026-09-08 · **Owner:** Security & Compliance Architect + SRE · **Tracker:**
E8.3 / E8.4 / E9.1 done; E8.1 / E8.2 in-review · **Closes audit** SEC-1/2/3/8, P0-8, OPS-5.

### Plan

- **E8.3** replace the keyword-blocklist `_safe_select` with an allow-list parser:
  single `SELECT`/`WITH`, only the six inventory tables, no comments hiding keywords,
  no `sys.`/`information_schema`/`WAITFOR`/`OPENROWSET`/…; add a statement timeout.
- **E8.4** the question and generated SQL never reach the logs — log a `sha256[:12]`
  hash + the table list + the query shape only.
- **E9.1** move the schema load + `db_datareader` grant off `sqlcmd` into
  `scripts/apply_sql.py` (pure Python, `mssql-python` + Entra token) so the hook needs
  neither `sqlcmd` nor `azd` on PATH.
- **E8.2** wire Function-App EasyAuth into the Bicep (`enableFunctionAuth` param, off by
  default, `excludedPaths ["/runtime"]`) so turning auth on is `azd env set` + `azd
  provision`, not a manual CLI recipe.
- **E8.1** document + verify one datastore per engagement (`resourceToken` already makes
  every resource env-unique; `azd down --purge`).

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | guard accepts real analytics (joins, CTEs, group-by, TOP, trailing comment) | `test_sqlguard` |
| C2 | guard rejects 2nd statement, non-SELECT, `sys.`/`information_schema`, unknown table, `WAITFOR`, `INTO`, `OPENROWSET`, comment-hidden `UNION sys.*`, unbalanced parens | `test_sqlguard` |
| C3 | table allow-list is exactly the six inventory tables; CTE names aren't flagged | `test_sqlguard` |
| C4 | `signature()` contains no question text and no SQL text; hash is stable | `test_sqlguard` |
| C5 | `query_inventory` logs a hash + tables + shape, never the text | code review |
| C6 | `apply_sql.py` splits `schema.sql` on `GO`, skips comment-only batches | unit-ish check |
| C7 | `az bicep build` clean with the new auth param (default off = no behaviour change) | `az bicep build` |

### Do

- `src/api/sqlguard.py` — new (`safe_select`, `signature`, `ALLOWED_TABLES`). `tools.py`
  — imports it, drops the old guard, adds `QUERY_TIMEOUT_S` + `cur.timeout`, scrubs
  every `logging.*` call (hash only).
- `scripts/apply_sql.py` — new. `postprovision.{sh,ps1}` — call it instead of the
  `sqlcmd` block. `scripts/requirements.txt` — `mssql-python`.
- `infra/{main,resources}.bicep` + `main.parameters.json` — `enableFunctionAuth` /
  `functionAuthClientId` params + `authsettingsV2` (conditional) + `QUERY_TIMEOUT_S`
  app setting.
- `tests/test_sqlguard.py` — 20 cases (114 total). `DEPLOY.md` updated (sqlcmd removed,
  auth recipe, isolation note).

### Check

`pytest tests -q` → **114 passed** (20 new). `az bicep build infra/main.bicep` → clean.
`apply_sql._run_batches` over `schema.sql` → 7 real batches, trailing comment skipped.
Guard spot-checks: `SELECT ... FROM sys.databases` → blocked (`sys.`); `SELECT * FROM
servers /* x */ UNION SELECT name,1,2 FROM sys.tables` → blocked; `WITH prod AS (...)
SELECT COUNT(*) FROM prod` → accepted.

### Act

- **E8.3 / E8.4 / E9.1 done.** `query_inventory` is now allow-list-parsed, timed out,
  and log-safe; the deploy no longer needs `sqlcmd`.
- **E8.2 / E8.1 in-review** — the Bicep path is ready and defaults off (no behaviour
  change); a live `azd provision` with `ENABLE_FUNCTION_AUTH=true` + an app registration
  is needed to confirm anonymous → 401 and the agent still works via MSI. Same live-verify
  bucket as E1.6.
- **Phase 1 backlog left:** E1.7 (mapping override), E4.3 (duration model), full E6.2
  resource loading, E8.5–8.7 / E9.2–9.5 (Phase 2). Plus the live checks (E1.6, E8.2).
- **New scope from the sponsor (this session):** client-ready **XLSX / DOCX / PPTX**
  exports of the estimate package, and an **Azure Migrate–style assessment dashboard**
  web app on the existing Container App from which end users export those artifacts.
  Added to the PRD as **E5.4** (exports) and **E5.5** (assessment web app). Next cycles.
- **Next — Cycle 13:** E5.4 — `deliverable/export.py`: the assembled package →
  a formatted Excel workbook, a Word document, and a PowerPoint deck.

---

## Cycle 11 — fault injection, output guard, CI gate

**Date:** 2026-09-08 · **Owner:** Applied Scientist + SRE · **Tracker:** E7.3 / E7.4 /
E7.5 (done) · **Closes audit** AI-3..6 (a tool failure or an un-sourced number could
slip through; nothing gated regressions).

### Plan

- **E7.3 fault injection** — every deterministic HTTP tool, given a broken request,
  returns a clean error (HTTP ≥ 400, body = an `error` string only) and never a 200
  with fabricated numbers; `assemble_estimate` omits a section when an upstream slot
  carries `{"error": ...}`.
- **E7.4 output guard** — a checker that flags any numeric claim (money, %, unit'd
  counts, magnitudes ≥ 1000) not backed by a tool value or a citation; run it against
  each scenario's own `summary_markdown` (the deliverable must be self-sourcing).
- **E7.5 CI gate** — a GitHub Actions workflow runs `pytest` + `evals/runner.py` on
  every push / PR; a stale `SCORECARD.md` or any regression fails the build. Changes to
  `scripts/create_agent.py` ride the same gate.

**Acceptance**

| # | Criterion | Check |
|---|---|---|
| C1 | every tool leaks nothing on a bad request (empty / wrong-type / missing) | `run_faults` / `test_evals` |
| C2 | `assemble_estimate` degrades: failed slot → section omitted, gap recorded, no fabricated figure | `run_faults` |
| C3 | output guard passes a real package render; flags a planted un-sourced number | `test_evals` |
| C4 | guard is quiet on dates, structural ints, and cited assumption/basis lines | manual + scenario runs |
| C5 | `evals/runner.py` exits non-zero on any golden / scenario / fault / guard failure | manual |
| C6 | CI workflow runs the full gate and diffs `SCORECARD.md` | `.github/workflows/evals.yml` |

**Design.** `evals/faults.py` (drives the real route functions with a fake
`func.HttpRequest`), `evals/output_guard.py` (`check_message` + `sourced_from_package`),
`runner.py` gains `run_faults` + a per-scenario guard check + a fault section in the
scorecard, `.github/workflows/evals.yml`. `assemble._ok()` skips a tool slot with an
`error` key and records the gap (+ `meta.tools_failed`).

### Do

- `evals/{faults,output_guard}.py` — new. `evals/runner.py` — `run_faults`, guard in
  `run_scenarios`, `scorecard(golden, scenarios, faults)`, dropped the daily date so the
  committed `SCORECARD.md` is stable. `evals/SCORECARD.md` regenerated (now 3 suites).
- `src/api/deliverable/assemble.py` — `_ok()` + `failed_tools` + register gap +
  `meta.tools_failed`.
- `.github/workflows/evals.yml` — new. `tests/test_evals.py` — +4 cases (94 total).
  `evals/README.md`, `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **94 passed**. `python evals/runner.py` → **PASS**:
```
Golden text-to-SQL (E7.1)                      32/32 (100%)   ✅
Full-estimate scenarios + output guard (E7.2/E7.4)  8/8       ✅
Fault injection (E7.3)                         26/26          ✅
```
Faults: 8 tools × 3–4 broken bodies each → all return `{"error": ...}` at 4xx/5xx;
the downstream case (compute + storage slots = `{"error": ...}`) → `tools_failed`
lists both, no compute/storage figures, register carries the gap. Guard: catches
`$2,400,000/year` / `1,200 person-days` / bare `63%`; passes every scenario's render.

### Act

- **E7 epic complete** (E7.1–E7.5). The engine now has a correctness gate that runs on
  every change.
- **Watch:** the output guard is heuristic — it challenges *claims*, not every digit,
  and exempts assumption/basis prose. It's a safety net for the agent's free text, not
  a formal proof; the live "agent never states an un-sourced number" drill is Phase 2.
  The CI workflow hasn't run yet (no push has triggered it) — first green run is the
  real confirmation.
- **Next — Cycle 12:** E8 (security & isolation — `query_inventory` auth on by default,
  allow-list SQL parse + statement timeout, SQL text out of logs, one datastore per
  engagement) + E9.1 (self-contained hooks). That closes Phase 1.

---

## Cycle 10 — eval harness (golden SQL + full-estimate scenarios)

**Date:** 2026-09-08 · **Owner:** Applied Scientist + FinOps + SRE · **Tracker:**
E7.1 / E7.2 (done) · **Closes audit** P0-7 / AI-1..8 (nothing proved the tools stay
correct as the agent, prices, or SKUs change).

### Plan

**Objective.** An offline harness that gates correctness:
- **E7.1** a golden text-to-SQL set (≥30 `question → T-SQL → expected` cases) run
  against a SQLite copy of the sample estate; each SQL must pass `tools._safe_select`
  and match its expected result exactly. Gate: ≥95%.
- **E7.2** ≥8 full-estimate scenarios — run the whole tool chain + `assemble_estimate`
  with deterministic synthetic price books and assert every headline figure lands in an
  expected band, every figure is traceable, and a re-run is byte-identical.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | ≥30 golden cases; ≥95% exact match over the sample | `runner.run_golden` / `test_evals` |
| C2 | every golden SQL passes the read-only SELECT guard | `test_evals` |
| C3 | ≥8 scenarios, all pass (figures in band + traceable + deterministic) | `runner.run_scenarios` / `test_evals` |
| C4 | scenarios exercise real levers (RI term, AHB, dev/test, appetite, DQ, slice) | scenarios.json |
| C5 | `python evals/runner.py` exits non-zero on any failure; writes SCORECARD.md | manual |

**Design.** `evals/` — `sample_db.py` (CSV → in-memory SQLite + a small test-only
T-SQL→SQLite shim: `TOP`→`LIMIT`, `GETDATE()`→fixed date, `DATEDIFF`, `ISNULL`…),
`fixtures.py` (synthetic price/rate books), `pipeline.py` (run every tool → assemble),
`runner.py` (golden + scenarios + scorecard + exit code), `golden_sql.json` (32 cases),
`scenarios.json` (8). `tests/test_evals.py` wraps it so `pytest` catches regressions.

**Deferred.** E7.3 fault-injection (each tool 5xx → agent reports, never invents),
E7.4 output guard (reject un-sourced numeric claims), E7.5 CI gate on every
`create_agent.py` change — next cycle. The live "model generates matching SQL" gate
needs credentials and belongs in CI.

### Do

- `evals/{sample_db,fixtures,pipeline,runner}.py`, `evals/{golden_sql,scenarios}.json`,
  `evals/README.md`, `evals/SCORECARD.md` (generated).
- `tests/test_evals.py` — 4 wrapper cases. `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **91 passed**. `python evals/runner.py` → **PASS**:
```
Golden text-to-SQL (E7.1)        32/32 (100%)   gate ≥95%   ✅
Full-estimate scenarios (E7.2)   8/8                        ✅
```
The 32 golden queries span servers / apps / storage / dependencies / performance —
counts, sums, group-bys, top-N, EOL date logic, distinct scopes. The 8 scenarios move
the RI term, AHB, dev/test pricing, disposition appetite, DQ confidence, and the estate
slice, and each lands in-band (e.g. no-AHB run-rate $132.6k vs house $113.9k;
aggressive-appetite effort 968 PD vs 834).

### Act

- **E7.1 / E7.2 done.** `SCORECARD.md` is committed as the evidence artifact; the runner
  regenerates it and any purposeful maths change re-commits it with adjusted expecteds.
- **Watch:** the SQLite shim is deliberately narrow — a golden query using a T-SQL
  construct it doesn't cover will error in the runner (not silently pass). Keep golden
  SQL within the documented shim surface or extend `sample_db.to_sqlite`.
- **Next — Cycle 11:** E7.3 / E7.4 / E7.5 — fault-injection harness, the un-sourced-
  number output guard, and the CI scorecard gate. Then E8 / E9 (security + ops), which
  finishes Phase 1.

---

## Cycle 9 — assemble_estimate (the structured deliverable)

**Date:** 2026-09-08 · **Owner:** PM + Staff Writer + SWE · **Tracker:** E5.1 / E5.2 /
E5.3 (done), E2.5 (done), E6.2 (basic) · **Closes audit** P0-5 / PS-2..4 (output was a
chat transcript, figures had no provenance, the assumptions register was hand-merged).

### Plan

**Objective.** `assemble_estimate` — stitch the other tools' outputs + an inventory
summary into ONE package:
- **E5.1** 8 sections (config-driven list).
- **E5.2** a stable ID on every headline figure + a calculation-appendix entry per
  figure (source tool, inputs, formula, assumptions applied, confidence).
- **E5.3** a machine-built assumptions / exclusions / data-gaps register, collected from
  every tool's own `assumptions` / `caveats` / `not_costed` / `missing_prices` /
  `needs_human_decision` arrays + the DQ report + standing exclusions — deduped, ID'd,
  categorised.
- **E2.5** top-3 cost drivers on the run-rate total.
- **E6.2 (basic)** a parametric person-day + services-cost estimate (contingency tied to
  the DQ confidence — E6.3).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | Assembles from inventory alone; a tool not run leaves its section marked, not dropped | unit test |
| C2 | Every figure has a calculation-appendix entry with a non-empty formula + source | unit test |
| C3 | Register collects each tool's caveats + standing exclusions; deduped and ID'd | unit test |
| C4 | Run-rate figures reconcile (compute + storage + extras); top-3 drivers ranked | unit test |
| C5 | Effort contingency = 8/12/20% for High/Medium/Low DQ confidence | unit test |
| C6 | Effort range + services cost reconcile | unit test |
| C7 | Overall confidence = worst of the figure confidences | unit test |
| C8 | Full pipeline (6 tools → assemble) is deterministic over the sample estate | unit test |

**Design.** `src/api/deliverable/{effort,assemble}.py` — pure, tool outputs injected.
`deliverable/functions.py` — `POST /api/assemble_estimate`. New `effort` (extended) +
`deliverable` config blocks. OpenAPI spec + agent tool #10 + prompt line.
`deliverable_bp` in `function_app.py`. Markdown render built in.

**Deferred.** Full effort model (wave-by-wave resource loading, peak FTE, the loading
curve) = a later E6.2 cycle. A rendered PDF/DOCX export = out of scope (the markdown
drops into the proposal template).

### Do

- `src/api/deliverable/{__init__,effort,assemble,functions}.py` — new package.
  `function_app.py` — `deliverable_bp`. `cost/config.py` — `effort` extended + new
  `deliverable` block.
- `src/api/openapi/assemble_estimate.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 10) + `SYSTEM_PROMPT` line.
- `tests/test_deliverable.py` — 7 cases incl. the full-pipeline test. `estimation_config.json`,
  `DEPLOY.md`, `README.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **87 passed**. C1–C8 pass (see test names).

Full pipeline over the sample estate (real prices + live storage rates):
```
HEADLINE       run-rate  $119,181 /mo   $1,430,167 /yr   (confidence Low)
               one-time  $77,170
               effort    834 PD (709–959)   services ~$650,286 ($553k–$748k)
SECTIONS       8 (current state / LZ / 6R / waves / run-rate / effort / register / next steps)
FIGURES        14, each with a formula + inputs + confidence in the appendix
REGISTER       28 assumptions · 6 exclusions · 8 data gaps  (all source-tagged)
TOP DRIVERS    compute effective 47% · managed disk 25% · monitoring 10%
```

### Act

- **E5.1/E5.2/E5.3 + E2.5 done. E6.2 partial** (basic parametric; full resource-loading
  model is a later cycle — tracker E6.2 stays `in-review` with that note).
- The deliverable is the audit's review-drill target: "hand it to an uninvolved
  architect; they answer 'where did this come from?' for 10 random figures using only
  the document." The calculation appendix + register are built for exactly that.
- **Watch:** effort execution-PD-per-disposition and the LZ/testing/hypercare constants
  are first-pass — a firm calibrates them against `sample-estate/effort-inputs.md`
  (which lands EAC ~775 PD; the tool gives ~834 for Medium confidence — same ballpark).
- **Next — Cycle 10:** E7.1/E7.2 — the eval harness: a golden text-to-SQL set (30+) with
  a runner, and full-estimate scenarios (8+) with expected ranges, 0 un-sourced numbers,
  identical on re-run. Uses the `microsoft-foundry` skill.

---

## Cycle 8 — score_dispositions + plan_waves (the wave engine)

**Date:** 2026-09-08 · **Owner:** Architect + PM + SWE · **Tracker:** E4.1 / E4.2 (done) ·
**Closes audit** P0-4 / MA-1..5 (no move-group / wave plan — the agent was inventing them).

### Plan

**Objective.** Two deterministic tools:
- **`score_dispositions` (E4.2)** — a rule-derived 6R candidate + rationale + confidence
  per app from inventory signals (servers, EOL OS, criticality, internet-facing, DB
  engine, stack, retire/repurchase markers). The agent explains it, never invents it.
- **`plan_waves` (E4.1)** — server dependency graph → drop stale / low-confidence /
  commodity (AD, DNS, NTP) edges → roll up to app-to-app edges → affinity move-groups
  (connected components) → risk-score each group → order low-risk-first into waves
  (platform wave 0, pilot next, regulated last), capped by servers/apps per wave, with
  entry/exit criteria and cross-wave blocking dependencies (real + dropped-but-flagged).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | 0 servers / retire marker → Retire; repurchase marker → Repurchase | unit test |
| C2 | small single-PaaS-DB low-criticality app → Replatform; clustered DB → Rehost (IaaS) | unit test |
| C3 | tier-1 PaaS-DB app → Rehost but notes the Replatform alternative; `aggressive` appetite flips it | unit test |
| C4 | EOL-OS servers noted on the Rehost rationale | unit test |
| C5 | chatty apps land in one move-group; standalone apps are singletons | unit test |
| C6 | stale / low-confidence / commodity edges excluded and counted | unit test |
| C7 | platform (shared-infra) group is wave 0; regulated group is last; pilot is low-risk | unit test |
| C8 | per-wave server / app cap splits into multiple waves | unit test |
| C9 | a dropped edge across waves is surfaced as an `unverified` blocking dependency | unit test |
| C10 | deterministic over the full sample estate | unit test |

**Design.** `src/api/waves/{disposition,plan}.py` — pure (own union-find, no graph lib).
`waves/functions.py` — `POST /api/score_dispositions` + `POST /api/plan_waves`. New
`disposition` + `waves` blocks in `cost/config.py` + `estimation_config.json`. 2 OpenAPI
specs + agent tools #8/#9 + prompt lines. `waves_bp` wired into `function_app.py`.

**Deferred.** E4.3 duration model (servers/wave ÷ throughput → dated plan + critical
path) — needs the effort model (E6.2). Same-wave non-prod-before-prod is a scheduling
note, not a separate wave.

### Do

- `src/api/waves/{__init__,disposition,plan,functions}.py` — new package.
  `function_app.py` — `waves_bp`. `cost/config.py` — `disposition` + `waves` blocks.
- `src/api/openapi/{score_dispositions,plan_waves}.json` — new. `scripts/create_agent.py`
  — `_OPENAPI_TOOLS` (now 9) + `SYSTEM_PROMPT` lines.
- `tests/test_waves.py` — 14 cases. `estimation_config.json`, `DEPLOY.md`, `README.md`,
  `tests/README.md` updated.

### Check

`pytest tests -q` → **80 passed**. C1–C10 pass (see test names).

Full sample estate (31 apps, 250 servers, 484 dependency rows):
```
DISPOSITIONS  Rehost 25 / Replatform 3 / Repurchase 2 / Retire 1
  Replatform: Corporate Website (CMS), Document Management, Procurement Portal  (all low conf)
  Repurchase: Learning Management, [Collaboration]      Retire: Analytics Sandbox
  needs_human_decision: 6

GRAPH  31 app nodes, 0 app edges, 31 components   (362 commodity/platform edges excluded,
       0 stale after the filter, platform_apps = [app-31])
  -> the sample's only cross-app coupling is AD/DNS/shared-infra; every business app is
     self-contained. Affinity clustering will bind groups on a messier real estate.

WAVES  0 platform  (app-31, 35 srv, high — foundation)
       1 pilot     (2 apps, 3 srv, medium — incl. the Retire app)
       2 standard  (6 apps, 23 srv, risk 47)
       3 standard  (6 apps, 30 srv, risk 60)
       4 standard  (6 apps, 29 srv, risk 71)
       5 standard  (6 apps, 29 srv, risk 77)
       6 regulated (5 apps, 34 srv, risk 79 — PCI-DSS + HIPAA, QSA gate)
```
7 waves, risk rising 47→79 across the standard band — matches the discovery answer's
7-wave shape, but derived from `dependencies.csv` + `applications.csv`.

### Act

- **E4.1 / E4.2 done.** The migration plan (move-groups + risk-ordered waves) and the 6R
  disposition are now deterministic tools.
- **Watch:** the sample's dependency data has no cross-app application-layer flows (all
  LDAP/DNS) so every app is a singleton move-group. That's a property of the synthetic
  data, not a bug — a real RVTools/DR-Migrate export with app-tier flows exercises the
  affinity clustering. Consider adding a few cross-app HTTP flows to `sample-estate` to
  demo it (candidate for a follow-up).
- **Next — Cycle 9:** E5.1/E5.2/E5.3 — "assemble estimate" into one structured
  deliverable (8 sections), stable IDs + calculation appendix on every figure, and the
  machine-tracked assumptions & exclusions register. Plus E2.5 (top-3 cost drivers)
  folds in here.

---

## Cycle 7 — design_landing_zone (CAF ALZ from the portfolio)

**Date:** 2026-09-08 · **Owner:** Architect (CAF/Landing Zones) + SWE · **Tracker:**
E3.1 / E3.2 / E3.3 (done) · **Closes audit** P0-3 / LZ-1..3 (no landing-zone output —
the biggest "toy → real" gap).

### Plan

**Objective.** A deterministic tool that turns the application portfolio + a server
summary into a **client-specific** CAF Azure Landing Zone: management-group hierarchy,
subscriptions, hub-spoke VNets + IP plan, policy set, identity, connectivity, DR, and a
**dedicated regulated spoke** (+ Confidential MG + CMK/private-endpoint overlay) for
every distinct compliance scope in the portfolio. The topology must be *derived* — swap
the portfolio and the spoke count / regulated flag change (E3.2). Resiliency tier per
app from criticality 1–4 (E3.3).

**Why a tool and not the `azure-enterprise-infra-planner` skill:** that skill is a
7-phase interactive IaC-generation pipeline (Bicep/Terraform + deploy, MCP-tool driven)
— it's what a delivery architect runs *after* the estimate. Landfall needs the
deterministic design the agent quotes during pre-sales. The tool's output is shaped as a
requirements document to hand to that skill downstream (`next_step` field).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | Zone rules: internet_facing→Online; regulated scope→Regulated; else Corp | unit test |
| C2 | No regulated app ⇒ no regulated spoke, no Confidential MG, no overlay | unit test |
| C3 | A regulated app ⇒ dedicated spoke pair + Confidential MG + CMK/PE + built-in initiative | unit test |
| C4 | Swapping the portfolio changes the spoke count and the zone set | unit test |
| C5 | IP plan blocks are inside the supernet and non-overlapping | unit test |
| C6 | criticality → resiliency tier; DR rollup counts | unit test |
| C7 | identity_model switch changes the hub (DCs vs none) | unit test |
| C8 | Deterministic over the full sample portfolio | unit test |

**Design.** `src/api/lz/design.py` — pure. `lz/functions.py` —
`POST /api/design_landing_zone`. New `landing_zone` block in `cost/config.py` DEFAULTS +
`estimation_config.json`. OpenAPI spec + agent tool #7 + prompt line. Wired into
`function_app.py` (`lz_bp`).

**Deferred.** Business-domain spoke grouping (the tool uses CAF archetype grouping —
zone × env; a per-app-affinity spoke map is an E4 wave-engine concern). Bicep
generation (hand off to the skill). Cost of the LZ platform itself (fixed services —
commercial line).

### Do

- `src/api/lz/{__init__,design,functions}.py` — new package. `function_app.py` —
  `lz_bp` registered. `cost/config.py` — `landing_zone` block.
- `src/api/openapi/design_landing_zone.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 7) + `SYSTEM_PROMPT` LZ line.
- `tests/test_landing_zone.py` — 8 cases. `estimation_config.json`, `DEPLOY.md`,
  `README.md`, `sample-estate/effort-inputs.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **66 passed**. C1–C8 pass (see test names).

Full sample portfolio (31 apps) + server summary:
```
CAF ALZ, swedencentral (DR westeurope). 9 spokes: 16 corp / 10 online / 5 regulated.
regulated: HIPAA, PCI-DSS  -> dedicated spoke pair + alz-confidential MG + policy overlay
  (CMK, deny public access, private endpoints, PCI DSS v4 + HIPAA HITRUST initiatives)
MGs:  platform{connectivity,identity,management} / landingzones{corp,online,confidential}
      / sandbox / decommissioned
subs: 3 platform + 8 LZ + sandbox = 12
IP:   hub 10.100.0.0/22 ; spokes 10.100.4.0/22 .. 10.100.36.0/22 ; DR supernet 10.104.0.0/14
hub:  ExpressRoute GW + backup VPN GW + Azure Firewall Premium (forced tunnel) + Bastion
      + Private DNS Resolver + 2x AD DC (extend AD)
DR:   region pair; ASR + native DB replication for tiers 1-2; tiers 3-4 from GRS backup
tiers: 13 T1 / 8 T2 / 6 T3 / 4 T4  (= criticality mix)
```
Matches the discovery answers (SC2 CMK, ID3 extend-AD, N2 ER+VPN, N7 forced tunnel,
B4/R3 Sweden Central + West Europe + AZs) — but derived from `applications.csv`, not the
discovery doc.

### Act

- **E3.1/E3.2/E3.3 done.** The landing-zone deliverable — the audit's #1 gap — now
  exists as a deterministic, portfolio-driven tool.
- **Watch:** HIPAA (1 app) gets its own spoke pair + subs. That's the correct
  conservative default (isolate per compliance boundary); a firm that folds HIPAA into
  the PCI segment edits `landing_zone.regulated_scopes`.
- **Next — Cycle 8:** E4.1/E4.2 — `plan_waves` (dependency graph → move groups →
  risk-ordered waves) + the deterministic 6R disposition scorer.

---

## Cycle 6 — estimate_run_rate_extras (run-rate + one-time migration cost)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.4 (done).

### Plan

**Objective.** The lines beyond compute + storage that still land on the monthly Azure
bill — **backup** (vault storage + protected-instance fees), **internet egress** (from
`net_out_gb_30d`), **monitoring** (Log Analytics ingestion + Defender for Servers),
**support plan** — plus the **one-time** cost of the migration (Azure Migrate/ASR
tooling after its free window, replication egress, dual-running on-prem + Azure during
cutover). Deterministic; all rates from `estimation_config.json ["extras"]`, nothing
fetched. `monthly_infra_cost` (compute + storage) drives the dual-run line.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | Powered-off servers excluded from every per-server line | unit test |
| C2 | Backup = protected-data·factor·$/GB + instances·$/instance | unit test |
| C3 | Egress applies the internet fraction and the free tier | unit test |
| C4 | Monitoring = LA ingestion + Defender; Defender toggle works | unit test |
| C5 | Support is the configured flat plan rate (0 for `none`) | unit test |
| C6 | Tooling one-time = 0 while avg migration months < free window; > 0 after | unit test |
| C7 | Dual-run one-time scales linearly with `monthly_infra_cost` | unit test |
| C8 | `total_monthly` reconciles; `first_year_extras = run_rate·12 + one_time` | unit test |
| C9 | Deterministic over the full sample `servers.csv` | unit test |

**Design.** `cost/run_rate.py` — one pure function, no network. `cost/functions.py` —
`POST /api/estimate_run_rate_extras`. New `extras` block in `config.py` DEFAULTS +
`estimation_config.json`. OpenAPI spec + agent tool #6 + prompt line.

**Deferred.** ExpressRoute/VPN and landing-zone fixed services stay separate proposal
lines (E3 / commercial). Commitment-tier LA discounts are a config edit, not modelled.

### Do

- `src/api/cost/run_rate.py` — new. `functions.py` — 4th route. `config.py` — `extras`
  block. `__init__.py` exports `estimate_run_rate_extras`.
- `src/api/openapi/estimate_run_rate_extras.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 6) + `SYSTEM_PROMPT` run-rate line.
- `tests/test_run_rate.py` — 9 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md`, `tests/README.md` updated.

### Check

`pytest tests -q` → **58 passed**. C1–C9 pass (see test names).

Full sample estate (233 powered-on servers), Sweden Central, infra bill $102.9k/mo:
```
backup          $  4,163 /mo   (vault storage + 233 protected instances)
internet egress $    491 /mo   (30% of 33 TB net_out, less 100 GB free, @ $0.05/GB)
monitoring      $ 11,534 /mo   (Log Analytics $8,039 @ 0.5 GB/server/day + Defender $3,495)
support         $    100 /mo   (Standard, flat)
RUN-RATE EXTRAS $ 16,287 /mo   ($195,445 /yr)

one-time: dual-run $77,170 (1.5 mo x 50% of infra) ; tooling $0 (within 180-day free window)
first-year extras  $272,615
```

### Act

- **E2.4 done.** Full Azure run-rate for the sample estate: compute+disk ~$86k +
  storage ~$16.5k + extras ~$16.3k ≈ **~$119k/mo (~$1.43M/yr)**, plus ~$77k one-time.
- **Watch:** monitoring is the largest extra and the most assumption-sensitive
  (LA GB/server/day). Default is deliberately conservative (0.5 GB — syslog + counters,
  not verbose VM insights); a real engagement sets it from the client's logging policy.
- **E2.1–E2.4 done** — right-size, compute BoM, storage BoM, run-rate extras. Every
  result already carries a low/expected/high range; **E2.5** (an explicit top-3
  cost-driver / sensitivity block on each result) is still open, small, and can fold
  into the E5 deliverable cycle. **Next — Cycle 7:** E3.1/E3.2 — `design_landing_zone`
  (ALZ topology, spoke count, regulated-spoke flag from the portfolio + compliance
  scope), using the `azure-enterprise-infra-planner` skill.

---

## Cycle 5 — estimate_storage_cost (file / DB / object BoM)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.3 (done) ·
**Closes audit** FIN-3 remainder (compute BoM landed in Cycle 4; storage was deferred).

### Plan

**Objective.** Cost the `dbo.storage` table — file shares (Files Premium / NetApp),
managed/PaaS DB volumes (SQL MI, Hyperscale, PostgreSQL/MySQL Flexible, Oracle), object
(Blob). Line-item bill + by-type totals + low/expected/high, deterministic on injected
rates. **Disjoint** from `estimate_compute_cost`: that tool prices one managed disk per
VM (`type='block'`), so block volumes are excluded here and only reported — unless
`storage.price_block_from_storage_table` is set (then the caller suppresses disk in the
compute tool).

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | `classify()` maps type + target_service → the right rate category | unit test |
| C2 | Block volumes excluded by default, counted in `excluded`; switch includes them | unit test |
| C3 | Files-premium / ANF min-provision floor billed even when the share is smaller | unit test |
| C4 | DB lines get the growth-headroom % and carry the "storage only" caveat | unit test |
| C5 | Injected rate overrides the config rate; `range.low ≤ expected ≤ high`; totals reconcile | unit test |
| C6 | Missing / zero size flagged in `not_costed`, never fatal | unit test |
| C7 | Deterministic over the full sample `storage.csv` | unit test |
| C8 | Live retail rates parse and are sanity-clamped to the config baseline | live fetch spot-check |

**Design.** `cost/storage_cost.py` — pure rate math on a `{category: usd_gb_month}`
book. `cost/pricing.py` gains `fetch_storagebook(region)` (best-effort per-service
queries, `_cheapest_stored` after a backup/redundancy exclude list, `_sane()` clamp to
0.4×–2.5× of the documented baseline so a mis-matched meter can't silently replace a
defensible rate). `cost/functions.py` — `POST /api/estimate_storage_cost` (6 h rate
cache). New `storage` block in `config.py` DEFAULTS + `estimation_config.json`. New
OpenAPI spec + agent tool #5 + prompt line.

**Deferred.** E2.4 — run-rate extras (backup, egress, monitoring, support) + one-time
migration cost. Object-tier lifecycle rules. Per-DB compute sizing (that's a replatform
concern, E4).

### Do

- `src/api/cost/storage_cost.py` — new. `pricing.py` — `fetch_storagebook` + helpers.
  `functions.py` — 3rd route + `_storage_rates` cache. `config.py` — `storage` block.
  `__init__.py` exports `estimate_storage_cost`, `classify`.
- `src/api/openapi/estimate_storage_cost.json` — new. `scripts/create_agent.py` —
  `_OPENAPI_TOOLS` (now 5) + `SYSTEM_PROMPT` storage line.
- `tests/test_storage_cost.py` — 10 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md` updated.

### Check

`pytest tests -q` → **49 passed**. C1–C7 pass (see test names).

C8 — live fetch (`swedencentral`, price_date `2026-09-01`): kept
`anf_standard 0.147`, `anf_premium 0.294`, `db_sql_mi 0.137` (GP LRS),
`db_sql_hyperscale 0.119`, `db_flex_postgresql 0.115`, `blob_hot 0.017`. Rejected by the
sanity clamp and fell back to config: `files_premium` (live 0.06 vs baseline 0.164 — a
Provisioned-v2 PAYG meter), `anf_ultra` (no match), `db_oracle` (no public meter).

Full sample estate (566 storage rows), Sweden Central:
```
file shares (5, 30 TB)     $  8,235 /mo
PaaS-DB volumes (39, 53 TB) $  8,301 /mo   (storage only — DB compute is a replatform line)
object                     $      0 /mo
TOTAL                       $ 16,536 /mo   ($198,430 /yr)
range                       $ 12,402 .. $ 20,670 /mo
excluded: 522 block volumes (~161 TB) — in the compute BoM's per-VM managed disk
```

### Act

- **E2.3 done.** Compute + storage now give a full infra run-rate: ~$86k/mo compute +
  disk, ~$16.5k/mo file/DB/object → **~$103k/mo (~$1.24M/yr)** for the sample estate,
  before dev/test pricing and E2.4 extras.
- **Watch:** the live storage-rate fetcher is heuristic (meter names vary by
  service). The `_sane()` clamp is the safety net; anything it rejects uses the
  documented `estimation_config.json` rate. Oracle DB@Azure has no retail meter — config
  rate only.
- **Next — Cycle 6:** E2.4 (`estimate_run_rate_extras` — backup GB, egress from
  `net_out_gb_30d`, monitoring, support tier + one-time migration/egress cost), then E3
  landing-zone deliverable (`azure-enterprise-infra-planner`).

---

## Cycle 4 — estimate_compute_cost (compute BoM)

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.2 (done), E6.1 (advances) ·
**Closes audit** FIN-3 (nothing aggregated the SKU mix into a costed bill).

### Plan

**Objective.** Turn the right-size output into a monthly Azure compute cost — a
line-item bill of materials with PAYG / reserved / AHB, per-environment scaling, and a
low/expected/high range — deterministic for a given price date.

**Acceptance this cycle**

| # | Criterion | Check |
|---|---|---|
| C1 | AHB prices a Windows server at the Linux (no-licence) rate; flagged per line | unit test (injected prices) |
| C2 | Reserved blend = coverage·RI + (1−coverage)·PAYG at the configured term | unit test |
| C3 | Per-environment factor scales dr / non-prod compute | unit test |
| C4 | A SKU with no price is flagged in `missing_prices`, never fatal; line falls back to disk-only | unit test |
| C5 | `range.low ≤ expected ≤ high`; totals reconcile; `annual == monthly·12` | unit test |
| C6 | Deterministic | unit test |
| C7 | Real retail prices parse correctly (RI = amortised term total, Windows vs Linux) | live fetch spot-check |

**Design.** `cost/compute_cost.py` — pure math on an injected **PriceBook**
(`{sku: {linux|windows: {payg, ri1y, ri3y}}}`) + **DiskBook** (`{tier: monthly}`).
`cost/pricing.py` — builds those from prices.azure.com (VM + Premium SSD meters, chunked
OData, paging). `cost/functions.py` — `POST /api/estimate_compute_cost` (right-size →
collect SKUs → fetch prices, 6 h cache → cost). New OpenAPI spec + agent tool + prompt
("pass env + os_name too; never cost servers yourself"). Config `uplift` block reworked
to `nonprod_of_prod_pct` / `dr_of_prod_pct` / `dev_test_discount_pct`.

**Deferred.** Storage-table cost (file shares / DB / object) = E2.3. Run-rate extras
(backup, egress, monitoring, support) + one-time migration cost = E2.4. `ESTIMATION_CONFIG`
now supports an inline-JSON app setting; a package-baked default file is still TODO.

### Do

- `src/api/cost/{compute_cost,pricing}.py` — new. `functions.py` — 2nd route + price cache.
  `__init__.py` exports. `config.py` — `uplift` rework + inline-JSON `ESTIMATION_CONFIG`.
- `src/api/openapi/estimate_compute_cost.json` — new. `scripts/create_agent.py` — tool +
  prompt.
- `tests/test_compute_cost.py` — 8 cases. `estimation_config.json`, `DEPLOY.md`,
  `sample-estate/effort-inputs.md` updated.

### Check

`pytest tests -q` → **40 passed**. C1–C6 pass (see test names).

C7 — live fetch (`swedencentral`, price_date `2026-06-01`):
`Standard_D4s_v5` linux `{payg 0.204, ri1y 0.12591, ri3y 0.08059}`, windows payg `0.388`
(the ~$0.184/hr delta is the Windows licence). First fetch returned RI as a **term lump
sum** (1103.0 / 2118.0) — fixed: reservations are always amortised `price/(years·8760)`.

Full 250-server estate, 1yr RI @ 80%, AHB on Windows:
```
compute PAYG        $ 81,106 /mo
compute RI          $ 50,315 /mo
compute effective   $ 56,473 /mo
managed disk        $ 29,884 /mo
TOTAL               $ 86,358 /mo   ($1,036,292 /yr)
range               $ 69,915 .. $138,840 /mo
missing_prices []   by_env prod 173 / nonprod 47 / dr 3 / dev 27
```
All 250 SKUs priced. Higher than `effort-inputs.md`'s old hand estimate (~$28–38k/mo) —
that assumed a 40% right-sizing cut and omitted managed-disk cost; the doc note is
updated. Every line is now traceable and ranged.

### Act

- E2.2 → `in-review` (unit + live-fetch verified; end-to-end via the agent with E1.6).
- **Next — Cycle 5:** E2.3 `estimate_storage_cost` over the `storage` table (file shares
  → Files/ANF, DB volumes → PaaS tiers, object), keeping it disjoint from the per-VM
  managed disk in `estimate_compute_cost`.

---

## Cycle 3 — deterministic right-sizer + firm config

**Date:** 2026-09-07 · **Owner:** FinOps + SWE · **Tracker:** E2.1 (done), E6.1 (partial) ·
**Closes audit** FIN-1 (`vcpu/2` haircut), FIN-2 (RAM never sized).

### Plan

**Objective.** Replace the crude `vm_rightsize` heuristic with a deterministic,
RAM-aware right-sizer driven by the firm's config.

**Acceptance criteria this cycle**

| # | Criterion | Check |
|---|---|---|
| B1 | Sizes vCPU and RAM independently; a 128 GB box never maps to a 32 GB SKU; output says which bound it | unit test |
| B2 | No perf data → allocation kept as-is (no blind haircut), confidence "low" | unit test |
| B3 | With utilisation data → sizes to p95 (not raw peak) at the configured target; confidence "high" | unit test + full-estate rollup |
| B4 | Disk tier respects IOPS, not just size | unit test (100 GiB / 4000 IOPS → P30) |
| B5 | `estimation_config.json` changes the output | unit test with `config` override |
| B6 | Deterministic — same input, same output | unit test |
| B7 | Full `sample-estate/` (250) → every server gets a SKU; over-provisioned fleet shrinks on vCPU | integration test |

**Design.** New `src/api/cost/` package: `config.py` (DEFAULTS + `estimation_config.json`
deep-merge loader), `skus.py` (v5 F/D/E families **incl. constrained-vCPU E-SKUs** for
RAM-heavy boxes + Premium SSD tiers), `rightsize.py` (pure logic), `functions.py`
(`POST /api/vm_rightsize` blueprint). `vm_rightsize` route moves out of `tools.py`.
New root `estimation_config.json`. OpenAPI spec + `create_agent.py` prompt updated so the
agent passes utilisation columns and never sizes servers itself.

**Deferred.** `ESTIMATION_CONFIG` app setting in Bicep; the pricing / effort blocks of the
config aren't consumed yet (E2.2 / E6.2). `azure_retail_prices` still returns raw meters —
the cost roll-up is E2.2 (next cycle).

### Do

- `src/api/cost/{__init__,config,skus,rightsize,functions}.py` — new.
- `estimation_config.json` — new (root).
- `src/api/tools.py` — `vm_rightsize` + `_SKU_TABLE` + `_HEURISTIC` removed.
- `src/api/function_app.py` — register `cost_bp`.
- `src/api/openapi/vm_rightsize.json` — v2 schema (utilisation inputs, range, bound_by).
- `scripts/create_agent.py` — tool description + `SYSTEM_PROMPT` ("pass ALL utilisation
  columns; never size servers yourself").
- **Data:** `sample-estate/generate_estate.py` now rolls up `cpu_p95_pct` / `ram_p95_pct`
  (p95 of daily averages — the right-sizing signal). `schema.sql`, `ingest/core.py`,
  `ingest/loader.py`, `load_estate.py`, `tools.py` `SCHEMA_HINT` extended. CSVs regenerated.
- `tests/test_rightsize.py` (9 cases) + smoke-import checks.
- `README.md` — `estimation_config.json` section + repo-layout rows.

### Check

`pytest tests -q` → **31 passed**.

Full `sample-estate/` right-size rollup:
```
servers 250 · downsized 72 · at_ceiling 0 · low_confidence 66
current_vcpu 1940 → recommended_vcpu 1604   (-17% fleet vCPU)
```
Spot check srv-0014 (64 vCPU / 256 GB, p95 CPU 33% / RAM 87%): → `E48s_v5`, bound_by
`ram`, confidence high, basis *"sized to p95 utilisation … at 65/80% targets"*, range
`E32s_v5`…`E48s_v5`. Unmonitored srv-0004: kept at 100%, confidence low, basis names it.

| # | Result |
|---|---|
| B1 | pass — `{vcpu:4, ram_gb:128}` → E-family, `ram_gb ≥ 128`, `bound_by=="ram"` |
| B2 | pass — no perf → `vcpu` not reduced, confidence low, "no blind reduction" in basis |
| B3 | pass — p95 path downsizes 16→8 vCPU, confidence high; full estate -17% vCPU, only monitored servers move |
| B4 | pass — 100 GiB / 4000 IOPS → P30 (P10 caps at 500 IOPS) |
| B5 | pass — `no_perf_data.cpu_scale_pct=60` → `need.vcpu == 6.0` |
| B6 | pass — `rightsize_one(s) == rightsize_one(s)` |
| B7 | pass — 250/250 get a `Standard_*` SKU; fleet vCPU shrinks |

Bug found + fixed during Check: sizing fell back to raw 30-day **peak** when p95 was
absent, which upsized the whole over-provisioned estate (2472 vs 1940 vCPU). Fixed:
added real `cpu_p95_pct` / `ram_p95_pct` rollups to the data; right-sizer p95-chain is now
`[p95, avg, peak×0.75]` — never sizes to a raw maximum.

### Act

- E2.1 → `in-review` (unit-verified; live check with E1.6). E6.1 → `in-review` (file +
  loader done; pricing/effort blocks unused until E2.2 / E6.2).
- **Next — Cycle 4:** E2.2 `estimate_compute_cost` — take the right-size output, price it
  via `azure_retail_prices`, compute monthly PAYG + 1yr/3yr RI + AHB, storage from the
  `storage` table, return a line-item BoM with region + term + price date and a
  low/expected/high range.

---

## Cycle 2 — deploy wiring + docs for the ingestion pipeline (E1.6, partial)

**Date:** 2026-09-07 · **Owner:** SRE + Writer · **Tracker:** E1.6, D1.

**Plan.** Make the ingestion pipeline reachable through `azd` and documented.

**Done.**
- `scripts/eventgrid.{sh,ps1}` already add the `landfall-inventory` subscription (cycle 1);
  reviewed — webhook `functionName=Host.Functions.ingest_blob`, subject prefix
  `/blobServices/default/containers/raw/blobs/inventory/`.
- `DEPLOY.md` + `INSTALL.md`: postdeploy now documented as two subscriptions; §"Load
  client data" rewritten around `raw/inventory/` + the DQ report; troubleshooting rows for
  "files don't load" and "wrong table / dropped columns"; note that `schema.sql` is a
  destructive recreate.
- `D1` closed except the `estimation_config.json` doc claim (removed in E6.1).

**Check.** Docs only — no runnable check. Reviewed the eventgrid scripts against the
blueprint function name.

**Deferred (still E1.6).** The live end-to-end check — `azd provision` (to apply the
schema changes: dropped FKs, new columns, `performance` / `ingest_log` tables) + `azd
deploy api` + drop a file in `raw/inventory/` on `rg-landfall` + confirm SQL + DQ report.
Needs the user to run `azd` against the live subscription; the schema recreate wipes the
current synthetic data (re-loadable from `sample-estate/`).

**Act.** E1.6 stays `in-progress` pending the live check. Proceeding to the cost engine
(E2) since it is the next audit blocker and fully buildable/testable offline.

---

## Cycle 1a — sample-estate performance & flow data (user request, out-of-band)

**Date:** 2026-09-07 · **Owner:** SWE + PMO · **Tracker:** feeds E2 (cost engine inputs),
E4 (wave engine — flow-based move groups), E10.1 (back-test reference estate).

**Ask.** Add 30 days of performance data to `sample-estate/` — CPU, memory, disk IOPS,
network ingress/egress volume — plus observed dependency data.

**Done.**
- `sample-estate/generate_estate.py` — new `build_performance()` (deterministic per
  server): 30 daily samples over 2026-08-08→09-06 for the 173 monitored+powered-on
  servers. Per day: CPU avg/peak/p95 %, memory avg/peak/p95 %, disk IOPS
  (avg/peak/read/write) + throughput, network in/out GB + peak Mbps. Weekday/weekend
  shape, ~6% spike days. Rolls up into `servers.csv` (`cpu_*_pct`, `ram_avg_pct`,
  `disk_iops_avg/peak`, `net_in_gb_30d`, `net_out_gb_30d`). 66 servers (26%) stay
  unmonitored — preserves the low-confidence path and the `effort-inputs.md` number.
- Dependencies now carry `bytes_30d_gb`, `flows_30d`, `last_seen`; ~3% stale edges.
- New files: `sample-estate/performance.csv` (5,190 rows). Regenerated all 5 CSVs.
- Schema: `dbo.performance` table; `servers` +4 cols; `dependencies` +3 cols.
- Ingestion: `landfall_performance` profile + `_NATIVE_PERF` mapping (also recognises
  generic "cpu avg / iops avg / network out gb" headers); `_NATIVE_SERVERS` / `_NATIVE_DEPS`
  extended; `loader.TABLE_COLS` + `dq.CRITICAL` updated. `tools.py` `SCHEMA_HINT` updated.
- `sample-estate/load_estate.py` loads `performance.csv`.
- Tests: +3 cases (21 total, all green). Docs: `sample-estate/README.md`,
  `generate_estate.py` docstring.

**Check.** `pytest tests -q` → `21 passed`. Distribution spot-check: cpu_avg median 21%
(over-provisioned, matches narrative), net_out_gb_30d median 68 GB / max ~2.8 TB
(ecommerce tier), deps 484 with 16 stale. Generator is deterministic (seed 42 +
per-server `random.Random("perf::"+id)`).

**Act.** Real utilisation data is now in the reference estate — unblocks building
`estimate_compute_cost` / `rightsize` (E2) against something other than summary guesses,
and flow-weighted move groups (E4). No PRD scope change.

---

## Cycle 1 — Ingestion & data-quality core

**Date:** 2026-09-07 · **Owner:** SWE (with PMO on the DQ findings) ·
**Tracker:** E1.1–E1.5 (core), D1 (partial) · **Commit:** _see git log for this cycle_

### Plan

**Objective.** Close the #1 audit blocker: a client can drop an inventory export into the
data lake and it lands in Azure SQL with a data-quality report — no manual column mapping.

**Acceptance criteria targeted this cycle**

| # | Criterion | How checked this cycle |
|---|---|---|
| A1 | The 3 source formats (Landfall-native CSV, RVTools vInfo, generic CMDB) are detected and mapped correctly | unit tests on real `sample-estate/` files + RVTools fixture |
| A2 | Units are normalised (RVTools MiB→GiB, VMware OS strings → name/version) | unit test asserts `16384 MiB → 16.0`, `"…Server 2019…" → ("Windows Server","2019")` |
| A3 | An unrecognised file loads **nothing** and says why | unit test: `unknown.csv` → `table=None` + error issue |
| A4 | The DQ report names every defect in a known-bad dump and nothing spurious | unit test on `broken_servers.csv` (dupe key, blank required, unmapped column, no perf) |
| A5 | The DQ report gives an overall confidence and a "what's missing" list | integration check renders the report for the full sample estate |
| A6 | Idempotent re-ingest keyed by `source_file` | `loader._dedupe` unit test + `DELETE … WHERE source_file=?` in `load()`; **full DB round-trip deferred** |
| A7 | `function_app.py` still parses and registers the new blueprint | ast test |

**Design.** New package `src/api/ingest/`:
`core.py` (read csv/xlsx → detect profile → normalise rows, pure), `dq.py` (data-quality
report, pure), `loader.py` (SQL upsert + `ingest_log`, lazy Azure imports),
`functions.py` (Event Grid blob trigger on `raw/inventory/{name}` + `POST /api/ingest`
+ `GET /api/ingest_status`). Profiles are declarative (`Col(sources, transform, required)`)
so a 4th format is a config edit. `scripts/schema.sql` gains `source_file` / `ingested_at`
on the 4 tables and a new `ingest_log` table; the two soft FKs are dropped (files arrive
one table at a time and out of order — the DQ report is the integrity check).
`scripts/eventgrid.{sh,ps1}` gain a `landfall-inventory` subscription.

**Explicitly deferred**

- End-to-end test through a real Event Grid trigger + Azure SQL + Blob → **tracker E1.6**
  (runs at deploy time).
- Per-engagement column-mapping override file → **tracker E1.7**.
- Relaxing FKs on the **live** `rg-landfall` DB needs a one-time `azd provision` (or manual
  `ALTER TABLE … DROP CONSTRAINT`) — postprovision recreates the tables, live data is
  synthetic. Noted for the next deploy.

**Check method.** `pytest tests -q` (pure logic, no Azure) + one scripted integration
render of the DQ report for the full `sample-estate/`. DB/trigger checks are deferred as
above.

### Do

Implemented as designed. Files:

- `src/api/ingest/{__init__,core,dq,loader,functions}.py` — new.
- `src/api/function_app.py` — register `ingest_bp`.
- `src/api/tools.py` — `SCHEMA_HINT` notes the soft links + provenance columns.
- `scripts/schema.sql` — `source_file`/`ingested_at` + `ingest_log`; soft FKs dropped.
- `scripts/eventgrid.{sh,ps1}` — `landfall-inventory` subscription.
- `tests/` — `conftest.py`, `test_ingest_core.py`, `test_ingest_dq.py`,
  `test_ingest_loader.py`, `test_smoke_imports.py`, fixtures, dev requirements, README.
- Docs (D1 partial): `README.md` (architecture + repo layout), `docs/operating-sop.html`
  (Phase 1 rewritten to the drop-in path + DQ report step), `sample-estate/README.md`.

### Check

`e:\Landfall> .venv2/Scripts/python -m pytest tests -q`

```
..................                                                       [100%]
18 passed in 0.39s
```

Integration render — DQ report for the full `sample-estate/` (servers + applications +
dependencies + storage):

```
confidence: Medium
 - 66 of 250 servers (26%) have no CPU/RAM utilisation history — right-sizing LOW confidence …
 - 67 servers (27%) are not mapped to an application — wave planning by infra role only …
 - 1 dependency endpoint is not a known server (internet) — external / unmodelled node
servers   rows=250 dupes=0 orphan_app=0 orphan_srv=0
dependencies rows=490  storage rows=573  applications rows=31
```

| # | Result |
|---|---|
| A1 | **pass** — `landfall_servers/applications/dependencies/storage` and `rvtools_vinfo` all detected; CMDB profile present (fixture-tested via headers) |
| A2 | **pass** — `16384 MiB → 16.0 GiB`; `"Microsoft Windows Server 2019 (64-bit)" → ("Windows Server","2019")`; `"poweredOff"` normalised |
| A3 | **pass** — `unknown.csv` → `table=None`, error issue, 0 rows |
| A4 | **pass** — `broken_servers.csv`: duplicate `srv-0001`, unmapped `rack_location`, `vcpu`/`ram_gb` null-rate > 0, `no_perf_data == row count`, confidence Low/Medium |
| A5 | **pass** — full-sample report is `Medium` with a correct "what's missing" list (the 26% perf-gap matches `effort-inputs.md`) |
| A6 | **partial** — `_dedupe` (last-write-wins) unit-tested; `DELETE … WHERE source_file` in `load()`; **DB round-trip deferred to E1.6** |
| A7 | **pass** — `function_app.py` parses; `from ingest.functions import ingest_bp` + `register_functions` present; blob trigger uses `BlobSource.EVENT_GRID` |

One bug found and fixed during Check: `build_report` was dict-overwriting when two files
target the same table (e.g. native + RVTools servers), producing false orphan counts.
Fixed to group results per table; re-verified.

### Act

- **Outcome:** ingestion core is built and unit-verified. The pre-sales premise ("client
  dumps to the data lake, it works") is now true for the offline path; the deploy-time
  wiring (E1.6) is the remaining piece before it is true end-to-end.
- **Tracker:** E1.1–E1.3 → `in-review` (unit-verified, deploy check pending E1.6);
  E1.4–E1.5 → `in-review`; D1 → `in-progress` (DEPLOY.md / INSTALL.md still to update);
  E1.6, E1.7 stay `backlog`.
- **PRD:** no scope change. OQ2 (isolation model) unaffected.
- **Carry-over:** DB round-trip + Event Grid trigger check; DEPLOY.md/INSTALL.md updates;
  live-DB FK migration note for the next `azd provision`.

**Next cycle — Cycle 2:** E1.6 — wire ingestion into `azd` deploy and run the end-to-end
check (drop a file in `raw/inventory/` on the live `rg-landfall`, confirm SQL + DQ report),
then finish D1 (DEPLOY.md / INSTALL.md).
