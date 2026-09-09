# Landfall — data-handling statement

**Status: DRAFT — pending review + signature by a security officer.** This is the
document a client CISO reads before approving an inventory upload. It describes
what a single Landfall engagement instance does with client data.

_Owner: Security. Last updated with Cycle 33 (E8.7)._

---

## 1. What Landfall ingests

| Accepted | Purpose |
|---|---|
| Server / VM inventory (RVTools export, CMDB extract, or CSV) | sizing, OS/EOL, disposition |
| Application portfolio (name, owner, criticality, compliance scope, tech stack) | wave planning, landing-zone design |
| Dependency / netflow export (src, dst, port, protocol, 30-day counts) | move-group affinity |
| Storage & backup inventory | storage cost |
| Narrative docs uploaded to `docs/` (network diagrams, DR runbooks, policies) | discovery context via search |
| Discovery questionnaire answers | assumptions register |

**Landfall does not ask for and should not be given:** credentials, secrets,
connection strings, private keys, end-user PII (customer records, employee data
beyond the application-owner name), cardholder data, or health records. The
ingestion pipeline does not parse or store free-text columns beyond an
application/owner label and short notes.

## 2. Where the data lives

- **One deployment per engagement.** Resources are provisioned into a single
  Azure resource group with an environment-unique name (`resourceToken`). Two
  engagements never share a storage account, database, or search index.
- **Region.** All resources are created in the single Azure region chosen at
  provision time (`primary_region`, e.g. `swedencentral`). Data does not leave
  that region except as described in §4.
- **At rest.** Azure Data Lake Storage Gen2 (inventory files, documents,
  generated deliverables, conversation transcripts) and Azure SQL Database
  (the six normalised inventory tables). Both are encrypted at rest with
  Microsoft-managed keys (AES-256); customer-managed keys are a supported
  hardening option.
- **In transit.** HTTPS/TLS 1.2+ only. The Function App and web app enforce
  Entra ID authentication (Easy Auth); anonymous requests receive `401`.

## 3. Who can see it

- **Authentication.** Microsoft Entra ID in front of both the API (Function App)
  and the dashboard (Container App). No unauthenticated access to any data plane.
- **Per-engagement isolation.** Azure SQL Row-Level Security filters every query
  by `SESSION_CONTEXT('engagement_id')` and is **fail-closed** — no context
  returns zero rows. Blob paths are namespaced per engagement.
- **Visibility.** Each engagement carries a `visibility` setting — `owner`
  (creator only), `group:<entra-object-id>` (creator + a named Entra group), or
  `all` (any signed-in user of this instance). The engagement list and every
  engagement-scoped read, the dashboard, and the chat all enforce it.
- **Conversations.** A chat thread can only be resumed through the engagement's
  server-side pointer, after the caller's visibility has been checked; a leaked
  response id cannot be replayed (E8.6).
- **Audit trail.** Engagement creation, bulk ingest, estimate publication, and
  chat turns are recorded with the acting principal to an append-only
  `_audit.jsonl` per engagement.
- **SQL safety.** Natural-language questions are compiled to a single read-only
  `SELECT` against a six-table allow-list, with a statement timeout; the client's
  question text and the generated SQL are never written to logs (a hash +
  table-shape signature is logged instead).

## 4. Processing & sub-processors

All processing is first-party Microsoft, within the same Entra tenant and Azure
region as the deployment:

| Sub-processor | Role | Data seen |
|---|---|---|
| Azure Storage / Azure SQL | primary data stores | all ingested data |
| Microsoft Foundry (Agent service) + Azure OpenAI (`gpt-4o`) | the estimator agent — turns questions into tool calls and prose | question text, tool inputs/outputs, retrieved document snippets |
| Azure AI Search | hybrid search over uploaded documents | document text + embeddings |
| Application Insights | operational telemetry | request metadata, exceptions, timings — **not** question text or SQL |
| Azure Container Apps / Functions | compute | in-memory request data only |

**Model data use.** Azure OpenAI does not use prompts or completions to train or
improve Microsoft or third-party models. Prompts and completions are processed in
the deployment's region. Abuse-monitoring logging is subject to the standard
Azure OpenAI terms and can be disabled by approved customers.

**No third parties outside Microsoft.** Landfall makes no outbound calls to
non-Microsoft services with client data. The only external fetch is anonymous,
read-only pricing data from the public Azure Retail Prices API (no client data in
the request).

## 5. Retention & deletion

- Client data persists only for the life of the engagement's Azure resource
  group.
- **Export before teardown:** the whole engagement (uploaded files, generated
  estimates, conversation) can be exported as a portable `.zip` from the
  dashboard.
- **Deletion:** `azd down` (or deleting the resource group) destroys the storage
  account, the SQL database, the search index, and all compute. No client data is
  retained by Landfall outside the resource group — there is no central store,
  no shared database, no backup outside the RG's own configuration.
- Application Insights telemetry follows its configured retention (default 90
  days) and contains no client inventory content.

## 6. Data residency

The Azure region is fixed at provision time and every resource — storage,
database, search, compute, and the Azure OpenAI deployment — is created in that
region. Cross-region replication is not enabled by default; if a DR pairing is
configured for an engagement it is disclosed to the client and stays within the
agreed geography.

## 7. Known limitations (as of this draft)

- The Azure SQL firewall currently allows connections from Azure services; the
  private-endpoint-only parameter set (E8.5) is not yet the default.
- An external penetration test has not yet been run (E10.4 / evidence pack).
- This statement has not yet been reviewed or signed.

---

## Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Security officer | _pending_ | | |
| Engagement sponsor | _pending_ | | |

_Once signed, retain the signed copy under `evidence/` and link it from
[`SCORECARD.md`](SCORECARD.md)._
