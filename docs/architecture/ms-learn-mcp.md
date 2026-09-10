# Microsoft Learn MCP & Knowledge Governance Architecture

**Epic Reference:** E15.1 (brief E15A.1–E15A.11)  
**Status:** Implemented & Verified (Cycle 60)  
**Author:** AI Architect & Staff Systems Engineer  

---

## 1. Overview & Purpose

Landfall integrates the official **Microsoft Learn Model Context Protocol (MCP) Server** at:
```text
https://learn.microsoft.com/api/mcp
```
The integration serves as Landfall's authoritative external reference for official Microsoft documentation, Cloud Adoption Framework (CAF) architectures, and Azure target-service best practices.

### Core Architecture Principles:
1. **Knowledge Retrieval Only**: Microsoft Learn MCP is exclusively a knowledge and reference service. It is **never** used as a numerical calculation engine.
2. **Three Authority Layers**:
   - **Customer Facts**: Grounded solely in verified Landfall engagement evidence (`dbo.*` tables and discovery questionnaire responses).
   - **Customer Numbers**: Calculated solely by deterministic Python engines (`estimate_compute_cost`, `vm_rightsize`, `estimate_storage_cost`, etc.).
   - **Microsoft Guidance**: Grounded in official Microsoft Learn MCP documentation, requiring source citations.
3. **Untrusted External Data**: All text returned from external MCP endpoints is treated strictly as **untrusted data**, never executable instructions.
4. **Confidentiality Boundary**: Queries dispatched to the external endpoint are scrubbed of customer identifiers, IP addresses, server hostnames, and secrets.

---

## 2. Protocol & Transport

- **Endpoint**: `https://learn.microsoft.com/api/mcp` (public, unauthenticated).
- **Transport**: JSON-RPC 2.0 over Server-Sent Events (SSE) / Streamable HTTP (`content-type: text/event-stream`).
- **Standard Payloads**:
  - Request:
    ```json
    {
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
        "name": "microsoft_docs_search",
        "arguments": {"query": "Azure landing zone hub spoke"}
      }
    }
    ```
  - Response:
    ```text
    event: message
    data: {"result": {"content": [{"type": "text", "text": "..."}]}}
    ```

---

## 3. Tool Allow-Listing & Discovery (E15A.7)

At client initialization and agent definition time, Landfall discovers remote tools and applies an explicit allow-list:

| Tool Name | Purpose | Parameters |
|---|---|---|
| `microsoft_docs_search` | Search official Microsoft/Azure docs and CAF guides | `query` (string) |
| `microsoft_docs_fetch` | Fetch full documentation page by URL | `url` (string) |
| `microsoft_code_sample_search` | Retrieve Bicep, Terraform, and SDK patterns | `query` (string), optional `language` |

Any unexpected or unlisted tools returned by the remote endpoint are filtered out to prevent capability confusion.

---

## 4. Defense in Depth: Untrusted Content Encapsulation (E15A.5)

External content returned by remote MCP endpoints can contain prompt injection, simulated system directives, or malicious commands.

Landfall enforces encapsulation via `encapsulate_untrusted_content()` in `src/api/mcp/learn_client.py`:
1. **XML Boundary Containment**:
   All external text is enclosed in unambiguous boundary tags:
   ```xml
   <untrusted_external_reference provider="Microsoft Learn" title="..." url="..." retrieved_at="...">
     ...content...
   </untrusted_external_reference>
   ```
2. **Instruction Quarantine**:
   Content is scanned for prompt-injection signatures:
   - `[SYSTEM INSTRUCTION: ...]`
   - `[OVERRIDE: ...]`
   - `ignore previous instructions`
   - `switch active engagement`
   - `run query ...` / `call tool ...`
3. **Escaping & Warning**:
   If suspicious signatures are detected:
   - Control brackets (`[`, `]`) and XML tags (`<`, `>`) are escaped.
   - An explicit security quarantine block is prepended inside the reference.
   - The LLM context is strictly instructed to treat the payload as inert descriptive text.

---

## 5. Confidentiality Boundary & Egress Scrubber (E15A.6)

To prevent unintentional data leakage from customer engagements to public Microsoft endpoints, `scrub_query()` sanitizes every outgoing query before dispatch:

- **Customer Identifiers**: Redacts registered customer names (`[REDACTED_CUSTOMER]`).
- **Engagement Slugs**: Strips `<customer>/<project>` paths (`[REDACTED_ENGAGEMENT]`).
- **Network Identifiers**: Redacts private and public IPv4 addresses (`[REDACTED_IP]`).
- **Server Hostnames**: Redacts pattern-matched hostnames such as `srv-*`, `server-*`, `vm-*`, `dc01.corp.*` (`[REDACTED_HOST]`).
- **Credentials & Connection Strings**: Strips connection strings, passwords, and API tokens (`[REDACTED_SECRET]`).
- **Fail-on-Leak Mode**: Optional mode for strict environments that rejects egress with an exception instead of silent scrubbing.

---

## 6. Mandatory Provenance & Citations (E15A.3)

Every architectural statement or guidance recommendation attributed to Microsoft must be backed by a `LearnCitation`:

```python
@dataclass
class LearnCitation:
    provider: str = "Microsoft Learn"
    title: str = ""
    url: str = ""
    retrieved_at: str = ""  # ISO 8601 UTC
    query: str = ""
    snippet: str = ""
    purpose: str = ""
```

**Markdown Citation Standard:**
```markdown
> [Azure Landing Zone Architecture](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/) (retrieved 2026-09-10)
```
No citation = no claim that "Microsoft recommends" a pattern.

---

## 7. FinOps Guardrails & Performance Caching (E15A.9)

To preserve the lab profile budget (< $40–50/month) and prevent agent timeout loops:

1. **Local Persistent Cache**:
   - Stored in `data/mcp_cache/` (JSON-backed).
   - Keyed by SHA-256 hash of `(tool_name + arguments)`.
   - Default TTL: **7 days** (`cache_ttl_seconds = 604,800`).
   - Cached responses return in `< 2 ms` with zero network overhead.
2. **Per-Turn FinOps Caps**:
   - `MAX_LEARN_SEARCHES_PER_TURN = 3` (configurable 1–10).
   - `MAX_LEARN_FETCHES_PER_TURN = 2` (configurable 1–10).
   - Centralized in `src/web/agent_limits.py`.
3. **Token Clipping**:
   - Responses clipped to `8,000 characters` (~2,000 tokens) with a clean truncation marker to prevent blowing agent context windows.
4. **Graceful Degradation**:
   - If Microsoft Learn MCP is unreachable or times out, the client returns `status: "unavailable"` rather than crashing the assessment pipeline.

---

## 8. Live Guidance Validation (E15A.4)

The helper `validate_guidance(decision_topic, architecture_pattern)` enables validating deterministic design decisions against live Microsoft guidance:

- Compares Landfall design against official Microsoft Cloud Adoption Framework patterns.
- Returns a structured `GuidanceValidation`:
  - `status`: `Aligned` | `Partial` | `Gap` | `N/A` | `Review`.
  - `citations`: list of `LearnCitation`.
  - `rationale`: explanation of alignment or variance.
  - `microsoft_guidance_summary`: executive excerpt.
- **Rule**: Never silently rewrites deterministic assessment figures or dispositions; flags differences for human review.

---

## 9. Verification & Quality Gates

The architecture is governed by continuous automated test suites:
- **Unit & Integration**: `tests/test_learn_mcp.py` (14 unit tests, mocked & cached transport, optional live integration test).
- **Adversarial Security Gates**: `evals/adversarial.py` (88 tests including `mcp-injection` and `data-egress` suites).
- **Static Analysis**: `ruff check src/` and `pyright src/` (0 errors).
