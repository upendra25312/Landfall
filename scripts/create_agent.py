"""
Create (or version) the Landfall "Migration Estimator" agent in the Foundry project
and print its name.  Called by the postprovision hook; can also be run by hand.

This targets the current Microsoft Foundry Agents surface (prompt agents, Responses
API, versioned).  The agent is referenced everywhere by NAME, not an `asst_` id.

Reads from environment (azd populates these in .azure/<env>/.env):
  FOUNDRY_PROJECT_ENDPOINT
  AZURE_OPENAI_CHAT_DEPLOYMENT
  AZURE_SEARCH_INDEX_NAME

Writes AGENT_ID back to stdout as `AGENT_ID=<name>` (the hook captures it with `azd env set`).
"""
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
)

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
                            query_type="vector_semantic_hybrid",
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

    # --- OpenAPI tools (query_inventory, vm_rightsize, azure_retail_prices) ---
    # Attach in the portal once the Function OpenAPI specs are published, or extend
    # this with OpenApiTool. Left as a documented follow-up so first deploy succeeds.

    definition = PromptAgentDefinition(
        model=model, instructions=SYSTEM_PROMPT, tools=tools
    )
    version = project.agents.create_version(AGENT_NAME, definition=definition)

    # agents are addressed by name; print it for the hook / services
    print(f"AGENT_ID={version.get('name', AGENT_NAME)}")


def _find_search_connection(project):
    """Return the connection name of the project's Azure AI Search connection, if any."""
    for c in project.connections.list():
        ctype = str(getattr(c, "type", "") or "").lower()
        if "search" in ctype or "search" in (getattr(c, "name", "") or "").lower():
            return c.name
    return None


if __name__ == "__main__":
    main()
