let busy=false,CARDS=[],ENG=localStorage.getItem('landfall.eng')||'';
const log=document.getElementById('log'),q=document.getElementById('q'),send=document.getElementById('send');
const engsel=document.getElementById('engsel'),engform=document.getElementById('engform');

function add(t,cls,cites,extra){
 const d=document.createElement('div');d.className='m '+cls;d.textContent=t;
 if(cites&&cites.length){const c=document.createElement('div');c.className='c';c.textContent='Sources: '+cites.join(', ');d.appendChild(c);}
 if(cls==='a'&&t&&(extra&&(extra.tables&&extra.tables.length))){
  const b=document.createElement('button');b.className='link';b.style.marginTop='6px';
  b.textContent='⭳ Download as Excel';
  b.onclick=()=>xlsxFromAnswer(extra.question||'',t,extra.tables||[],extra.sql||'');
  d.appendChild(b);
 }
 log.appendChild(d);d.scrollIntoView({block:'end'});return d;
}
async function xlsxFromAnswer(question,answer,tables,sql){
 try{
  const r=await fetch('/api/answer_to_xlsx',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({engagement:ENG,question:question,answer:answer,tables:tables,sql:sql})});
  if(!r.ok){toast('Excel export failed');return;}
  const blob=await r.blob(),u=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=u;a.download=(ENG||'landfall').replace('/','-')+'-answer.xlsx';a.click();
  setTimeout(()=>URL.revokeObjectURL(u),4000);
 }catch(e){toast('Excel export failed');}
}
function working(){
 const d=document.createElement('div');d.className='m a';
 d.innerHTML='<div class="working"><span class="spin"></span><span>The estimator is working<span class="dots"></span> <span class="el"></span></span></div>';
 log.appendChild(d);d.scrollIntoView({block:'end'});
 const t0=Date.now();const el=d.querySelector('.el');
 let stage='';
 d._timer=setInterval(async()=>{
  const elapsed=Math.round((Date.now()-t0)/1000);
  el.textContent='('+elapsed+'s)'+(stage?' · '+stage:'');
  if(ENG && elapsed%5===0){
   try{const [c,p]=ENG.split('/');
    const r=await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/progress');
    if(r.ok){const state=await r.json();
     if(state.updated_at && Date.parse(state.updated_at)>=t0-2000){
      stage=state.tool?state.tool.replace(/_/g,' '):(state.status==='queued'?'Waiting for the agent':'Preparing the answer');
     }
    }
   }catch(e){}
  }
 },1000);
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
 const engnote = ENG
  ? '<p class="sub eng">Active engagement: <b>'+esc(engLabel(ENG))+'</b> — every answer, upload and estimate is scoped to it. Add the client inventory in the panel above, then ask for the estimate.</p>'
  : '<p class="sub warn">No engagement selected. Pick one top-left, or click <b>+ New engagement</b> to start a customer / project — then upload their server &amp; application inventory.</p>';
 w.innerHTML='<div class=intro><h2>'+esc(i.title||'Landfall — Migration Estimator')+'</h2>'
  +engnote
  +'<p>'+esc(i.body||'').replace(/\n/g,'<br>')+'</p>'
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

async function loadEngagements(){
 let list=[];
 try{const r=await fetch('/api/engagements');list=(await r.json()).engagements||[];}catch(e){}
 window._engagements=list;
 engsel.innerHTML='';
 if(!list.length){
  const o=document.createElement('option');o.value='';o.textContent='— no engagements —';engsel.appendChild(o);
 }
 list.forEach(e=>{
  const o=document.createElement('option');o.value=e.engagement;
  o.textContent=(e.customer||e.engagement.split('/')[0])+' / '+(e.project||e.engagement.split('/')[1])
   +'  ·  '+(e.target_region||'?');
  engsel.appendChild(o);
 });
 if(ENG && list.some(e=>e.engagement===ENG)) engsel.value=ENG;
 else { ENG=engsel.value||''; localStorage.setItem('landfall.eng',ENG); }
 document.getElementById('expeng').hidden=!ENG;
 renderWelcome();showUpload();loadChat();syncDashLink();
}
function syncDashLink(){const a=document.getElementById('dashlink');
 const current=(window._engagements||[]).find(e=>e.engagement===ENG);
 document.getElementById('visibility').textContent=current?'Visibility: '+(current.visibility||'owner'):'';
 if(a)a.href=ENG?('/dashboard?e='+encodeURIComponent(ENG)):'/dashboard';}
engsel.onchange=()=>{ENG=engsel.value;localStorage.setItem('landfall.eng',ENG);HINTED=false;
 document.getElementById('expeng').hidden=!ENG;renderWelcome();showUpload();loadChat();syncDashLink();};

// --- per-engagement conversation (E11.26) ------------------------------
async function loadChat(){
 if(!ENG){return;}
 let doc={turns:[]};
 const [c,p]=ENG.split('/');
 try{doc=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/chat')).json();}catch(e){}
 const turns=doc.turns||[];
 log.innerHTML='<div id=welcome></div>';
 if(!turns.length){renderWelcome();return;}
 document.getElementById('welcome').remove();
 turns.forEach((t,i)=>add(t.text,t.role==='user'?'u':'a',t.citations,
   t.role==='assistant'?{tables:t.tables,sql:t.sql,question:(turns[i-1]||{}).text||''}:null));
}
document.getElementById('expeng').onclick=()=>{
 if(!ENG)return;const [c,p]=ENG.split('/');
 window.location='/api/engagements/'+enc(c)+'/'+enc(p)+'/export';
};
const impfile=document.getElementById('impfile');
document.getElementById('impeng').onclick=()=>impfile.click();
impfile.onchange=async()=>{
 const f=impfile.files[0];impfile.value='';if(!f)return;
 const fd=new FormData();fd.append('file',f);
 let r=await fetch('/api/engagements/import',{method:'POST',body:fd});
 let j=await r.json();
 if(r.status===409 && confirm(j.error+'\n\nReplace it?')){
  fd.append('overwrite','true');
  r=await fetch('/api/engagements/import',{method:'POST',body:fd});j=await r.json();
 }
 if(j.error){alert('Import failed: '+j.error);return;}
 toast('Imported '+j.engagement+' ('+j.imported+' files)');
 ENG=j.engagement;localStorage.setItem('landfall.eng',ENG);
 await loadEngagements();engsel.value=ENG;
};

// --- Upload panel (E11.6 / E11.24) ---------------------------------------
const upanel=document.getElementById('uploadpanel'),uz=document.getElementById('uz'),
      ufile=document.getElementById('ufile'),frows=document.getElementById('filerows'),
      toastEl=document.getElementById('toast');
const enc=encodeURIComponent;
function toast(m){toastEl.textContent=m;toastEl.classList.add('show');setTimeout(()=>toastEl.classList.remove('show'),3200);}
function ukind(){return (document.querySelector('input[name=ukind]:checked')||{}).value||'auto';}
function fmtSize(n){return n>=1048576?(n/1048576).toFixed(1)+' MB':n>=1024?Math.round(n/1024)+' KB':n+' B';}
function engLabel(eid){const o=[...engsel.options].find(o=>o.value===eid);return o?o.textContent.split('  ·  ')[0]:eid;}
function showUpload(){
 if(!ENG){upanel.hidden=true;pipeEl.hidden=true;return;}
 upanel.hidden=false;document.getElementById('upeng').textContent=engLabel(ENG);loadFiles();loadPipeline();
}

// --- Guided pipeline state (E13.2 / E12.8) ------------------------------
const pipeEl=document.getElementById('pipeline');
let PIPE=null,HINTED=false;
const PIPE_ACTION={uploads:'Upload the client inventory in the panel above.',
 analysis:'Click "Start analysis" once the inventory is uploaded.',
 estimate:'Ask for "the full estimate" to produce and publish it.',
 poe:'Ask for "the landing-zone cost (Calculator POE)".'};
async function loadPipeline(){
 if(!ENG){pipeEl.hidden=true;return;}
 const [c,p]=ENG.split('/');
 try{PIPE=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/pipeline')).json();}
 catch(e){pipeEl.hidden=true;return;}
 if(!PIPE||!PIPE.steps){pipeEl.hidden=true;return;}
 const nx=PIPE.next;
 pipeEl.innerHTML=PIPE.steps.map(s=>{
  const cls=s.done?'done':(s.key===nx?'next':'todo');
  const mk=s.done?'✓':(s.key===nx?'▸':'');
  return '<div class="step '+cls+'"><div class=hd><span class=mk>'+mk+'</span>'+esc(s.label)+'</div>'
   +'<div class=dt>'+esc(s.detail||'')+'</div></div>';
 }).join('')
 +(nx&&PIPE_ACTION[nx]?'<div class=hint>Next: '+esc(PIPE_ACTION[nx])+'</div>':'');
 pipeEl.hidden=false;
}
let ANALYSIS={};   // file name -> ingest report
const abar=document.getElementById('analysisbar'),anote=document.getElementById('analysisnote'),
      startBtn=document.getElementById('startanalysis'),dqEl=document.getElementById('dqsummary');
async function loadFiles(){
 frows.innerHTML='';dqEl.hidden=true;abar.hidden=true;if(!ENG)return;
 const [c,p]=ENG.split('/');
 let hasInv=false;
 try{
  const j=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files')).json();
  try{const a=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/analysis')).json();
      ANALYSIS={};(a.reports||[]).forEach(r=>ANALYSIS[r.file]=r);
      if((a.summary||{}).files_ingested)renderDQ(a.summary);}catch(e){}
  const n=(j.files||[]).length;
  (j.files||[]).forEach(f=>{if(f.kind==='inventory')hasInv=true;frows.appendChild(doneRow(f));});
  document.getElementById('upcount').textContent=n?(' · '+n+(n===1?' file':' files')):'';
  if(j.over_soft_cap)toast('This engagement is over the 2 GB soft cap.');
 }catch(e){}
 abar.hidden=!hasInv;
 if(!hasInv)upanel.open=true;        // fresh engagement — prompt the upload; returning users see it collapsed
}
function delFile(nm){
 return async()=>{if(!confirm('Remove '+nm+'?'))return;const [c,p]=ENG.split('/');
  await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files/'+enc(nm),{method:'DELETE'});loadFiles();};
}
function ingestBadge(f){
 if(f.kind!=='inventory')return '';
 const r=ANALYSIS[f.name];
 if(!r)return '<span class="badge wait">not analysed</span>';
 if(r.status&&r.status!=='ok'&&r.status!=='rejected')return '<span class="badge rej">'+esc(r.status)+'</span>';
 let b='<span class="badge ing">✓ '+(r.rows_loaded||0)+' rows'+(r.table?(' → '+esc(r.table)):'')+'</span>';
 if(r.rows_rejected)b+=' <span class="badge rej">'+r.rows_rejected+' rejected</span>';
 return b;
}
function doneRow(f){
 const li=document.createElement('li');li.className='frow ok';
 const prof=f.profile?(' · '+esc(f.profile)):'',rows=f.rows?(' · '+f.rows+' rows'):'';
 li.innerHTML='<span class=nm>'+esc(f.name)+'</span>'+ingestBadge(f)+
   '<span class=st>✓ '+esc(f.kind)+prof+rows+' · '+fmtSize(f.size)+'</span><button class=x title=Remove>✕</button>';
 li.querySelector('.x').onclick=delFile(f.name);return li;
}
function renderDQ(s){
 if(!s||!s.files_ingested){dqEl.hidden=true;return;}
 const tbl=Object.entries(s.tables||{}).map(([t,n])=>esc(t)+' ('+n+')').join(', ');
 let h='<h4>Data-quality summary</h4>';
 h+='<div>'+s.files_ingested+' file'+(s.files_ingested===1?'':'s')+' loaded · '+
    s.rows_loaded+' rows'+(tbl?(' · '+tbl):'')+
    (s.confidence?(' · confidence <span class="conf '+esc(s.confidence)+'">'+esc(s.confidence)+'</span>'):'')+'</div>';
 if((s.pending||[]).length)h+='<div class=warn>still ingesting: '+s.pending.map(esc).join(', ')+'</div>';
 if((s.findings||[]).length)h+='<ul>'+s.findings.map(f=>'<li>'+esc(f)+'</li>').join('')+'</ul>';
 dqEl.innerHTML=h;dqEl.hidden=false;
}
async function startAnalysis(){
 if(!ENG)return;const [c,p]=ENG.split('/');
 startBtn.disabled=true;anote.textContent='ingesting the uploaded files…';
 try{
  const j=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/analyze',{method:'POST'})).json();
  if(j.error){anote.textContent='✗ '+j.error;startBtn.disabled=false;return;}
  ANALYSIS={};(j.reports||[]).forEach(r=>ANALYSIS[r.file]=r);
  renderDQ(j.summary);await loadFiles();
  let tries=(j.summary&&j.summary.pending||[]).length?8:0;
  while(tries-- > 0){
   await new Promise(r=>setTimeout(r,2500));
   const a=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/analysis')).json();
   ANALYSIS={};(a.reports||[]).forEach(r=>ANALYSIS[r.file]=r);
   renderDQ(a.summary);await refreshRows();
   if(!((a.summary||{}).pending||[]).length)break;
  }
  anote.textContent='';
 }catch(e){anote.textContent='✗ '+e;}
 startBtn.disabled=false;
 loadPipeline();
}
async function refreshRows(){
 if(!ENG)return;const [c,p]=ENG.split('/');
 try{const j=await (await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/files')).json();
  frows.innerHTML='';(j.files||[]).forEach(f=>frows.appendChild(doneRow(f)));}catch(e){}
}
startBtn.onclick=startAnalysis;
function uploadOne(file){
 if(window._directUploads && file.size>=8*1024*1024){uploadDirect(file);return;}
 const li=document.createElement('li');li.className='frow';
 li.innerHTML='<span class=nm>'+esc(file.name)+'</span><span class=pbar><i></i></span><span class=st>uploading…</span>';
 frows.prepend(li);
 const bar=li.querySelector('.pbar i'),st=li.querySelector('.st'),[c,p]=ENG.split('/');
 const fd=new FormData();fd.append('kind',ukind());fd.append('file',file);
 const xhr=new XMLHttpRequest();
 xhr.open('POST','/api/engagements/'+enc(c)+'/'+enc(p)+'/upload');
 xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.round(e.loaded/e.total*100);bar.style.width=pct+'%';st.textContent=pct<100?('uploading '+pct+'%'):'checking…';}};
 xhr.onload=()=>{let j={};try{j=JSON.parse(xhr.responseText);}catch(e){}
  if(xhr.status===201){li.replaceWith(doneRow(j));toast(j.name+' added to '+engLabel(ENG));}
  else{li.className='frow err';
   li.innerHTML='<span class=nm>'+esc(file.name)+'</span><span class=st>✗ '+esc(j.error||('error '+xhr.status))+'</span><button class=x>✕</button>';
   li.querySelector('.x').onclick=()=>li.remove();}};
 xhr.onerror=()=>{li.className='frow err';st.textContent='✗ network error';};
 xhr.send(fd);
}
uz.onclick=()=>ufile.click();
ufile.onchange=()=>{[...ufile.files].forEach(uploadOne);ufile.value='';};
uz.ondragover=e=>{e.preventDefault();uz.classList.add('drag');};
uz.ondragleave=()=>uz.classList.remove('drag');
uz.ondrop=e=>{e.preventDefault();uz.classList.remove('drag');[...e.dataTransfer.files].forEach(uploadOne);};

async function loadRegions(){
 try{const r=await fetch('/api/calc_regions');const regs=(await r.json()).regions||[];
  const tr=document.getElementById('trsel'),dr=document.getElementById('drsel');
  regs.forEach(x=>{tr.appendChild(new Option(x,x));dr.appendChild(new Option(x,x));});
  tr.value='swedencentral';
 }catch(e){}
}

document.getElementById('neweng').onclick=()=>{engform.hidden=!engform.hidden;};
document.getElementById('engcancel').onclick=()=>{engform.hidden=true;};
document.getElementById('ef').onsubmit=async ev=>{
 ev.preventDefault();
 const fd=Object.fromEntries(new FormData(ev.target).entries());
 const btn=ev.target.querySelector('button[type=submit]');btn.disabled=true;btn.textContent='Creating…';
 try{
  const r=await fetch('/api/engagements',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(fd)});
  const j=await r.json();
  if(j.error){alert('Could not create: '+j.error);}
  else{ENG=j.engagement;localStorage.setItem('landfall.eng',ENG);engform.hidden=true;ev.target.reset();
       await loadEngagements();engsel.value=ENG;showUpload();newChat();
       toast('Engagement created — now upload the client inventory below.');}
 }catch(e){alert('Error: '+e);}
 btn.disabled=false;btn.textContent='Create engagement';
};

async function newChat(){
 if(busy)return;
 if(ENG){const [c,p]=ENG.split('/');
  try{await fetch('/api/engagements/'+enc(c)+'/'+enc(p)+'/chat/new',{method:'POST'});}catch(e){}}
 log.innerHTML='<div id=welcome></div>';renderWelcome();q.value='';q.focus();
}
document.getElementById('newchat').onclick=newChat;

async function ask(v){
 v=(v||'').trim();if(!v||busy)return;
 if(!ENG){
  add('Pick an engagement first (top-left) — or click "+ New engagement" to create one. '
     +'Every question is scoped to a customer / project so the estimate stays that client\'s.','a');
  engform.hidden=false;return;
 }
 const w=document.getElementById('welcome');if(w)w.remove();
 q.value='';add(v,'u');
 // E13.2 — a one-time, non-blocking nudge if nothing's been analysed yet
 if(PIPE && PIPE.analysed===false && !HINTED){
  HINTED=true;
  add('Heads up — no inventory has been analysed for this engagement yet, so I have no '
     +'server data to work from. Upload the client\'s inventory and click "Start analysis" '
     +'for a grounded estimate. I\'ll still answer general questions.','a');
 }
 setBusy(true);
 const ph=working();
 try{
  const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({message:v,engagement:ENG})});
  const j=await r.json();
  clearInterval(ph._timer);ph.remove();
  if(j.error){add('Error: '+j.error,'a');}
  else{add(j.answer,'a',j.citations,{tables:j.tables,sql:j.sql,question:v});}
 }catch(err){clearInterval(ph._timer);ph.remove();add('Error: '+err,'a');}
 setBusy(false);
 loadPipeline();
}
document.getElementById('f').onsubmit=e=>{e.preventDefault();ask(q.value);};
loadCards();loadEngagements();loadRegions();q.focus();
fetch('/api/me').then(r=>r.json()).then(me=>{
 window._directUploads=me.direct_uploads;
 document.getElementById('identity').textContent=me.signed_in?'Signed in as '+me.name:'Local preview';
 document.getElementById('signout').hidden=!me.signed_in;
}).catch(()=>{document.getElementById('identity').textContent='Identity unavailable';});

async function uploadDirect(file){
 const [c,p]=ENG.split('/'),base='/api/engagements/'+enc(c)+'/'+enc(p);
 const kind=ukind();
 toast('Uploading '+file.name+' directly to secure storage…');
 try{
  const response=await fetch(base+'/upload-ticket',{method:'POST',headers:{'content-type':'application/json'},
   body:JSON.stringify({name:file.name,size:file.size,kind})});
  if(!response.ok)throw new Error('Could not start upload');
  const ticket=await response.json();
  const put=await fetch(ticket.url,{method:'PUT',headers:{'x-ms-blob-type':'BlockBlob'},body:file});
  if(!put.ok)throw new Error('Storage upload failed');
  const complete=await fetch(base+'/upload-complete',{method:'POST',headers:{'content-type':'application/json'},
   body:JSON.stringify({ticket:ticket.ticket})});
  if(!complete.ok)throw new Error('Upload validation failed');
  const done=await complete.json();toast(done.name+' uploaded and checked');await loadFiles();
 }catch(error){toast(error.message+' — please try again');}
}
