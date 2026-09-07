# Landfall — Production-Readiness Audit by an Expert Panel

> Reusable prompt. Paste into a fresh session (or hand to a review panel) to audit
> Landfall against the pre-sales scenario it is built for. Fill in the bracketed inputs
> in §1 before running.

## 1. How to use this prompt

You are convening a panel of independent senior experts to audit the **Landfall**
solution. Each expert reviews the same material through their own lens, then the panel
consolidates findings into **one prioritized backlog**.

- Work **evidence-based**. Cite specific files, line ranges, config values, prompts, or
  doc sections. "Feels immature" is not a finding; "the cost tool sums raw vCPU instead of
  rightsizing per server — `src/api/tools.py` `vm_rightsize`, and the agent prompt in
  `scripts/create_agent.py` never forces per-server iteration" is.
- For every finding, classify it: **(A) blocks production use**, **(B) hurts estimate
  defensibility / accuracy**, **(C) hurts usability or understandability**, **(D)
  operational / security / cost risk**.
- Separate *"required to stop being a toy"* from *"would be nice"*. Be explicit about
  which is which.
- Assume a **real paid engagement** depends on the output. A wrong number in a SoW is a
  financial and reputational loss, not a bug.

Repo: `github.com/upendra25312/Landfall` (direct-to-main). Docs site:
`https://upendra25312.github.io/Landfall/`. Live deployment: resource group
`rg-landfall`, `swedencentral`.

Fill in before running:
- Engagement archetype to test against: `[e.g. 250-server VMware estate, DC-exit driven, 12-month window]`
- Client's actual constraint: `[verbatim — e.g. "compliance forbids agents/collectors on-prem and any third-party SaaS discovery; client will export RVTools + CMDB + app docs to our Azure Data Lake and nothing more"]`
- Who consumes the output: `[pre-sales solution lead building a fixed-price SoW they must defend to the client's procurement and to internal delivery]`

## 2. The mission — what "production-ready" means here

Landfall exists for one situation:

> A prospective client **cannot or will not** run Azure Migrate appliances, install
> discovery collectors (DR Migrate, Movere, etc.), or use third-party discovery SaaS in
> their on-prem environment — usually a compliance / data-sovereignty / change-freeze
> reason. They **are** willing to export their own server and application inventory plus
> supporting documents into an Azure Data Lake we control.
>
> From **only that dump**, Landfall must let a **pre-sales team** produce a **defensible
> proposal**: current-state analysis, a target Azure **landing-zone design**, a
> **migration approach** per application, a **high-level migration plan** (waves,
> sequencing, timeline), the **Azure run-cost estimate**, the **one-time migration
> effort and cost**, and all the **backup data a Statement of Work can be built on and
> defended** in a commercial negotiation.

The audit question is not "does the demo work." It is:

**"If we handed this to a pre-sales team tomorrow and they used its output in a real SoW,
where would that SoW be wrong, indefensible, unusable, or unsafe — and what is the
shortest path to fixing that?"**

### The acid test (every expert runs this)

Take the engagement archetype above. Trace it end to end through the *actual* solution as
built:

1. Client exports `servers.csv` / `applications.csv` / `dependencies.csv` / narrative
   docs to ADLS. (Use `sample-estate/` as the stand-in dump — 250 VMware VMs, 31 apps,
   "Meridian Retail Group".)
2. Data is normalized → Azure SQL + AI Search.
3. Pre-sales lead interacts with the agent (chat) and the batch RFP sheet.
4. Out comes: cost, landing-zone proposal, migration effort, high-level plan, SoW inputs.

At each hop, record: what breaks, what silently produces a wrong or unsupported number,
what a pre-sales person wouldn't understand or trust, and what a client's technical
reviewer would tear apart.

## 3. Material under review

| Area | Artifacts |
|---|---|
| Architecture & build intent | `docs/build-spec.html`, `README.md` |
| Agent definition & tools | `scripts/create_agent.py` (system prompt, tool wiring), `src/api/tools.py` (`query_inventory` text-to-SQL + SELECT guard, `vm_rightsize` heuristic, `azure_retail_prices`), `src/api/openapi/*.json` |
| Ingestion & data model | `src/api/function_app.py` (Durable normalize + RFP batch runner), `scripts/schema.sql`, `scripts/setup_search.py`, `sample-estate/generate_estate.py`, `sample-estate/load_estate.py` |
| Infra | `infra/main.bicep`, `infra/resources.bicep`, `azure.yaml`, `scripts/postprovision.*`, `scripts/eventgrid.*`, `scripts/grant_api_sql.sql` |
| Pre-sales method | `docs/discovery-questionnaire.html`, `docs/effort-and-resource-loading.html`, `sample-estate/discovery-answers.md`, `sample-estate/effort-inputs.md` |
| Operability | `docs/operating-sop.html`, `INSTALL.md`, `DEPLOY.md` |
| Reference dataset | `sample-estate/` (all files) |

### Known weak points (pressure-test these; don't just repeat them — decide if they're blockers and how to close them)

- The agent's cost method is **crude**: it sums vCPU across servers rather than
  rightsizing each server and pricing the resulting SKU mix. RI/savings plans, non-prod
  and DR uplift, storage tiering, egress, and licensing (AHB / SQL / Windows) treatment
  is thin or absent.
- `query_inventory` is **anonymous** (SELECT-only guard + read-only DB user is the only
  control). Text-to-SQL correctness is unverified against a test set.
- Azure AI Search is **Free tier** — no semantic ranker (`vector_simple_hybrid` only);
  narrative-doc grounding quality is unmeasured.
- Azure SQL is the **Free serverless offer** — auto-pauses after 60 min, first query can
  time out. Fine for a lab, questionable under a consultant on a client call.
- Landing-zone output: check whether the solution actually **produces an ALZ design**
  (management-group hierarchy, subscription topology, networking/hub-spoke, identity,
  policy/guardrails, connectivity to on-prem, DR region) or only talks about cost.
- Migration plan: check whether **wave/sequencing logic is driven by the dependency and
  application data** or is a generic template.
- Inventory reality: client dumps are **incomplete and have no performance data**. Assess
  how the solution detects, surfaces, and compensates for missing utilization,
  missing dependencies, stale CMDB, unknown OS/support status, licensing ambiguity.
- Assumptions / exclusions / confidence: check they are **machine-tracked and surfaced on
  every number**, not just prose in a doc.

## 4. The expert panel

Each expert produces their own section (findings + severity + evidence + fix). Stay in
your lane; flag cross-lane issues for the consolidation step.

### 4.1 Azure Migration & Modernization Architect
Mandate: is the migration methodology sound and defensible to a client architect?
- 6 R's disposition logic — is it derived from the app/inventory data or asserted? Is
  rehost/replatform/refactor guidance actually justified per app?
- OS / DB / middleware **end-of-support** handling and its effect on disposition and cost.
- Dependency-driven **wave planning**: are waves buildable from `dependencies.csv`? How
  are dependency gaps handled? Move-group integrity, shared services, AD/DNS, file shares.
- Migration tooling assumptions in the *target* approach (ASR / Azure Migrate
  server-migration / DMS) vs. the client's *discovery* constraint — is the distinction
  made clearly (they can't run discovery collectors, but server-side replication at cutover
  may still be allowed — or may not)?
- Cutover, testing, rollback, hypercare in the plan.
- Does the high-level plan carry realistic **durations and a critical path**, or just a
  wave list?

### 4.2 Azure Landing Zone / Platform Architect
Mandate: could a platform team build from Landfall's landing-zone output?
- Does Landfall emit an actual ALZ proposal (MG hierarchy, subscription design, platform
  vs. landing-zone subs, `Corp`/`Online`, policy set, RBAC model, naming/tagging)?
- Networking: hub-spoke / vWAN, address planning, on-prem connectivity (ER/VPN), DNS,
  firewall/egress, private endpoints. Is any of this generated or is it a stock diagram?
- Identity: Entra tenant, hybrid identity, PIM, break-glass.
- DR: paired-region design, RTO/RPO tie-in to app tiers.
- Governance & guardrails: policy, cost management, Defender for Cloud, Sentinel.
- Is the ALZ output **parameterised by the client's data** (app count, tiers,
  compliance regime, regions) or one-size-fits-all?

### 4.3 FinOps / Cloud Economics expert
Mandate: are the numbers right and would they survive client scrutiny?
- Recompute the sample estate's Azure run cost **by hand** (or independent method) and
  compare to Landfall's output. Quantify the gap.
- Rightsizing: per-server SKU selection vs. vCPU-sum shortcut — model the $ difference.
- Missing performance data: what rightsizing assumption is used, is it stated, is it
  conservative or optimistic, what's the confidence band?
- Commercial levers: RI / savings plans (1yr/3yr), Azure Hybrid Benefit, dev/test
  pricing, reservations coverage %, ramp / phased consumption during migration.
- Storage: managed-disk tiering, snapshots, backup vault, archive; is storage priced from
  `storage.csv` or estimated?
- Non-prod + DR compute uplift, egress, backup, monitoring, support plan, marketplace.
- One-time migration cost: replication egress, dual-run overlap, ASR/DMS licensing, spike
  compute.
- Does every figure carry an **assumptions list, a confidence level, and a
  sensitivity** (what moves the number most)?
- Currency, region, and price-date freshness (`azure_retail_prices` caching / staleness).

### 4.4 Pre-Sales Solution Lead / Bid Manager
Mandate: can I build and *defend* a SoW from this?
- Map Landfall's outputs to the sections of a real SoW: scope, out-of-scope, assumptions,
  dependencies, deliverables, milestones, price, payment schedule, RAID, acceptance
  criteria, change control.
- What's missing that a bid team always needs: exclusions register, client obligations,
  environment/access assumptions, resource on/offshore mix, rate card application, margin.
- Defensibility: when the client says "your number is too high / your timeline too long,"
  what evidence does Landfall give the pre-sales lead to hold the line? Is the chain from
  raw inventory → assumption → number **traceable and exportable**?
- Output format: is it something a pre-sales lead can drop into a proposal deck / SoW
  template, or raw chat text they must re-key?
- The discovery questionnaire + effort model: are they self-consistent with what the
  agent produces? If the agent and the doc disagree on effort, which wins and how is that
  reconciled?
- Repeatability across deals: how much per-engagement tuning (`estimation_config.json`,
  prompt edits) does each new client require, and who is qualified to do it?

### 4.5 Data Engineer / Discovery-without-Tooling specialist
Mandate: the client dump is the only input — is ingestion robust?
- Input contract: what formats/columns does Landfall actually accept (RVTools export
  variants, ServiceNow/BMC CMDB exports, hand-built spreadsheets)? Is it documented and
  validated, or does it only work with `generate_estate.py`'s exact schema?
- Data-quality gate: dedupe, unit normalization (MiB/GB/GiB, MHz), decommissioned hosts,
  templates/clones, non-VM rows, powered-off VMs, orphans.
- Missing-data detection and reporting — a **data-quality report** the pre-sales team can
  send back to the client with "we need X, Y, Z to tighten the estimate."
- Dependency data: usually absent or partial. How is it elicited / inferred / flagged?
- Application-to-server mapping quality; multi-tenant hosts; shared DB servers.
- Idempotent re-ingestion when the client sends a corrected dump (does it re-load cleanly
  — `load_estate.py --append` vs. truncate).
- PII / sensitive data in the dump (hostnames, IPs, app owners, business names) —
  handling, retention, deletion.

### 4.6 AI / Agent Engineer
Mandate: is the agent reliable enough to put numbers in front of a client?
- Hallucination surface: where can the agent invent a SKU, a price, a count, a wave, an
  assumption? What forces every quantitative claim to come from a tool call?
- Text-to-SQL (`query_inventory`): build a **20–30 question eval set** (counts, sums,
  group-bys, joins, edge cases) and measure accuracy. SELECT-guard bypasses. Behavior on
  ambiguous questions. Does it expose the SQL for review?
- Tool-orchestration: does the agent reliably chain `query_inventory → vm_rightsize →
  azure_retail_prices` per server, or shortcut? Determinism across runs — same question,
  same answer?
- Grounding on narrative docs (Free-tier `vector_simple_hybrid`) — retrieval quality,
  citation correctness.
- Prompt/versioning: `create_agent.py` publishes a new version silently picked up with no
  redeploy — change control, regression risk, rollback.
- Evaluation harness: is there **any** automated eval? What would a minimum viable one
  look like (golden estate → golden answers → CI)?
- Cost/latency of a full estimate run; failure modes (SQL paused, price API down, search
  empty) and whether the agent degrades gracefully or bluffs.
- Conversation memory (`previous_response_id`) and multi-user isolation in the chat UI.

### 4.7 Security, Compliance & Data-Residency architect
Mandate: the whole reason the client won't use normal tooling is compliance — does
Landfall respect that?
- Where does the client's inventory data live, in which region, encrypted how, retained
  how long, deleted how? Is there a data-handling statement a client CISO could sign off?
- Tenant isolation: one Landfall per client vs. shared. Cross-client data leakage risk in
  SQL / Search / agent memory / logs.
- `query_inventory` anonymous endpoint — real risk assessment, not just "SELECT-only."
  The documented EasyAuth + managed-auth hardening: is it truly optional or must-do?
- Web UI auth (single-tenant Entra + EasyAuth) — adequate? Guest access, conditional
  access, session handling.
- Secrets: connection strings, tokens, the Container App client secret — storage,
  rotation, exposure in logs / IaC / hooks.
- Least privilege on the workload identity, the Foundry MI, deployment principals.
- Logging & audit: who ran which estimate, what data was accessed, can it be produced for
  a client audit.
- Supply chain: `mssql-python`, `azure-ai-projects` pinning, the CDN-loaded doc assets.

### 4.8 SRE / Delivery Operability reviewer
Mandate: can a consultant who didn't build this run it under deal pressure?
- Deploy repeatability: does `azd up` work clean on a fresh sub, fresh machine, per
  `INSTALL.md`? Every gap where a hook fails and needs manual steps (`azd` not on PATH,
  `sqlcmd` missing, SQL paused, Event Grid webhook) is a finding — these are documented as
  known manual workarounds today.
- Time-to-first-estimate for a new client from zero.
- The Free-tier choices (SQL auto-pause, Search Free, scale-to-zero) vs. a live client
  call — where does "cheap" become "embarrassing"? What's the paid-tier switch and its
  cost delta?
- Multi-engagement operation: 5 active pursuits at once — one deployment each? Naming,
  teardown, cost tracking, data cleanup between deals.
- Observability: how does an operator know the agent gave a bad answer?
- The SOP (`docs/operating-sop.html`) — walk it as a new user; note every place it
  assumes knowledge, skips a step, or doesn't match the built solution.
- DR/backup of the engagement data itself; accidental `azd down --purge`.

### 4.9 Delivery Lead / PMO (effort & resource realism)
Mandate: is the effort model something delivery would actually commit to?
- `docs/effort-and-resource-loading.html` + `effort-inputs.md`: sanity-check the PD
  numbers per server / per app against real migration-factory benchmarks. The sample
  claims ~554 PD delivery / ~775 EAC / ~36 PM / ~7 peak FTE for 250 servers / 31 apps —
  credible? Over/under?
- Does effort scale sensibly with disposition mix (rehost vs. replatform vs. refactor)?
- Contingency, ramp, knowledge transfer, hypercare, PM/PMO/architecture overheads.
- Resource loading vs. the wave plan — do the curves match the timeline?
- Rate card / commercial conversion — is the ~$626k in the sample defensible or a
  placeholder?

## 5. Cross-cutting rubric (each expert scores 1–5, with justification)

| Dimension | 1 = toy | 5 = production |
|---|---|---|
| **Correctness** | numbers wrong / unverifiable | reproducible, verified against independent method, within stated band |
| **Defensibility** | "trust the AI" | every number traces raw data → assumption → calc, exportable |
| **Completeness vs. mission** | cost only | cost + landing zone + migration approach + plan + SoW inputs, all generated |
| **Robustness to bad input** | needs the sample's exact schema | ingests real messy client dumps, reports data quality, degrades gracefully |
| **Usability for pre-sales** | raw chat, needs re-keying | proposal-ready output, minimal per-deal tuning, usable by non-builders |
| **Understandability** | opaque | a new consultant understands what it did and why in <1 hour |
| **Operability** | manual workarounds to deploy/run | clean deploy, repeatable per engagement, known-good under pressure |
| **Security/compliance fit** | anonymous endpoints, unclear data handling | signed-off data-handling story, tenant isolation, least privilege, audit |
| **Reliability of the agent** | non-deterministic, hallucination-prone | eval'd, grounded, deterministic where it matters, fails loud |

## 6. Required panel output

Produce, in this order:

1. **Verdict** (3–5 sentences): is Landfall today a usable pre-sales tool, a promising
   prototype, or a demo? What is the single biggest thing standing between it and real
   engagement use?

2. **Scenario walk-through result**: the acid test from §2, hop by hop — what actually
   happened, what a pre-sales lead would get, where it fails or misleads.

3. **Per-expert findings** (§4): each finding as
   `[ID] [severity A/B/C/D] [P0/P1/P2] Title — evidence (file:line / config / prompt) — impact — recommended fix — rough effort (S/M/L)`.

4. **Consolidated prioritized backlog**: all findings merged, de-duped, ranked. Group into:
   - **P0 — must fix before any real engagement use** (the "stop being a toy" list)
   - **P1 — needed before the second engagement / before scaling**
   - **P2 — hardening and polish**
   For each P0/P1: definition of done, and how to verify it's fixed.

5. **"Defensible SoW" gap list**: the specific data/outputs a pre-sales lead needs to
   build and defend a SoW that Landfall does **not** produce today, each with what would
   have to be built to close it.

6. **Recommended target-state** (1 page): what the minimum production version looks like
   — tier choices, added guardrails, the eval harness, the output artifacts, the
   per-engagement operating model — with a rough sizing of the work to get there from
   today.

## 7. Ground rules

- Cite evidence for every claim. No evidence → mark it "hypothesis, needs verification."
- Distinguish *built* from *documented-but-not-built* from *aspirational in the spec*.
- When you assert a number is wrong, show the independent calculation.
- Prefer the smallest fix that reaches production-grade over a rewrite; call out where a
  rewrite is genuinely warranted.
- The client constraint in §1 is non-negotiable — no recommendation may assume on-prem
  agents, collectors, or third-party discovery SaaS. Server-side replication *at cutover*
  is a separate question; treat it as such and flag the assumption.
- Keep the pre-sales user — not the builder — as the primary persona throughout.
