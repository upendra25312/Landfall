"""
Landfall chat UI - a thin FastAPI front end over the Foundry Migration Estimator agent.

One page, one endpoint. Each browser tab keeps its own agent thread id so the
conversation has memory. Authentication in front of this app is handled by the
Container App's built-in Entra ID (Easy Auth) - configure it after first deploy.
"""
import os
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

logging.basicConfig(level=logging.INFO)

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_ID = os.environ.get("AGENT_ID", "")

_cred = DefaultAzureCredential()
_project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=_cred)

app = FastAPI(title="Landfall")


@app.get("/healthz")
def health():
    return {"ok": True, "agent_configured": bool(AGENT_ID)}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    question = (body.get("message") or "").strip()
    thread_id = body.get("thread_id")
    if not question:
        return JSONResponse({"error": "empty message"}, status_code=400)
    if not AGENT_ID:
        return JSONResponse({"error": "AGENT_ID not set - run the postprovision hook"}, status_code=503)

    try:
        if not thread_id:
            thread_id = _project.agents.threads.create().id
        _project.agents.messages.create(thread_id, role="user", content=question)
        run = _project.agents.runs.create_and_process(thread_id, agent_id=AGENT_ID)
        if run.status != "completed":
            return JSONResponse({"error": f"run {run.status}", "thread_id": thread_id}, status_code=502)
        msg = _project.agents.messages.get_last_message_by_role(thread_id, "assistant")
        text = "\n".join(t.text.value for t in msg.text_messages)
        cites = sorted({a.file_name for a in msg.file_citation_annotations})
        return {"answer": text, "citations": cites, "thread_id": thread_id}
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
