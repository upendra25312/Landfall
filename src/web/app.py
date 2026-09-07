"""
Landfall chat UI - a thin FastAPI front end over the Foundry Migration Estimator agent.

One page, one endpoint. The agent is a Microsoft Foundry prompt agent addressed by
name and driven through the Responses API; each browser tab carries the last
response id so the conversation keeps its memory. Authentication in front of this
app is handled by the Container App's built-in Entra ID (Easy Auth) - configure it
after first deploy.
"""
import os
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

logging.basicConfig(level=logging.INFO)

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = os.environ.get("AGENT_ID", "")  # Foundry agents are addressed by name

_cred = DefaultAzureCredential()
_project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=_cred)
_openai = _project.get_openai_client()

app = FastAPI(title="Landfall")


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
    return {"ok": True, "agent_configured": bool(AGENT_NAME)}


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
        resp = _openai.responses.create(**kwargs)
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
<header>Landfall &mdash; Migration Estimator</header>
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
