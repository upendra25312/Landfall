"""
Landfall chat UI - a thin FastAPI front end over the Foundry Migration Estimator agent.

One page, one endpoint. The agent is a Microsoft Foundry prompt agent addressed by
name and driven through the Responses API; each browser tab carries the last
response id so the conversation keeps its memory. Authentication in front of this
app is handled by the Container App's built-in Entra ID (Easy Auth) - configure it
after first deploy.
"""
import os
import json
import pathlib
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

logging.basicConfig(level=logging.INFO)

PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
AGENT_NAME = os.environ.get("AGENT_ID", "")  # Foundry agents are addressed by name
STORAGE_URL = os.environ.get("STORAGE_URL", "")  # assessment dashboard reads answers/estimate/*

_cred = DefaultAzureCredential()
_clients: dict = {}


def _openai_client():
    """Lazy — keep import (and container start) free of network / token calls."""
    if "openai" not in _clients:
        proj = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=_cred)
        _clients["openai"] = proj.get_openai_client()
    return _clients["openai"]


app = FastAPI(title="Landfall")

_HERE = pathlib.Path(__file__).parent
_ESTIMATE = {"prefix": "estimate", "container": "answers"}
_EXPORT_MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_blob_state: dict = {}


def _estimate_container():
    if "cc" not in _blob_state:
        from azure.storage.blob import BlobServiceClient

        if not STORAGE_URL:
            raise RuntimeError("STORAGE_URL not set")
        svc = BlobServiceClient(STORAGE_URL, credential=_cred)
        _blob_state["cc"] = svc.get_container_client(_ESTIMATE["container"])
    return _blob_state["cc"]


def _estimate_prefixes(engagement: str | None) -> list[str]:
    """Where a published estimate might live. Prefer the engagement path; fall back to
    the default engagement, then the pre-E11 flat `estimate/` path."""
    out = []
    eid = (engagement or "").strip().strip("/")
    if eid and eid != "_default_/_default_":
        out.append(f"engagements/{eid}/estimate")
    out.append("engagements/_default_/_default_/estimate")
    out.append("estimate")  # legacy (cycles 1-17)
    return out


def _read_estimate_blob(name: str, engagement: str | None = None) -> bytes | None:
    for prefix in _estimate_prefixes(engagement):
        try:
            return _estimate_container().download_blob(f"{prefix}/{name}").readall()
        except Exception:  # noqa: BLE001 - missing blob -> try the next location
            continue
    return None


def _citations(resp) -> list:
    """Pull document/URL citation labels out of a Responses API result."""
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
    return sorted(seen)


@app.get("/healthz")
def health():
    return {"ok": True, "agent_configured": bool(AGENT_NAME),
            "storage_configured": bool(STORAGE_URL),
            "estimate_published": _read_estimate_blob("latest.json") is not None}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    question = (body.get("message") or "").strip()
    prev_id = body.get("thread_id")  # last response id, kept per browser tab
    if not question:
        return JSONResponse({"error": "empty message"}, status_code=400)
    if not AGENT_NAME:
        return JSONResponse({"error": "AGENT_ID not set - run the postprovision hook"}, status_code=503)

    try:
        kwargs = {
            "input": question,
            "extra_body": {
                "agent_reference": {"type": "agent_reference", "name": AGENT_NAME}
            },
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id
        resp = _openai_client().responses.create(**kwargs)
        text = (resp.output_text or "").strip()
        if not text:
            return JSONResponse(
                {"error": f"agent returned no text (status {resp.status})", "thread_id": resp.id},
                status_code=502,
            )
        return {"answer": text, "citations": _citations(resp), "thread_id": resp.id}
    except Exception as exc:  # noqa: BLE001
        logging.exception("chat failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """The assessment dashboard — an Azure Migrate–style read of the published estimate."""
    return (_HERE / "dashboard.html").read_text(encoding="utf-8")


@app.get("/dashboard/data")
def dashboard_data(e: str | None = None):
    blob = _read_estimate_blob("latest.json", e)
    if blob is None:
        return JSONResponse({"error": "no estimate published"}, status_code=404)
    return JSONResponse(json.loads(blob))


@app.get("/dashboard/download/{fmt}")
def dashboard_download(fmt: str, e: str | None = None):
    fmt = fmt.lower().lstrip(".")
    if fmt not in _EXPORT_MIME:
        return JSONResponse({"error": "format must be xlsx | docx | pptx"}, status_code=400)
    blob = _read_estimate_blob(f"latest.{fmt}", e)
    if blob is None:
        return JSONResponse({"error": f"no {fmt} export published"}, status_code=404)
    name = (e or "landfall-estimate").replace("/", "-")
    return Response(blob, media_type=_EXPORT_MIME[fmt], headers={
        "Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html><html><head><meta charset=utf-8>
<title>Landfall</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>
 body{font:15px/1.6 system-ui;margin:0;background:#0b151d;color:#e6edf1}
 header{padding:14px 20px;border-bottom:1px solid #25343f;font-weight:600}
 #log{max-width:820px;margin:0 auto;padding:20px}
 .m{margin:12px 0;padding:12px 14px;border-radius:8px;white-space:pre-wrap}
 .u{background:#152430}.a{background:#111f2a;border:1px solid #25343f}
 .c{font-size:12px;color:#94a5b0;margin-top:6px}
 form{position:sticky;bottom:0;background:#0b151d;max-width:820px;margin:0 auto;display:flex;gap:8px;padding:16px 20px}
 input{flex:1;padding:10px;border-radius:8px;border:1px solid #25343f;background:#111f2a;color:#e6edf1}
 button{padding:10px 18px;border-radius:8px;border:0;background:#0e7c8b;color:#fff;font-weight:600}
</style></head><body>
<header>Landfall &mdash; Migration Estimator
<a href="/dashboard" style="float:right;color:#7fd3dd;font-size:13px;text-decoration:none">Assessment dashboard &rarr;</a></header>
<div id=log></div>
<form id=f><input id=q placeholder="Ask about the client inventory, sizing, waves, cost..." autocomplete=off>
<button>Send</button></form>
<script>
let tid=null;const log=document.getElementById('log');
function add(t,cls,cites){const d=document.createElement('div');d.className='m '+cls;d.textContent=t;
 if(cites&&cites.length){const c=document.createElement('div');c.className='c';c.textContent='Sources: '+cites.join(', ');d.appendChild(c);}
 log.appendChild(d);window.scrollTo(0,document.body.scrollHeight);}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();
 const q=document.getElementById('q');const v=q.value.trim();if(!v)return;q.value='';add(v,'u');
 add('...','a');const ph=log.lastChild;
 try{const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},
   body:JSON.stringify({message:v,thread_id:tid})});const j=await r.json();
  ph.remove();if(j.error){add('Error: '+j.error,'a');}else{tid=j.thread_id;add(j.answer,'a',j.citations);}}
 catch(err){ph.remove();add('Error: '+err,'a');}};
</script></body></html>"""
