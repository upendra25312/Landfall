"""
Project Sounding - RFP question-sheet batch runner (Azure Durable Functions, Python v2)

Flow:  blob lands in questions/*.xlsx
       -> starter copies it to work/ and kicks off the orchestrator
       -> orchestrator parses the sheet, fans out one `ask` activity per question
          (throttled by host.json maxConcurrentActivityFunctions), fans back in
       -> write_results builds answers/<name>_answered.xlsx

host.json:
{
  "version": "2.0",
  "extensions": {
    "durableTask": {
      "maxConcurrentActivityFunctions": 3,
      "maxConcurrentOrchestratorFunctions": 1
    }
  }
}

requirements.txt:
  azure-functions
  azure-functions-durable
  azure-identity
  azure-ai-projects
  azure-storage-blob
  pandas
  openpyxl

App settings needed:
  FOUNDRY_PROJECT_ENDPOINT   e.g. https://<proj>.services.ai.azure.com/api/projects/<name>
  AGENT_ID                   the Migration Estimator agent id
  STORAGE_URL                https://<account>.blob.core.windows.net
  STORAGE_CONN               connection string / identity-based config for the blob trigger
The Function app's managed identity needs: Storage Blob Data Contributor on the account,
and Azure AI Developer on the Foundry project.
"""

import io
import os
import logging

import pandas as pd
import azure.functions as func
import azure.durable_functions as df
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.storage.blob import BlobServiceClient

from tools import bp  # query_inventory / azure_retail_prices HTTP tools
from cost.functions import cost_bp  # vm_rightsize (deterministic cost engine)
from ingest.functions import ingest_bp  # raw/inventory/* -> normalize -> Azure SQL + DQ report

app = df.DFApp()
app.register_functions(bp)
app.register_functions(cost_bp)
app.register_functions(ingest_bp)

# Lazily built on first use - keep module import (and worker function indexing) fast
# and free of network/token calls.
_cred = DefaultAzureCredential()
_clients: dict = {}


def _blob_client() -> BlobServiceClient:
    if "blob" not in _clients:
        _clients["blob"] = BlobServiceClient(os.environ["STORAGE_URL"], credential=_cred)
    return _clients["blob"]


def _openai_client():
    if "openai" not in _clients:
        proj = AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=_cred
        )
        _clients["openai"] = proj.get_openai_client()
    return _clients["openai"]


AGENT_NAME = os.environ.get("AGENT_ID", "")  # Foundry prompt agent, addressed by name
MAX_ROWS = 300  # budget guard: reject oversized sheets

ANSWER_FORMAT = (
    "\n\nAnswer the question for an Azure migration RFP estimate. "
    "End your response with these labelled lines: "
    "Answer | Basis | Assumptions | Data gaps | Confidence (High/Medium/Low)."
)


# --------------------------------------------------------------------------
# starter: fires when a workbook is dropped in questions/
# --------------------------------------------------------------------------
@app.blob_trigger(
    arg_name="src",
    path="questions/{name}.xlsx",
    connection="STORAGE_CONN",
    source=func.BlobSource.EVENT_GRID,  # required on the Flex Consumption plan
)
@app.durable_client_input(client_name="client")
async def start(src: func.InputStream, client):
    name = os.path.basename(src.name)
    _blob_client().get_blob_client("work", name).upload_blob(src.read(), overwrite=True)
    instance_id = await client.start_new("orchestrator", client_input=name)
    logging.info("started orchestration %s for %s", instance_id, name)


# --------------------------------------------------------------------------
# orchestrator: fan-out / fan-in
# --------------------------------------------------------------------------
@app.orchestration_trigger(context_name="context")
def orchestrator(context: df.DurableOrchestrationContext):
    name = context.get_input()

    questions = yield context.call_activity("parse_sheet", name)
    if questions == "TOO_MANY_ROWS":
        logging.error("%s exceeded MAX_ROWS=%d - skipped", name, MAX_ROWS)
        return

    tasks = [context.call_activity("ask", q) for q in questions]
    rows = yield context.task_all(tasks)

    yield context.call_activity("write_results", {"name": name, "rows": rows})


# --------------------------------------------------------------------------
# activities
# --------------------------------------------------------------------------
@app.activity_trigger(input_name="name")
def parse_sheet(name: str):
    data = _blob_client().get_blob_client("work", name).download_blob().readall()
    frame = pd.read_excel(io.BytesIO(data))
    if "Question" not in frame.columns:
        raise ValueError(f"{name}: no 'Question' column found")
    if len(frame) > MAX_ROWS:
        return "TOO_MANY_ROWS"
    return frame["Question"].fillna("").astype(str).tolist()


def _citations(resp) -> str:
    seen = []
    for item in getattr(resp, "output", None) or []:
        for content in getattr(item, "content", None) or []:
            for ann in getattr(content, "annotations", None) or []:
                label = (
                    getattr(ann, "filename", None)
                    or getattr(ann, "title", None)
                    or getattr(ann, "url", None)
                )
                if label and label not in seen:
                    seen.append(label)
    return "; ".join(sorted(seen))


@app.activity_trigger(input_name="question")
def ask(question: str):
    """One question -> one grounded answer via the Foundry agent (Responses API)."""
    if not question.strip():
        return {"q": question, "answer": "", "cites": "", "status": "empty"}
    try:
        resp = _openai_client().responses.create(
            input=question + ANSWER_FORMAT,
            extra_body={
                "agent_reference": {"type": "agent_reference", "name": AGENT_NAME}
            },
        )
        text = (resp.output_text or "").strip()
        if not text:
            return {"q": question, "answer": "", "cites": "", "status": f"run_{resp.status}"}
        return {"q": question, "answer": text, "cites": _citations(resp), "status": "ok"}
    except Exception as exc:  # noqa: BLE001 - want every row to complete
        logging.exception("ask failed for: %s", question)
        return {"q": question, "answer": "", "cites": "", "status": f"error: {exc}"}


@app.activity_trigger(input_name="payload")
def write_results(payload: dict):
    rows = payload["rows"]
    out = pd.DataFrame(
        [
            {
                "Question": r["q"],
                "Answer": r.get("answer", ""),
                "Sources": r.get("cites", ""),
                "Status": r["status"],
            }
            for r in rows
        ]
    )
    buf = io.BytesIO()
    out.to_excel(buf, index=False)
    buf.seek(0)

    out_name = payload["name"].replace(".xlsx", "_answered.xlsx")
    _blob_client().get_blob_client("answers", out_name).upload_blob(buf, overwrite=True)
    logging.info("wrote answers/%s (%d rows)", out_name, len(out))
    # optional: send the workbook by email here via Microsoft Graph
