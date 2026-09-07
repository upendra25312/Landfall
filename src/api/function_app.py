"""
Project Sounding - RFP question-sheet batch runner (Azure Durable Functions, Python v2)

Flow:  blob lands in questions/*.xlsx
       -> starter copies it to _work/ and kicks off the orchestrator
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

app = func.FunctionApp()

_cred = DefaultAzureCredential()
_proj = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=_cred)
_blob = BlobServiceClient(os.environ["STORAGE_URL"], credential=_cred)

AGENT_ID = os.environ["AGENT_ID"]
MAX_ROWS = 300  # budget guard: reject oversized sheets

ANSWER_FORMAT = (
    "\n\nAnswer the question for an Azure migration RFP estimate. "
    "End your response with these labelled lines: "
    "Answer | Basis | Assumptions | Data gaps | Confidence (High/Medium/Low)."
)


# --------------------------------------------------------------------------
# starter: fires when a workbook is dropped in questions/
# --------------------------------------------------------------------------
@app.blob_trigger(arg_name="src", path="questions/{name}.xlsx", connection="STORAGE_CONN")
@app.durable_client_input(client_name="client")
async def start(src: func.InputStream, client):
    name = os.path.basename(src.name)
    _blob.get_blob_client("_work", name).upload_blob(src.read(), overwrite=True)
    instance_id = await client.start_new("orchestrator", client_input=name)
    logging.info("started orchestration %s for %s", instance_id, name)


# --------------------------------------------------------------------------
# orchestrator: fan-out / fan-in
# --------------------------------------------------------------------------
@app.orchestration_trigger(context_name="ctx")
def orchestrator(ctx: df.DurableOrchestrationContext):
    name = ctx.get_input()

    questions = yield ctx.call_activity("parse_sheet", name)
    if questions == "TOO_MANY_ROWS":
        logging.error("%s exceeded MAX_ROWS=%d - skipped", name, MAX_ROWS)
        return

    tasks = [ctx.call_activity("ask", q) for q in questions]
    rows = yield ctx.task_all(tasks)

    yield ctx.call_activity("write_results", {"name": name, "rows": rows})


# --------------------------------------------------------------------------
# activities
# --------------------------------------------------------------------------
@app.activity_trigger(input_name="name")
def parse_sheet(name: str):
    data = _blob.get_blob_client("_work", name).download_blob().readall()
    frame = pd.read_excel(io.BytesIO(data))
    if "Question" not in frame.columns:
        raise ValueError(f"{name}: no 'Question' column found")
    if len(frame) > MAX_ROWS:
        return "TOO_MANY_ROWS"
    return frame["Question"].fillna("").astype(str).tolist()


@app.activity_trigger(input_name="question")
def ask(question: str):
    """One question -> one grounded answer via the Foundry agent."""
    if not question.strip():
        return {"q": question, "answer": "", "cites": "", "status": "empty"}
    try:
        thread = _proj.agents.threads.create()
        _proj.agents.messages.create(
            thread.id, role="user", content=question + ANSWER_FORMAT
        )
        run = _proj.agents.runs.create_and_process(thread.id, agent_id=AGENT_ID)
        if run.status != "completed":
            return {"q": question, "answer": "", "cites": "", "status": f"run_{run.status}"}

        msg = _proj.agents.messages.get_last_message_by_role(thread.id, "assistant")
        text = "\n".join(t.text.value for t in msg.text_messages)
        cites = "; ".join(sorted({a.file_name for a in msg.file_citation_annotations}))
        return {"q": question, "answer": text, "cites": cites, "status": "ok"}
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
    _blob.get_blob_client("answers", out_name).upload_blob(buf, overwrite=True)
    logging.info("wrote answers/%s (%d rows)", out_name, len(out))
    # optional: send the workbook by email here via Microsoft Graph
