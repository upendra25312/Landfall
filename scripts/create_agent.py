"""
Create (or update) the Landfall "Migration Estimator" agent in the Foundry project
and print its id.  Called by the postprovision hook; can also be run by hand.

Reads from environment (azd populates these in .azure/<env>/.env):
  FOUNDRY_PROJECT_ENDPOINT
  AZURE_OPENAI_CHAT_DEPLOYMENT
  AZURE_SEARCH_ENDPOINT
  AZURE_SEARCH_INDEX_NAME

Writes AGENT_ID back to stdout as `AGENT_ID=<id>` (the hook captures it with `azd env set`).
"""
import os
import sys

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AzureAISearchTool, McpTool

AGENT_NAME = "landfall-migration-estimator"

SYSTEM_PROMPT = """You help a migration architect estimate an Azure landing zone and a
server/application migration from client-supplied on-premises inventory.

- Use `query_inventory` for any count, sizing, or aggregation question and show the SQL you ran.
- Use `vm_rightsize` then `azure_retail_prices` for compute cost, always naming region + term + price date.
- Use `microsoft_docs` for landing-zone, Cloud Adoption Framework, and target-service guidance.
- Use `search_documents` for client constraints (compliance, network, DR, non-functional).

Every estimate must end with these labelled lines:
Answer | Basis | Assumptions | Data gaps | Confidence (High/Medium/Low).

Never state a number without its basis. If inventory is missing a field the answer needs,
say so and give a ranged estimate. Output is a DRAFT for architect review, not a bid.
"""


def main() -> None:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
    search_endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
    index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME", "landfall-docs")

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    tools: list = []
    tool_resources: dict = {}

    # --- Microsoft Learn MCP (public, read-only) ---
    mcp = McpTool(
        server_label="microsoft_docs",
        server_url="https://learn.microsoft.com/api/mcp",
        allowed_tools=[],
    )
    mcp.set_approval_mode("never")
    tools += mcp.definitions

    # --- Azure AI Search over the narrative docs index ---
    if search_endpoint:
        conn = _find_search_connection(project, search_endpoint)
        if conn:
            ais = AzureAISearchTool(index_connection_id=conn, index_name=index_name)
            tools += ais.definitions
            tool_resources.update(ais.resources)
        else:
            print("WARN: no Foundry connection found for the search service - add it in the "
                  "portal (Management center > Connected resources) and re-run.", file=sys.stderr)

    # --- OpenAPI tools (query_inventory, vm_rightsize, azure_retail_prices) ---
    # These are registered against the deployed Function app. Attach them in the portal
    # or extend this script with OpenApiTool once the function OpenAPI specs are published
    # under src/api/openapi/. Left as a documented follow-up so first deploy succeeds.

    existing = next((a for a in project.agents.list_agents() if a.name == AGENT_NAME), None)
    if existing:
        agent = project.agents.update_agent(
            existing.id, model=model, instructions=SYSTEM_PROMPT,
            tools=tools, tool_resources=tool_resources or None,
        )
    else:
        agent = project.agents.create_agent(
            model=model, name=AGENT_NAME, instructions=SYSTEM_PROMPT,
            tools=tools, tool_resources=tool_resources or None,
        )

    print(f"AGENT_ID={agent.id}")


def _find_search_connection(project, search_endpoint):
    host = search_endpoint.replace("https://", "").rstrip("/")
    for c in project.connections.list():
        target = (getattr(c, "target", "") or "").replace("https://", "").rstrip("/")
        if host in target:
            return c.id
    return None


if __name__ == "__main__":
    main()
