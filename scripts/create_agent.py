"""
Create (or version) the Landfall "Migration Estimator" agent in the Foundry project
and print its name.  Called by the postprovision hook; can also be run by hand.

This targets the current Microsoft Foundry Agents surface (prompt agents, Responses
API, versioned).  The agent is referenced everywhere by NAME, not an `asst_` id.

Reads from environment (azd populates these in .azure/<env>/.env):
  FOUNDRY_PROJECT_ENDPOINT
  AZURE_OPENAI_CHAT_DEPLOYMENT
  AZURE_SEARCH_INDEX_NAME
  SERVICE_API_NAME              Function app name - OpenAPI tools point at it
  AGENT_TOOL_AUTH              (optional) "managed" -> query_inventory uses the Foundry MSI
  FUNC_AUTH_AUDIENCE          (optional) audience for managed auth, default api://<SERVICE_API_NAME>

Writes AGENT_ID back to stdout as `AGENT_ID=<name>` (the hook captures it with `azd env set`).
"""
import json
import os
import sys

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    MCPTool,
    AzureAISearchTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    OpenApiTool,
    OpenApiFunctionDefinition,
    OpenApiAnonymousAuthDetails,
    OpenApiManagedAuthDetails,
    OpenApiManagedSecurityScheme,
)

AGENT_NAME = "landfall-migration-estimator"

# OpenAPI specs for the Function tools live next to src/api
_OPENAPI_DIR = os.path.join(
    os.path.dirname(__file__), "..", "src", "api", "openapi"
)
_OPENAPI_TOOLS = {
    "query_inventory": "Count / sizing / aggregation questions over the client inventory (Azure SQL).",
    "vm_rightsize": "Deterministic Azure VM SKU + disk tier per server - sizes vCPU and RAM independently, uses utilisation data when present, driven by estimation_config.json.",
    "estimate_compute_cost": "Monthly Azure compute + managed-disk cost (bill of materials, PAYG/reserved/AHB, per-environment, low/expected/high) for a set of servers. Right-sizes and prices in one call.",
    "estimate_storage_cost": "Monthly Azure cost for the storage inventory (dbo.storage) - file shares (Files Premium / NetApp), DB volumes (SQL MI / Hyperscale / Flexible Server / Oracle), object (Blob). Block/managed-disk volumes are covered by estimate_compute_cost and excluded here.",
    "estimate_run_rate_extras": "Run-rate lines beyond compute + storage - backup, internet egress, monitoring (Log Analytics + Defender), support plan - plus one-time migration cost (tooling, replication, dual-run). Pass the servers and the compute+storage monthly total.",
    "design_landing_zone": "Client-specific CAF Azure Landing Zone from the application portfolio - management groups, subscriptions, hub-spoke VNets + IP plan, policy set, identity, connectivity, DR, and a dedicated regulated spoke per compliance scope. Topology is derived from the data.",
    "score_dispositions": "Rule-derived 6R disposition (Rehost / Replatform / Repurchase / Retire / Retain / Refactor) + rationale + confidence per application, from OS EOL, stack, criticality, internet-facing and DB engine. Repurchase / Refactor / Retire need business sign-off.",
    "plan_waves": "Risk-ordered migration wave plan - server dependency graph -> affinity move-groups -> waves (pilot first, regulated last) with entry/exit criteria and cross-wave blocking dependencies. Pass applications + servers + dependencies.",
    "assemble_estimate": "Assembles every other tool's output + an inventory summary into ONE structured estimate package: 8 sections, a stable ID + calculation appendix on every figure, an assumptions/exclusions/data-gaps register, a parametric effort + services-cost estimate, and a markdown render. Call this last.",
    "export_estimate": "Renders the assembled estimate package into a client-ready file - Excel workbook, Word document, or PowerPoint deck (format = xlsx|docx|pptx). Pass the assemble_estimate result. Returns the file.",
    "publish_estimate": "Assembles the estimate and writes it + the Excel/Word/PPT exports to blob so the assessment dashboard web app shows it. Call after assembling; then point the user at the Container App /dashboard URL.",
    "azure_retail_prices": "Live Azure pay-as-you-go and reserved prices (cached proxy over prices.azure.com) - for ad-hoc price lookups outside the compute BoM.",
}

SYSTEM_PROMPT = """You help a migration architect estimate an Azure landing zone and a
server/application migration from client-supplied on-premises inventory.

- Use `query_inventory` for any count, sizing, or aggregation question and show the SQL you ran.
- For compute cost pull each server's vcpu, ram_gb, env, os_name and its utilisation
  columns (cpu_p95_pct / cpu_peak_pct / cpu_avg_pct, ram_avg_pct or the performance
  table's mem_*_pct, provisioned_disk_gb, disk_iops_peak) and pass them ALL to
  `estimate_compute_cost` - never size or cost servers yourself. Quote its totals, the
  low/expected/high range, region + reserved term + price_date, and any missing_prices.
  Use `vm_rightsize` alone when only the SKU mapping is wanted, `azure_retail_prices` for
  ad-hoc price lookups.
- For storage cost pass every dbo.storage row (type, size_gb, target_service) to
  `estimate_storage_cost`. It costs file shares, DB volumes and object storage; block
  volumes are already in `estimate_compute_cost`. Quote its by_type totals and the
  DB-storage caveat (DB compute/licensing is a separate replatform line).
- For a full run-rate call `estimate_run_rate_extras` with the servers
  (used_disk_gb, net_out_gb_30d, powerstate) and monthly_infra_cost = the compute +
  storage total. It adds backup, egress, monitoring, support and the one-time
  migration cost. Report run_rate_monthly.total_monthly and one_time.total separately.
- For the landing-zone design call `design_landing_zone` with the full applications
  list (criticality, internet_facing, compliance_scope) and a server_summary. Present
  its management groups, subscription list, spokes, IP plan, identity + connectivity
  model, policy overlay and DR strategy. Never hand-design the topology — quote the tool.
- For dispositions call `score_dispositions` (applications + a server_rollup of
  {servers, eol_servers} per app_id). For the migration plan call `plan_waves`
  (applications + servers + dependencies). Present the disposition mix and the wave
  table with the pilot wave, the regulated wave, and blocking dependencies. The 6R
  call and the wave order are the tool's — you explain them, you don't invent them.
- To produce the estimate, run the tools above then call `assemble_estimate` with an
  inventory_summary, the data_quality report, and each tool's JSON output. Present its
  `summary_markdown` and headline figures verbatim; cite figure ids for traceability.
  Do not restate numbers the package didn't produce.
- When the user wants a client-ready file, call `export_estimate` with the
  `assemble_estimate` result and `format` = xlsx (Excel workbook), docx (Word), or
  pptx (PowerPoint). Offer all three; each drops into the proposal with light edits.
- To make the estimate available as the interactive **assessment dashboard**, call
  `publish_estimate` with the `assemble_estimate` result, then give the user the
  chat-UI Container App URL with `/dashboard` (they download Excel/Word/PPT from there).
- Use `microsoft_docs` for Cloud Adoption Framework and target-service guidance.
- Use `search_documents` for client constraints (compliance, network, DR, non-functional).

Every estimate must end with these labelled lines:
Answer | Basis | Assumptions | Data gaps | Confidence (High/Medium/Low).

Never state a number without its basis. If inventory is missing a field the answer needs,
say so and give a ranged estimate. Output is a DRAFT for architect review, not a bid.
"""


def main() -> None:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")
    index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME", "landfall-docs")

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    tools: list = []

    # --- Microsoft Learn MCP (public, read-only, no approval prompt) ---
    tools.append(
        MCPTool(
            server_label="microsoft_docs",
            server_url="https://learn.microsoft.com/api/mcp",
            require_approval="never",
        )
    )

    # --- Azure AI Search over the narrative-docs index ---
    conn = _find_search_connection(project)
    if conn:
        tools.append(
            AzureAISearchTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[
                        AISearchIndexResource(
                            project_connection_id=conn,
                            index_name=index_name,
                            # vector + keyword hybrid; "vector_semantic_hybrid" needs the
                            # semantic ranker, which the Free AI Search tier does not offer
                            query_type="vector_simple_hybrid",
                        )
                    ]
                )
            )
        )
    else:
        print(
            "WARN: no Foundry connection found for the search service - add it in the "
            "portal (Management center > Connected resources) and re-run.",
            file=sys.stderr,
        )

    # --- OpenAPI tools over the deployed Function app ---
    tools += _openapi_tools()

    definition = PromptAgentDefinition(
        model=model, instructions=SYSTEM_PROMPT, tools=tools
    )
    version = project.agents.create_version(AGENT_NAME, definition=definition)

    # agents are addressed by name; print it for the hook / services
    print(f"AGENT_ID={version.get('name', AGENT_NAME)}")


def _openapi_tools() -> list:
    """One OpenApiTool per spec in src/api/openapi, with servers[0].url pointed at the
    deployed Function app. Anonymous auth by default; set AGENT_TOOL_AUTH=managed to make
    every tool call carry the Foundry managed-identity token (needed once the Function App
    has EasyAuth on — see DEPLOY.md 'Harden the Function App'). EasyAuth is app-global, so
    it's all tools or none, not query_inventory alone."""
    func_name = os.environ.get("SERVICE_API_NAME", "")
    if not func_name:
        print(
            "WARN: SERVICE_API_NAME not set - skipping the OpenAPI tools. Re-run this "
            "script after `azd deploy` to attach them.",
            file=sys.stderr,
        )
        return []

    host = f"{func_name}.azurewebsites.net"
    managed = os.environ.get("AGENT_TOOL_AUTH") == "managed"
    audience = os.environ.get("FUNC_AUTH_AUDIENCE", f"api://{func_name}")
    if managed:
        print(f"   OpenAPI tools: managed-identity auth (audience {audience})", file=sys.stderr)

    out = []
    for name, description in _OPENAPI_TOOLS.items():
        path = os.path.join(_OPENAPI_DIR, f"{name}.json")
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["servers"] = [{"url": f"https://{host}/api"}]

        if managed:
            auth = OpenApiManagedAuthDetails(
                security_scheme=OpenApiManagedSecurityScheme(audience=audience)
            )
        else:
            auth = OpenApiAnonymousAuthDetails()

        out.append(
            OpenApiTool(
                openapi=OpenApiFunctionDefinition(
                    name=name, description=description, spec=spec, auth=auth
                )
            )
        )
    return out


def _find_search_connection(project):
    """Return the connection name of the project's Azure AI Search connection, if any."""
    for c in project.connections.list():
        ctype = str(getattr(c, "type", "") or "").lower()
        if "search" in ctype or "search" in (getattr(c, "name", "") or "").lower():
            return c.name
    return None


if __name__ == "__main__":
    main()
