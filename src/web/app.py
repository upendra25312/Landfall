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


@app.get("/api/prompt_cards")
def prompt_cards():
    """Intro + capability list + the clickable prompt cards for the chat UI (E11.7).
    Config so pre-sales can edit `src/web/prompt_cards.json` without a code change."""
    try:
        return JSONResponse(json.loads((_HERE / "prompt_cards.json").read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        logging.warning("prompt_cards.json unreadable: %s", exc)
        return JSONResponse({"intro": {"title": "Landfall — Migration Estimator",
                                       "body": "Ask about the client inventory, sizing, waves or cost.",
                                       "capabilities": []}, "cards": []})


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
 :root{--bg:#0b151d;--panel:#111f2a;--line:#25343f;--ink:#e6edf1;--muted:#94a5b0;--accent:#0e7c8b}
 *{box-sizing:border-box}
 body{font:15px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
 header{display:flex;align-items:center;gap:12px;padding:12px 20px;border-bottom:1px solid var(--line);font-weight:600;position:sticky;top:0;background:var(--bg);z-index:5}
 header .sp{flex:1}
 header a,header button.link{color:#7fd3dd;font-size:13px;text-decoration:none;background:none;border:0;cursor:pointer;font-family:inherit}
 header button.link:hover,header a:hover{text-decoration:underline}
 #log{max-width:820px;margin:0 auto;padding:20px 20px 8px}
 .m{margin:12px 0;padding:12px 14px;border-radius:10px;white-space:pre-wrap;word-wrap:break-word}
 .u{background:#152430}
 .a{background:var(--panel);border:1px solid var(--line)}
 .c{font-size:12px;color:var(--muted);margin-top:6px}
 .empty{max-width:820px;margin:60px auto;text-align:center;color:var(--muted)}
 .working{display:flex;align-items:center;gap:10px;color:var(--muted)}
 .spin{width:15px;height:15px;border:2px solid var(--line);border-top-color:#7fd3dd;border-radius:50%;animation:sp .8s linear infinite;flex:none}
 @keyframes sp{to{transform:rotate(360deg)}}
 .dots::after{content:'';animation:dots 1.4s steps(4,end) infinite}
 @keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
 form{position:sticky;bottom:0;background:var(--bg);max-width:820px;margin:0 auto;display:flex;gap:8px;padding:14px 20px 18px;border-top:1px solid var(--line)}
 input{flex:1;padding:11px 12px;border-radius:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font:inherit}
 input:disabled{opacity:.55}
 button.send{padding:11px 20px;border-radius:8px;border:0;background:var(--accent);color:#fff;font-weight:600;cursor:pointer}
 button.send:disabled{opacity:.5;cursor:default}
 .intro{max-width:820px;margin:26px auto 6px;padding:0 20px}
 .intro h2{margin:0 0 8px;font-size:19px}
 .intro p{color:var(--muted);margin:0 0 14px}
 .caps{list-style:none;margin:0 0 18px;padding:0;display:grid;gap:6px}
 .caps li{color:var(--ink);font-size:13.5px;padding-left:18px;position:relative}
 .caps li::before{content:'▹';position:absolute;left:0;color:#7fd3dd}
 .cardgrid{max-width:820px;margin:0 auto 4px;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
 .pc{display:flex;align-items:center;gap:9px;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--ink);font:inherit;font-size:13px;text-align:left;cursor:pointer}
 .pc:hover{border-color:#7fd3dd}
 .pc .ic{width:20px;height:20px;border-radius:6px;background:#152430;display:flex;align-items:center;justify-content:center;color:#7fd3dd;flex:none}
 .pc:disabled{opacity:.5;cursor:default}
</style></head><body>
<header>
 <span>Landfall &mdash; Migration Estimator</span>
 <span class=sp></span>
 <button class=link id=newchat title="Clear this conversation and start fresh">+ New chat</button>
 <a href="/dashboard">Assessment dashboard &rarr;</a>
</header>
<div id=log><div id=welcome></div></div>
<form id=f>
 <input id=q placeholder="Ask about the client inventory, sizing, waves, cost..." autocomplete=off>
 <button class=send id=send>Send</button>
</form>
<script>
let tid=null,busy=false,CARDS=[];
const log=document.getElementById('log'),q=document.getElementById('q'),send=document.getElementById('send');

function add(t,cls,cites){
 const d=document.createElement('div');d.className='m '+cls;d.textContent=t;
 if(cites&&cites.length){const c=document.createElement('div');c.className='c';c.textContent='Sources: '+cites.join(', ');d.appendChild(c);}
 log.appendChild(d);d.scrollIntoView({block:'end'});return d;
}
function working(){
 const d=document.createElement('div');d.className='m a';
 d.innerHTML='<div class="working"><span class="spin"></span><span>The estimator is working<span class="dots"></span> <span class="el"></span></span></div>';
 log.appendChild(d);d.scrollIntoView({block:'end'});
 const t0=Date.now();const el=d.querySelector('.el');
 d._timer=setInterval(()=>{el.textContent='('+Math.round((Date.now()-t0)/1000)+'s)';},1000);
 return d;
}
function setBusy(b){busy=b;q.disabled=b;send.disabled=b;send.textContent=b?'Working…':'Send';
 document.querySelectorAll('.pc').forEach(x=>x.disabled=b);if(!b)q.focus();}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

function renderWelcome(){
 const w=document.getElementById('welcome');if(!w)return;
 const i=window._intro||{};
 const caps=(i.capabilities||[]).map(c=>'<li>'+esc(c)+'</li>').join('');
 const cards=CARDS.map((c,ix)=>'<button class=pc data-i="'+ix+'"><span class=ic>'+esc(c.icon||'▸')+'</span><span>'+esc(c.label)+'</span></button>').join('');
 w.innerHTML='<div class=intro><h2>'+esc(i.title||'Landfall — Migration Estimator')+'</h2>'
  +'<p>'+esc(i.body||'').replace(/\\n/g,'<br>')+'</p>'
  +(caps?'<ul class=caps>'+caps+'</ul>':'')+'</div>'
  +(cards?'<div class=cardgrid>'+cards+'</div>':'');
 w.querySelectorAll('.pc').forEach(b=>b.onclick=()=>{if(busy)return;ask(CARDS[+b.dataset.i].prompt);});
}

async function loadCards(){
 try{const r=await fetch('/api/prompt_cards');const j=await r.json();
  window._intro=j.intro||{};CARDS=j.cards||[];}
 catch(e){window._intro={};CARDS=[];}
 renderWelcome();
}

function newChat(){
 if(busy)return;tid=null;log.innerHTML='<div id=welcome></div>';renderWelcome();q.value='';q.focus();
}
document.getElementById('newchat').onclick=newChat;

async function ask(v){
 v=(v||'').trim();if(!v||busy)return;
 const w=document.getElementById('welcome');if(w)w.remove();
 q.value='';add(v,'u');
 setBusy(true);
 const ph=working();
 try{
  const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({message:v,thread_id:tid})});
  const j=await r.json();
  clearInterval(ph._timer);ph.remove();
  if(j.error){add('Error: '+j.error,'a');}
  else{tid=j.thread_id;add(j.answer,'a',j.citations);}
 }catch(err){clearInterval(ph._timer);ph.remove();add('Error: '+err,'a');}
 setBusy(false);
}
document.getElementById('f').onsubmit=e=>{e.preventDefault();ask(q.value);};
loadCards();q.focus();
</script></body></html>"""
