# Azure AI Landing Zone — design checklist (vendored design reference)

**Source:** Azure AI Landing Zones — design checklist
(<https://azure.github.io/AI-Landing-Zones/architecture/design-checklist/>) and the
Azure Architecture Center *Azure OpenAI / AI Foundry baseline* guidance. Distilled and
retrieved **2026-09-09** as a fixed ruleset for `src/api/lz/conformance.py`.

**Applicability:** this overlay is scored only when the portfolio contains AI / ML /
analytics workloads — an application whose `workload_type` (or name / tech stack)
indicates AI, ML, GenAI, LLM, analytics, data-science or cognitive services, or a
server running an ML runtime. Otherwise every row below is reported `n/a` and is
excluded from the met/total ratio.

## AI platform

- **AILZ-1 — Azure AI Foundry hub + project per engagement, deployed into the landing
  zone (not a standalone/public resource).**
- **AILZ-2 — Model capacity plan: Provisioned Throughput (PTU) baseline with
  Pay-As-You-Go spillover, and quota requested per region.**

## Networking & security

- **AILZ-3 — AI Foundry, Azure OpenAI, AI Search and Content Safety reachable only
  through Private Endpoints; public network access disabled.**
- **AILZ-4 — Managed identities for every AI service-to-service call; no API keys in
  app configuration.**
- **AILZ-5 — Azure API Management as the generative-AI gateway (token metering,
  throttling, multi-region load balancing, key vaulting).**
- **AILZ-6 — Grounding / RAG data stored in a private, access-controlled store
  (private AI Search, private storage).**

## Responsible AI & governance

- **AILZ-7 — Azure AI Content Safety (prompt-shield + output filtering) on every
  production inference path.**
- **AILZ-8 — Responsible-AI review: content-filter policy, abuse monitoring, and a
  documented evaluation / red-team step before go-live.**

## Operations & cost

- **AILZ-9 — AI observability: token usage, latency, cost and quality telemetry to
  the central Log Analytics workspace.**
- **AILZ-10 — Cost controls for AI spend: PTU reservation sizing, per-project budgets
  and quota alerts.**
