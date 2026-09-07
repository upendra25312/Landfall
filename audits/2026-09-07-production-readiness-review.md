# Landfall — Production-Readiness Review · Observations

**Audit prompt:** [`prompts/production-readiness-audit.md`](../prompts/production-readiness-audit.md)
**Run date:** 2026-09-07
**Reviewer:** single agent synthesising the 9 expert lenses in the prompt (not a literal panel)
**Commit reviewed:** `959e725` (main)
**Method:** static review of the repo + live-deployment notes in project memory. No live
agent runs were executed for this pass — items that need a live run to confirm are marked
**[needs live run]**.

### §1 inputs used

| Input | Value |
|---|---|
| Engagement archetype | 250-server VMware estate ("Meridian Retail Group", `sample-estate/`), DC-exit driven (Ashburn lease ends 2027-08-31), ~6-month window |
| Client constraint | No agents / collectors / discovery SaaS on-prem (compliance). Client exports RVTools + CMDB + app portfolio + docs to our Azure Data Lake and nothing more. |
| Output consumer | Pre-sales solution lead building a fixed-price / T&M-ceiling SoW they must defend to client procurement and to internal delivery |

---

## 1. Verdict

**Landfall today is a promising prototype, not a usable pre-sales tool.** The agent
surface, the tool-calling pattern, the answer contract (Answer/Basis/Assumptions/Data
gaps/Confidence), the infra, and the pre-sales method docs are genuinely good bones. But
three things stand between it and a real engagement, in order:

1. **The ingestion path the whole premise depends on does not exist.** The build spec and
   the README architecture diagram both describe a "Normalize" Durable Function that
   Event-Grid-triggers on `raw/inventory/`, sniffs RVTools/CMDB/portfolio files, maps
   columns to the schema, and loads SQL with a gap log. It is not implemented. The only
   way data reaches SQL is a human running `sample-estate/load_estate.py` locally against
   CSVs that already match `schema.sql` exactly. "Client dumps to the data lake and it
   works" is not true yet.
2. **The cost engine is not defensible.** Right-sizing without performance data is a
   fixed `vCPU / 2` haircut; RAM is never sized independently; nothing aggregates the SKU
   mix into a costed bill of materials; RI / Azure Hybrid Benefit / storage / egress /
   backup / support are the agent's in-context mental arithmetic. A client's technical
   reviewer would take this apart in the first meeting.
3. **There is no landing-zone design output and no structured deliverable.** The agent
   produces prose *about* landing zones from Microsoft Learn; it does not emit a
   client-specific ALZ (management-group hierarchy, subscription topology, hub-spoke IP
   plan, policy set, connectivity). And every output lands as chat transcript that the
   pre-sales lead re-keys by hand.

**Single biggest blocker:** #1 — build the data-lake ingestion + data-quality pipeline.
Without it the tool only works on data someone has already hand-cleaned into its exact
schema, which is the work the client said they can't do.

---

## 2. Scenario walk-through (the acid test)

Tracing the 250-server MRG estate end-to-end through the solution **as built**:

| Hop | What the spec/README promises | What actually happens | Verdict |
|---|---|---|---|
| **1. Client exports to ADLS** | `raw/inventory/` container exists; client drops RVTools/CMDB/portfolio + docs | Container exists in Bicep. Nothing consumes `raw/inventory/`. Docs in `raw/docs/` *are* picked up by the Search indexer (6-hourly). | ⚠️ half-built |
| **2. Normalize → SQL** | Durable Function: header-signature file-type detection → column map → upsert → `answers/_ingest_log.txt` gap log | **Not implemented.** Operator must hand-map the client's columns to `schema.sql`, adapt `load_estate.py`, run it locally against Azure SQL with `db_datawriter`. RVTools has ~90 columns and varies by version; CMDB exports vary by tool. | ❌ blocker |
| **3a. query_inventory** | NL → one read-only SELECT → rows + SQL | Works. gpt-4o text-to-SQL, temp 0, SELECT-only regex guard, `db_datareader` user, 200-row cap. No eval set, so accuracy is unknown; a wrong COUNT silently becomes a wrong estimate. Anonymous public endpoint. **[needs live run]** for accuracy | ⚠️ works, unverified |
| **3b. vm_rightsize** | Map each server → Azure SKU + disk tier, documented heuristic | Works mechanically. But with no `cpu_peak_pct` (the real-world case — a paper inventory has no perf data) it just halves vCPU. RAM is never sized — the SKU's RAM is whatever comes with the vCPU pick, so a 128 GB box can be silently mapped to a 32 GB SKU. | ❌ not defensible |
| **3c. azure_retail_prices** | Live PAYG + reserved prices | Works — cached proxy over `prices.azure.com`, follows paging, trims fields. Returns raw meter rows. Does **not** compute monthly cost, amortise RI, apply AHB, or price storage. | ⚠️ raw data only |
| **3d. Compute the bill** | (implied) | The agent must loop per server, join rightsize → price, sum, apply levers — all in context. The SOP's own troubleshooting table says to "check whether the agent right-sized per server or just scaled a total," i.e. it often doesn't. Non-reproducible. | ❌ blocker |
| **4. Disposition + waves** | 6 R's per app; group into waves by dependency cluster | Prompt asks for it; no tool computes move groups from the `dependencies` table. Agent would pull all edges via `query_inventory` (200-row cap — MRG has ~490) and cluster in context. Unreliable past a few dozen nodes. No wave/critical-path output structure. | ❌ not built |
| **5. Landing zone** | "what the landing zone must contain" grounded in CAF / ALZ | Returns Microsoft Learn prose. The concrete "11 spokes / hub-spoke / PCI spoke / ExpressRoute" design exists only as hand-written synthetic text in `sample-estate/effort-inputs.md`, retrieved by search — not generated from the client's data. | ❌ not built |
| **6. Effort + cost → SoW** | Pull deliverable lines; apply firm rates via `estimation_config.json` | `estimation_config.json` is referenced in README + SOP but **nothing reads it** — not `create_agent.py`, not `tools.py`, not the prompt. The agent has no rate card, no effort bands, no uplift %. It invents or omits them. Output is chat text + an `.xlsx` of Q/A rows; assumptions are per-answer prose to be merged by hand. | ❌ blocker |

**What a pre-sales lead would actually get from a full run today:** correct inventory
counts and totals (assuming the load was mapped right), a rough compute run-rate with
shaky sizing, generic landing-zone talking points, a hand-assembled disposition list, and
no traceable link from raw data → assumption → number. Not enough to build a defensible
SoW; enough to accelerate a manual estimate a competent architect was already going to
do.

---

## 3. Findings by lens

Severity: **A** blocks production use · **B** hurts defensibility/accuracy · **C** hurts
usability/understandability · **D** operational/security/cost risk.
Priority: **P0** before any real engagement · **P1** before the 2nd engagement / scale ·
**P2** hardening.

### 3.1 Migration & Modernization Architect

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| MA-1 | A | P0 | No move-group / wave engine. Wave grouping is asked of the LLM with no tool support and a 200-row cap below MRG's ~490 dependency edges. | `create_agent.py:52-54`, `tools.py:36` `MAX_ROWS`, `schema.sql` `dependencies` | Add a `plan_waves` tool: pull the full edge list, build connected components / affinity groups, order by criticality + risk, return waves with entry/exit and blocking deps. | M |
| MA-2 | B | P1 | 6 R's disposition is LLM-asserted, not rule-derived. No link from OS EOL / tech stack / criticality / internet-facing → disposition. | `schema.sql:21` (`disposition` "agent-filled"), no scoring code | Add a deterministic disposition scorer (inputs → candidate R + rationale) the agent explains rather than invents. | M |
| MA-3 | B | P1 | OS end-of-support drives nothing. `os_eol_date` is in the schema; no tool flags ESU cost, forced-upgrade effort, or disposition impact. | `schema.sql:32` | Fold EOL into the disposition scorer and the cost model (ESU line). | S |
| MA-4 | C | P1 | The "client can't run discovery tooling" constraint vs. "target migration may use ASR/DMS at cutover" distinction is never stated. A reviewer will conflate them. | prompt, docs | One paragraph in the prompt + SOP: discovery is paper-only; replication tooling at cutover is a separate assumption to confirm (see `discovery-answers` F5). | S |
| MA-5 | C | P2 | High-level plan has no durations or critical path — `effort-inputs.md` has a wave list and a phase overlay but the agent can't produce the equivalent for a real estate. | `effort-inputs.md §5` | `plan_waves` output feeds a simple duration model (servers/wave ÷ throughput). | M |

### 3.2 Landing Zone / Platform Architect

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| LZ-1 | A | P0 | No ALZ design is produced. Only Learn prose. No MG hierarchy, subscription topology, hub-spoke, IP plan, policy set, identity, connectivity, DR region. | `create_agent.py:54`, SOP `#p2` step 4 | Wire the just-installed **azure-enterprise-infra-planner** flow (or a `design_landing_zone` tool) to emit an `infrastructure-plan.json`-shaped design parameterised by app count, tiers, compliance regime, regions. | L |
| LZ-2 | B | P1 | Spoke/topology sizing (`effort-inputs.md`: "11 spokes") is hand-authored synthetic content, not derived from `applications` / `compliance_scope`. | `effort-inputs.md:19` | Derive spoke count + regulated-spoke flag from the app portfolio in the LZ tool. | M |
| LZ-3 | B | P2 | No WAF-reliability / DR tie-in to app criticality (RTO/RPO per tier). | schema has `criticality`; no mapping | Add a criticality→resiliency-tier table to the LZ output. | S |

### 3.3 FinOps / Cloud Economics

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| FIN-1 | B | P0 | No-perf-data right-sizing is `needed = vcpu / 2.0` — an arbitrary 50% cut, not an analysis. Real paper inventories have **no** perf data, so this is the default path. | `tools.py:213-214` | Replace with a documented, conservative model: keep vCPU (or cut to a configurable %), band by workload class, wide confidence range, and *state the range in dollars*. Make the haircut a config knob, not a constant. | M |
| FIN-2 | B | P0 | RAM is never sized. `_rightsize_one` picks the SKU by vCPU only (`row[0] >= needed`); RAM is whatever the SKU carries. A 4-vCPU/128 GB box → E-family by ratio → `E4s_v5` (32 GB) if `vcpu/2=2`. Silent 4× under-provision. | `tools.py:201-227` | Size against `max(vcpu_need, ram_need)`; pick the smallest SKU meeting both; report both dimensions and which one bound. | S |
| FIN-3 | A | P0 | Nothing aggregates per-server SKUs into a costed BoM. `azure_retail_prices` returns raw meter rows; monthly cost = hours × price × count, RI amortisation, AHB, dev/test pricing, and roll-up are all in-context arithmetic. Non-reproducible, unverifiable. | `tools.py:268-306` | Add an `estimate_compute_cost` tool: takes the rightsize output, fetches prices, computes monthly PAYG + 1yr/3yr RI + AHB variants, returns a line-item table with region + term + price date. | M |
| FIN-4 | B | P1 | Storage cost is not modelled. `storage` table + disk GB exist; no join to managed-disk tier price, snapshots, backup vault, ANF for file shares. | `tools.py` (no storage pricing), `schema.sql:59` | Extend the cost tool: `used_disk_gb` → disk tier → price; file → ANF/Files; DB → PaaS tier. | M |
| FIN-5 | B | P1 | No egress, backup, monitoring, support plan, marketplace, or one-time migration cost (replication egress, dual-run overlap, ASR). | cost tooling scope | Add a fixed-plus-parametric "run-rate extras" and a "one-time migration cost" section to the cost tool. | M |
| FIN-6 | B | P1 | No sensitivity / "what moves the number most". Confidence is a word, not a band. | answer contract | Cost tool returns low/expected/high and the top 3 drivers. | S |
| FIN-7 | C | P2 | `azure_retail_prices` price-date freshness: 6 h cache TTL is fine, but the returned `effectiveStartDate` isn't surfaced as "price date" in a structured field the agent must quote. | `tools.py:246-250` | Return a single `price_date` in the tool response. | S |
| FIN-8 | C | P2 | `azure-cost` skill (just installed) is actual-spend only — cannot help pre-sales estimation. Don't route estimate questions to it. | skill docs | Note in the agent prompt / operator guide. | S |

### 3.4 Pre-Sales Solution Lead / Bid Manager

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| PS-1 | A | P0 | `estimation_config.json` is documented as the mechanism for firm rates/bands/uplifts but **is not implemented anywhere**. The agent has no rate card. | `README.md:90-98`, SOP `#p4` step 2; absent from `create_agent.py`, `tools.py` | Implement it: a config blob (rates, S/M/L/XL bands, RI term, non-prod/DR uplift %, overhead %) loaded into the agent context or a `get_firm_rates` tool. Until then, remove the claim from the docs. | M |
| PS-2 | A | P0 | Output is chat transcript + a Q/A `.xlsx`. No structured, exportable pre-sales package (current-state, BoM, LZ, disposition, waves, cost, effort, assumptions register, exclusions). | SOP `#p4` ("gather from the chat transcript") | Add an "assemble estimate" batch flow that emits a single structured document (JSON + rendered) with all deliverable sections and a machine-tracked assumptions/gaps register. | L |
| PS-3 | B | P0 | No traceable chain raw data → assumption → number. Assumptions are per-answer prose to merge by hand; the SQL is shown but not linked to the figure it fed. | `tools.py` responses, SOP `#p4` step 3 | Every number in the assembled package carries: source tool + query/filter, assumptions applied, confidence, and a stable ID. | M |
| PS-4 | B | P1 | No exclusions register, client-obligations list, or environment/access assumptions — always needed in a SoW. | docs | Add these as fixed sections seeded from the discovery questionnaire's assumption register. | S |
| PS-5 | C | P1 | Agent vs. `effort-and-resource-loading.html` can disagree on effort with no reconciliation rule. | two sources of effort | Decide: the doc's model is authoritative; the agent produces the *inputs* (counts, disposition mix), the model computes PD. Wire that. | M |
| PS-6 | C | P2 | Per-engagement tuning burden is undefined — who edits the prompt / config per client, and how is that change-controlled? | `create_agent.py` versioning | Document the operating model; keep per-client config out of the prompt (see PS-1). | S |

### 3.5 Data Engineer / Discovery-without-Tooling

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| DE-1 | A | P0 | The Normalize ingestion function is unbuilt (see Verdict #1). No file-type detection, no column mapping, no upsert, no gap log. | `build-spec.html:186,303-306` vs `function_app.py` (RFP runner only) | Build it: Event Grid trigger on `raw/inventory/`, header-signature routing (RVTools vCPU/vInfo tabs, common CMDB shapes), configurable column map, upsert into the 4 tables, write `answers/_ingest_log.txt`. | L |
| DE-2 | A | P0 | Input contract is "match `schema.sql` exactly". Only `generate_estate.py`'s output and hand-adapted `load_estate.py` fit. Real RVTools/CMDB exports don't. | `load_estate.py:24-36`, `sample-estate/README.md:18` | A mapping layer (DE-1) + a documented, versioned input spec with per-source templates. | M |
| DE-3 | A | P0 | No data-quality gate or report. No dedupe, unit normalisation (MiB/GiB/GB, MHz), powered-off/template/decommissioned handling, orphan detection, or completeness scorecard. `generate_estate.py` produces clean data so this is untested. | no DQ code anywhere | A `data_quality_report` step after ingest: row counts, null-rate per critical column, dupes, unmapped columns, FK orphans, "fields missing that the estimate needs" — output to `answers/` for the client. | M |
| DE-4 | B | P1 | Dependency data is assumed present. Real clients rarely have it. No elicitation/inference/flagging path; wave planning silently degrades. | `dependencies` table, MA-1 | DQ report flags dependency coverage %; wave tool states confidence when coverage is low; questionnaire chases it. | S |
| DE-5 | B | P1 | Re-ingestion of a corrected client dump: `load_estate.py` default is `DELETE FROM` all tables then reload (not upsert). A partial re-send wipes prior rows. | `load_estate.py:65-69` | DE-1 does keyed upsert; keep a full-reload mode explicit. | S |
| DE-6 | D | P1 | PII in the dump (hostnames, IPs, owners, business names) has no handling/retention/deletion policy beyond "delete the storage account if the contract says so". | SOP `#p5` step 3 | A documented data-handling lifecycle (see SEC-4). | S |

### 3.6 AI / Agent Engineer

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| AI-1 | A | P0 | No evaluation harness. text-to-SQL, tool orchestration, cost math, and grounding are all unmeasured. A wrong COUNT → wrong estimate, silently. | no `evals/` anywhere | Build a golden set: `sample-estate` → 25–30 NL questions with known answers, plus 5–8 full-estimate scenarios with expected ranges. Run via the **microsoft-foundry** skill's eval flow in CI on every `create_agent.py` change. | M |
| AI-2 | B | P0 | Hallucination surface is wide: the agent does cost arithmetic, wave clustering, and rate assumptions in-context with nothing forcing tool-sourced numbers. | `create_agent.py:49-62` prompt | FIN-3 + MA-1 move the math into tools; tighten the prompt to "never compute a cost or a wave yourself — call the tool". | M |
| AI-3 | B | P1 | text-to-SQL guard is regex deny-list. Doesn't stop `WAITFOR DELAY` (time-based), `sys.*`/`INFORMATION_SCHEMA` catalog enumeration, or expensive cartesian joins (DoS). `\binto\b` also blocks legit `SELECT … INTO @v`. | `tools.py:87-111` | Prefer an allow-list parse (single SELECT, known tables only) + a statement timeout + `SET LOCK_TIMEOUT`. Constrain to the 4 tables. | M |
| AI-4 | B | P1 | Agent prompt/version change control: `create_agent.py` publishes a new version picked up live with no redeploy, no regression gate, no rollback record. | `create_agent.py:114`, SOP appendix | AI-1's eval set becomes the gate; record version + eval score; document rollback (`create_version` of the prior definition). | S |
| AI-5 | C | P1 | Batch runner answers each question in an isolated `responses.create` (no `previous_response_id`), so "how many prod servers" and "total prod vCPU" can be answered by different runs that disagree. | `function_app.py:150-168` | For a batch, run a single threaded pass or pin a shared context snapshot; or post-validate cross-question consistency. | M |
| AI-6 | C | P2 | `previous_response_id` chaining assumes server-side response storage is on by default for Azure Foundry Responses API — unverified. If `store` defaults false, chat memory silently breaks. **[needs live run]** | `app.py:68-70` | Confirm; set `store=True` explicitly if needed. | S |
| AI-7 | C | P2 | Free AI Search: 50 MB cap, no SLA, `vector_simple_hybrid` only. Retrieval quality on real doc volume untested. | `resources.bicep:120-135`, `create_agent.py:95` | Measure recall on the golden set; document the Basic-tier upgrade ($) as the switch when doc volume grows. | S |
| AI-8 | C | P2 | `azure_retail_prices` `_price_filter` interpolates user input into OData strings — breaks on `'`, and is sloppy (OData injection into a public API). | `tools.py:253-265` | Escape single quotes; validate SKU/region against known patterns. | S |

### 3.7 Security, Compliance & Data-Residency

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| SEC-1 | A | P0 | `query_inventory` is an anonymous public HTTPS endpoint returning arbitrary SELECT results over **all** client inventory in the DB. The regex guard + `db_datareader` limit the *shape* of abuse, not *access*. | `tools.py:126`, DEPLOY "Harden query_inventory" is marked optional | Make EasyAuth + `AGENT_TOOL_AUTH=managed` a **required** deploy step, not "recommended". Better: move the tool behind the Function app's Entra auth by default and document opening it, not closing it. | S |
| SEC-2 | A | P0 | No tenant/engagement isolation. One SQL DB, one Search index, one storage account, one agent for every client. Two live engagements = commingled confidential data, or full teardown between clients. | `resources.bicep` (single instances), SOP `#p5` (contradicts itself: "park it" vs `azd down --purge`) | Decide the model: one deployment per engagement (make `azd up`/`down` reliable and fast — see OPS-1) **or** add a `client_id` column + row-level security + per-client Search index. Per-engagement deployment is simpler and safer. | M–L |
| SEC-3 | D | P1 | SQL firewall rule `0.0.0.0`→`0.0.0.0` allows every Azure tenant's services; `publicNetworkAccess: Enabled`; no private endpoints. Combined with SEC-1 the client-data attack surface is real. | `resources.bicep:225-229,197` | Private endpoints for SQL + Storage + Search + Foundry; drop the all-Azure firewall rule; VNet-integrate the Function and Container App. Offer a "hardened" parameter set. | L |
| SEC-4 | A | P0 | No data-handling statement a client CISO could sign. Where the data lives, region, encryption, retention, deletion, sub-processors (Foundry, App Insights) — undocumented beyond one SOP line. | SOP `#p0` step 3, `#p5` step 3 | Write a one-page data-handling doc: residency (region-pinned), encryption at rest/transit, retention window, deletion procedure + evidence, what Foundry/AOAI retains, logging scope. This is table-stakes given the whole premise is compliance. | S |
| SEC-5 | D | P1 | Client SQL text (and possibly data) is written to App Insights on error: `logging.warning("unsafe SQL for %r", question)`, `logging.exception("query failed")`. Log retention 30 days, no scrubbing. | `tools.py:138,154`; `resources.bicep:52` | Log a hash / template, not the question or SQL; document log retention in SEC-4. | S |
| SEC-6 | C | P1 | Web UI conversation isolation is weak: `previous_response_id` comes from the browser as `thread_id` with no per-user binding. Single-tenant limits blast radius to colleagues, but a leaked/shared id resumes someone else's thread. | `app.py:54-70` | Bind thread ids to the EasyAuth user principal server-side. | M |
| SEC-7 | C | P2 | `disableLocalAuth: false` on the Foundry account; `allowSharedKeyAccess: false` on storage is good but Search uses `aadOrApiKey`. | `resources.bicep:151,133` | Set `disableLocalAuth: true` on Foundry; `disableLocalAuth` / `apiKeyOnly:false` equivalent on Search. | S |
| SEC-8 | C | P2 | Supply chain: `azure-identity`, `azure-storage-blob` unpinned in `src/api/requirements.txt`; doc pages load fonts from Google CDN. | `src/api/requirements.txt:3,5` | Pin all runtime deps; note the CDN dependency. | S |

### 3.8 SRE / Delivery Operability

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| OPS-1 | A | P0 | `azd up` does not reliably run end-to-end. Documented manual workarounds: `azd` not on PATH so hooks fail; `sqlcmd` missing so the SQL grant is applied by hand; Event Grid subscription needs a separate postdeploy hook; first SQL connect times out on resume. | project memory; `create_agent.py` WARN paths; SOP troubleshooting rows | Make hooks self-contained (no `azd` dependency inside hooks — pass values as env/args); bundle the SQL grant via a Python step not `sqlcmd`; retry-wrap the first SQL connect; test a clean-machine `azd up` in CI. | M |
| OPS-2 | D | P0 | No observability of answer quality. Nothing tells an operator the agent gave a bad number. | App Insights is wired for infra telemetry only | Emit structured traces per tool call (inputs, SQL, row counts, prices, final number) to App Insights; a simple dashboard; alerts on tool error rate. Pair with AI-1. | M |
| OPS-3 | C | P1 | Free-tier choices vs. a live client call: SQL auto-pauses (60 min) → 30–60 s stall; Container App scale-to-zero → ~10 s cold start; Search Free no SLA. | `resources.bicep:216,295`; SOP troubleshooting | A `--tier prod` parameter set (SQL serverless min-capacity up or provisioned; Container App min-replica 1; Search Basic). Document the cost delta (~$150–400/mo). | S |
| OPS-4 | C | P1 | Multi-engagement operation undefined (naming, teardown, cost tracking, data cleanup between deals). Ties to SEC-2. | SOP `#p5` | Per-engagement `azd env` naming convention + a checklist; `azd down --purge` + Foundry/KV purge as the documented close-out. | S |
| OPS-5 | C | P2 | The SOP assumes the reader can hand-map RVTools→schema and adapt a load script ("Phase 1 step 3"). That's a data-engineering task, not a pre-sales one. | SOP `#p1` step 3 | DE-1 removes the need; until then, the SOP should be explicit that step 3 requires an engineer. | S |
| OPS-6 | D | P2 | No backup of the engagement data itself; `azd down --purge` is irreversible and one line away in the SOP. | SOP `#p5` step 2 | Document an export-before-teardown step (dump the 4 tables + docs to a retained location). | S |

### 3.9 Delivery Lead / PMO (effort realism)

| ID | Sev | Pri | Finding | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| PM-1 | B | P1 | Effort unit rates in the model are asserted, not benchmarked. Rehost @ 0.5 PD/server is optimistic (aggressive automation, few surprises); testing 84 PD for 31 apps incl. 4 PCI + 2 XL is light. | `effort-inputs.md §4` | Calibrate the bands against real delivery actuals; widen or annotate as "illustrative pending rate card". | M |
| PM-2 | B | P1 | 12% inventory-quality contingency is low for an estate with 26% missing perf data and unvalidated dependencies. Real pre-sales carries 20–30%. | `effort-inputs.md:73` | Tie contingency to the DE-3 data-quality score, not a fixed %. | S |
| PM-3 | C | P2 | The model and the agent aren't connected — the agent can't produce the doc's roll-up for a real estate (see PS-5). | `effort-and-resource-loading.html` | Agent emits inputs; the parametric model (implemented as a tool or config) computes PD + resource loading. | M |
| PM-4 | C | P2 | Resource-loading curve is hand-fitted to the sample; no derivation from wave count/size. | `effort-inputs.md §5` | Generate the loading curve from `plan_waves` output + role ratios. | M |

---

## 4. Consolidated prioritized backlog

### P0 — must fix before any real engagement ("stop being a toy")

| # | Item | Rolls up | DoD / verify |
|---|---|---|---|
| P0-1 | **Build the data-lake ingestion + data-quality pipeline** — Event Grid Normalize function: file-type detection, configurable column mapping (RVTools + at least one CMDB shape), keyed upsert to the 4 tables, `_ingest_log.txt` gap log, and a `data_quality_report` artifact. | DE-1,2,3,4,5; OPS-5 | Drop a raw RVTools export + a messy CMDB CSV into `raw/inventory/`; SQL is populated; `answers/` has an ingest log naming every unmapped column and a completeness scorecard. No manual `load_estate.py`. |
| P0-2 | **Cost engine as tools, not prose** — `estimate_compute_cost` (rightsize → price → monthly PAYG/1yr/3yr/AHB, line-item BoM, region+term+price-date) + storage pricing + run-rate extras + one-time migration cost. Fix RAM sizing (FIN-2) and the `vcpu/2` haircut (FIN-1). | FIN-1..7; AI-2 | For the MRG estate the agent returns a costed BoM table that an independent hand-calc matches within the stated band; every figure carries region/term/date; re-running gives the same number. |
| P0-3 | **Landing-zone design output** — wire `azure-enterprise-infra-planner` (or a `design_landing_zone` tool) to emit a client-specific ALZ: MG hierarchy, subscription topology, hub-spoke + IP plan, policy set, identity, connectivity, DR region, regulated spoke — parameterised by the app portfolio + compliance scope. | LZ-1,2,3 | For MRG the agent produces an ALZ design doc that a platform engineer says they could build from, with the PCI spoke and ExpressRoute derived from the data, not a template. |
| P0-4 | **Wave / move-group engine** — `plan_waves` tool: full dependency graph → affinity groups → risk-ordered waves with entry/exit criteria and blocking deps; feeds a duration model. | MA-1,5; DE-4 | For MRG, waves are reproducible, respect the dependency graph, and the low-risk-first ordering is explained. |
| P0-5 | **Structured deliverable + traceability** — an "assemble estimate" flow that emits one structured package (current-state, BoM, LZ, disposition, waves, cost, effort, assumptions register, exclusions), every number carrying source + assumptions + confidence + stable id. | PS-2,3,4 | A pre-sales lead can take the package into a SoW with no re-keying and answer "where did this number come from?" for any line. |
| P0-6 | **Implement `estimation_config.json`** (firm rates, S/M/L/XL bands, RI term, uplift %, overhead %) — or delete the claim from the docs until it exists. | PS-1,5; PM-3 | The agent's effort + cost output visibly uses the firm's configured numbers; changing the config changes the output. |
| P0-7 | **Evaluation harness in CI** — golden NL-question set + full-estimate scenarios with expected ranges, run via the foundry eval flow on every agent change; becomes the version gate. | AI-1,2,4 | `make eval` (or CI) reports pass/fail; a regression in text-to-SQL or cost math fails the build. |
| P0-8 | **Require `query_inventory` auth + a data-handling statement** — flip EasyAuth + managed-auth from "recommended" to default; publish the one-page CISO-signable data-handling doc. | SEC-1,4,5 | Anonymous `curl` of the endpoint returns 401; the data-handling doc exists and covers residency/retention/deletion/sub-processors. |
| P0-9 | **Decide + implement engagement isolation** — recommend one deployment per engagement; make `azd up`/`down` reliable and fast (fix the hooks). | SEC-2; OPS-1,4 | Two engagements never share a datastore; a clean-machine `azd up` succeeds in CI with no manual steps. |

### P1 — before the second engagement / before scaling

- MA-2, MA-3, MA-4 — disposition scorer (rule-derived), EOL→cost/effort, discovery-vs-cutover-tooling wording.
- FIN-4, FIN-5, FIN-6 — storage cost, run-rate extras + one-time cost, sensitivity/ranges.
- AI-3, AI-5 — allow-list SQL parse + statement timeout; batch cross-question consistency.
- SEC-3, SEC-6 — private endpoints / hardened parameter set; bind chat threads to the auth principal.
- OPS-2, OPS-3, OPS-4 — answer-quality observability; `--tier prod` parameter set; multi-engagement runbook.
- PS-5, PM-1, PM-2 — reconcile agent vs. effort model; calibrate unit rates; data-quality-linked contingency.
- DE-6 — data lifecycle doc.

### P2 — hardening & polish

- AI-6, AI-7, AI-8 — confirm response storage; measure Search recall; fix OData escaping.
- SEC-7, SEC-8 — `disableLocalAuth`; pin deps.
- LZ-3, MA-5, PM-4 — resiliency tiers; plan durations; derived resource-loading curve.
- OPS-6 — export-before-teardown.
- FIN-7, FIN-8 — structured `price_date`; note `azure-cost` is out of scope for estimation.

---

## 5. "Defensible SoW" gap list

Data / outputs a pre-sales lead needs to build and defend a SoW that Landfall does **not**
produce today:

| Gap | What's needed to close it |
|---|---|
| **Costed Azure bill of materials** (per workload group: SKU, qty, monthly PAYG + RI + AHB, storage, region, price date) | P0-2 |
| **One-time migration cost** (replication egress, dual-run overlap, tooling, spike compute) | FIN-5 |
| **Landing-zone design + build estimate** (topology, spokes, policy, connectivity → LZ build PD) | P0-3, LZ-2 |
| **Wave plan with durations and a critical path** (not just a wave list) | P0-4, MA-5 |
| **Disposition rationale per app** (why Rehost vs Replatform, tied to EOL / stack / criticality) | MA-2, MA-3 |
| **Effort estimate traceable to counts** (the parametric model run on the client's actuals, not a static doc) | P0-6, PS-5, PM-3 |
| **Machine-tracked assumptions & exclusions register** with confidence per line | P0-5, PS-4 |
| **Data-quality / completeness report** to send back to the client ("we need X, Y, Z to firm this up") | P0-1 (DE-3) |
| **Traceability**: for any number, "which query/tool/doc produced it and under what assumptions" | P0-5 (PS-3) |
| **Client-signable data-handling statement** (needed to get the inventory in the first place) | P0-8 (SEC-4) |
| **Sensitivity analysis** ("the estimate moves ±X% on these 3 assumptions") | FIN-6 |

---

## 6. Recommended target-state (minimum production version)

**Shape:** one Landfall deployment per engagement. `azd up` → load → estimate → export →
`azd down --purge`. No shared datastores, simplest isolation story, matches the
"confidential client data" premise.

**Pipeline:**
1. Client drops raw exports in `raw/inventory/` + docs in `raw/docs/`.
2. **Normalize function** maps and loads SQL; emits an **ingest log** + **data-quality
   report** (completeness scorecard, what's missing for the estimate).
3. Agent runs the estimate through **tools that do the math**: `query_inventory` (auth'd,
   allow-list parsed), `vm_rightsize` (RAM-aware, config-driven haircut),
   `estimate_compute_cost` (BoM + RI/AHB + storage), `plan_waves` (dependency-driven),
   `design_landing_zone` (ALZ from the portfolio), plus `search_documents` /
   `microsoft_docs` for grounding.
4. **`estimation_config.json`** supplies the firm's rates/bands/uplifts; a parametric
   effort model turns counts + disposition mix into PD + resource loading.
5. **"Assemble estimate"** emits one structured package with a machine-tracked
   assumptions/exclusions register and full source-to-number traceability.
6. **Eval harness** gates every agent change in CI.

**Tiers:** `--tier prod` (SQL min-capacity up or provisioned, Container App min-replica 1,
Search Basic for the semantic ranker) — cost delta ~$150–400/mo, on only during an active
engagement.

**Guardrails:** `query_inventory` auth on by default; private endpoints as an option;
client SQL text kept out of logs; a published data-handling statement; per-engagement
teardown + purge checklist.

**Rough sizing to get there from today:**

| Workstream | Effort |
|---|---|
| P0-1 ingestion + data-quality pipeline | ~2–3 wk |
| P0-2 cost engine (tools + tests) | ~2 wk |
| P0-3 landing-zone output (wire the skill + shape the deliverable) | ~2 wk |
| P0-4 wave engine | ~1 wk |
| P0-5 structured deliverable + traceability | ~2 wk |
| P0-6 estimation_config + effort model | ~1 wk |
| P0-7 eval harness | ~1 wk |
| P0-8 auth + data-handling doc | ~3 d |
| P0-9 isolation decision + `azd up` reliability | ~1 wk |
| **Total P0** | **~10–12 weeks, 1–2 engineers** |

P1 is a further ~4–6 weeks. After P0 the tool is usable on a real engagement with
architect oversight; after P1 it scales past the first one.

---

## 7. Rubric scores (1 = toy, 5 = production)

| Dimension | Score | Note |
|---|---|---|
| Correctness | **2** | Counts likely right; sizing and cost math are not defensible; no verification. |
| Defensibility | **1** | No raw-data → assumption → number trace; assumptions are loose prose. |
| Completeness vs. mission | **2** | Cost (rough) + disposition; **no** ingestion, landing-zone design, wave engine, or structured deliverable. |
| Robustness to bad input | **1** | Needs the sample's exact schema; no data-quality gate; clean synthetic data only. |
| Usability for pre-sales | **2** | Good chat + answer contract; output is a transcript to re-key; `estimation_config` doesn't exist. |
| Understandability | **3** | Strong docs and SOP; the SOP overstates what's built (Normalize, config). |
| Operability | **2** | `azd up` needs manual workarounds; no answer-quality observability; Free-tier stalls on live calls. |
| Security / compliance fit | **2** | Good identity hygiene (MI, Entra-only SQL, no shared keys); anonymous data endpoint, no isolation, no data-handling statement — weak given the premise. |
| Reliability of the agent | **1** | No evals; wide hallucination surface (math + planning in-context); silent version swaps. |

**Overall: ~1.8 / 5 — prototype.** The architecture and the pre-sales method are sound;
the parts that turn a client's paper inventory into defensible numbers are mostly not
built yet.
