
const $ = (s,el=document)=>el.querySelector(s);
// engagement + published-version awareness (E11.8)
const QS = new URLSearchParams(location.search);
const ENG = (QS.get("e")||"").trim();
let SNAP = (QS.get("snapshot")||"").trim();
function withScope(url, opts){
  const u = new URL(url, location.origin);
  if(ENG) u.searchParams.set("e", ENG);
  if(SNAP && (opts||{}).snap!==false) u.searchParams.set("snapshot", SNAP);
  return u.pathname + u.search;
}
const fmt = n => n==null ? "—" : (Math.abs(n)>=100 ? Math.round(n).toLocaleString()
                : n.toLocaleString(undefined,{maximumFractionDigits:2}));
const money = (n,cur) => n==null ? "—" : (cur? cur+" " : "$") + fmt(n);
const el = (tag,cls,html)=>{const e=document.createElement(tag); if(cls)e.className=cls;
  if(html!=null)safeSetHTML(e,html); return e;};

function figMap(pkg){const m={}; (pkg.figures||[]).forEach(f=>m[f.key]=f); return m;}
function sectionBody(pkg,key){const s=(pkg.sections||[]).find(x=>x.key===key); return s? s.body||{} : {};}
function ref(f){return f? `<span class="ref">${f.id}</span>` : "";}

function tile(label,value,r){
  const t=el("div","tile");
  t.append(el("div","k",label), el("div","v",value));
  if(r) t.append(el("div","r",r));
  return t;
}

function donut(parts){ // parts: [{label,value,color}]
  const total=parts.reduce((a,p)=>a+p.value,0)||1; let acc=0; const R=52,C=2*Math.PI*R;
  const segs=parts.map(p=>{const len=p.value/total*C; const s=`<circle r="${R}" cx="70" cy="70" fill="none"
     stroke="${p.color}" stroke-width="20" stroke-dasharray="${len} ${C-len}"
     stroke-dashoffset="${-acc}" transform="rotate(-90 70 70)"/>`; acc+=len; return s;}).join("");
  return `<svg viewBox="0 0 140 140" width="140" height="140" role="img">${segs}</svg>`;
}

function render(pkg){
  const root=$("#root"); root.innerHTML="";
  const meta=pkg.meta||{}, F=figMap(pkg);
  $("#statusBadge").textContent = meta.status||"Draft";
  $("#confPill").textContent = "confidence " + (meta.overall_confidence||"—");

  root.append(el("h1",null,`Migration estimate — ${meta.package_id||""}`));
  root.append(el("p","sub",
    `Region ${meta.region||"n/a"} · ${meta.currency||"USD"} · prices ${meta.price_date||"n/a"}`
    + (meta.generated_on? ` · generated ${meta.generated_on}`:"")
    + (meta.tools_failed&&meta.tools_failed.length? ` · ⚠ tools failed: ${meta.tools_failed.join(", ")}`:"")));

  // headline tiles
  const cs=sectionBody(pkg,"current_state");
  const tiles=el("div","tiles");
  tiles.append(
    tile("Servers", fmt(cs.servers), F.servers_total?F.servers_total.id:""),
    tile("Applications", fmt(cs.applications), F.apps_total?F.apps_total.id:""),
    tile("Azure run-rate / mo", money(F.run_rate_monthly?.value, meta.currency),
         F.run_rate_monthly? F.run_rate_monthly.id+" · "+F.run_rate_monthly.confidence : ""),
    tile("Run-rate / year", money(F.run_rate_annual?.value, meta.currency), F.run_rate_annual?.id||""),
    tile("One-time migration", money(F.one_time_cost?.value, meta.currency), F.one_time_cost?.id||""),
    tile("Migration effort", (F.effort_pd? fmt(F.effort_pd.value)+" PD":"—"), F.effort_pd?.id||""),
    tile("Services cost", money(F.services_cost?.value, meta.currency), F.services_cost?.id||""),
  );
  root.append(tiles);

  const grid=el("div","grid"); root.append(grid);

  // --- inventory & readiness
  grid.append(card("Inventory & readiness","F1", `
    <div class="kv">
      <b>Servers</b><span>${fmt(cs.servers)} (${cs.servers_powered_on??"?"} powered on)</span>
      <b>Applications</b><span>${fmt(cs.applications)}</span>
      <b>Compute</b><span>${fmt(cs.total_vcpu)} vCPU · ${fmt(cs.total_ram_gb)} GB RAM</span>
      <b>Storage</b><span>${fmt(cs.provisioned_disk_tb)} TB provisioned · ${fmt(cs.used_disk_tb)} TB used</span>
      <b>OS past end-of-support</b><span>${fmt(cs.eol_servers)} servers</span>
      <b>No performance history</b><span>${fmt(cs.no_perf_data_servers)} servers</span>
      <b>Data-quality confidence</b><span>${cs.data_quality_confidence||"n/a"}</span>
    </div>
    ${barsFromObj(cs.by_env,"By environment")}`));

  // --- run-rate cost
  const rc=sectionBody(pkg,"run_rate_cost"), drivers=rc.top_cost_drivers||[];
  const dcolors=["var(--c1)","var(--c2)","var(--c3)","var(--c4)","var(--c5)"];
  const shown=drivers.reduce((a,d)=>a+d.share_pct,0);
  const dslices=drivers.map((d,i)=>({label:d.driver,value:d.monthly,color:dcolors[i%5]}));
  if(shown<99 && rc.monthly) dslices.push({label:"Other",value:rc.monthly*(100-shown)/100,color:"var(--c5)"});
  grid.append(card("Azure run-rate cost","F8", `
    <div data-layout="display:flex;gap:18px;align-items:center;flex-wrap:wrap">
      <div>${donut(dslices)}</div>
      <div data-layout="flex:1;min-width:180px">
        <div data-layout="font-size:20px;font-weight:650">${money(rc.monthly,meta.currency)} <span data-layout="font-size:12px;color:var(--muted)">/ month</span></div>
        <div data-layout="color:var(--muted);font-size:13px">~${money(rc.annual,meta.currency)} / year · ${rc.reserved_term||"?"} reserved</div>
        ${rc.one_time? `<div data-layout="color:var(--muted);font-size:13px">one-time ~${money(rc.one_time,meta.currency)}</div>`:""}
      </div>
    </div>
    <table data-layout="margin-top:12px"><thead><tr><th>Cost driver</th><th class="num">Share</th></tr></thead><tbody>
      ${drivers.map((d,i)=>`<tr><td><i class="legend" data-layout="background:${dcolors[i%5]};width:9px;height:9px;display:inline-block;border-radius:2px;margin-right:6px"></i>${d.driver}</td><td class="num">${d.share_pct}%</td></tr>`).join("")}
    </tbody></table>`));

  // --- landing zone
  const lz=sectionBody(pkg,"landing_zone");
  const dc=lz.design_conformance||null;
  const dcBlock = dc ? `
    <div class="conf" data-layout="margin-top:10px;border-top:1px solid var(--line);padding-top:8px">
      <b data-layout="font-size:12px">Design conformance</b>
      <span class="pill" title="Scored against the Azure (AI) Landing Zone design checklist">${dc.headline||""}</span>
      ${dc.ai_lz_applicable? `<span class="pill">AI-LZ overlay</span>`:``}
      ${(dc.gaps&&dc.gaps.length)? `<details data-layout="margin-top:6px"><summary data-layout="cursor:pointer;color:var(--muted);font-size:12px">${dc.gaps.length} gap${dc.gaps.length>1?"s":""} to close</summary>
        <ul data-layout="margin:6px 0 0;padding-left:18px;font-size:12px;color:var(--muted)">
        ${dc.gaps.map(g=>`<li><b>${g.id}</b> ${g.item} — ${g.recommendation}</li>`).join("")}</ul></details>`:``}
    </div>` : ``;
  grid.append(card("Landing zone","F13", lz.note? `<p class="sub">${lz.note}</p>` : `
    <p data-layout="margin:0 0 8px">${lz.summary||""}</p>
    <div class="kv">
      <b>Region</b><span>${lz.region||"?"} → DR ${lz.dr_region||"?"}</span>
      <b>Identity</b><span>${lz.identity||"?"}</span>
      <b>Connectivity</b><span>${lz.connectivity||"?"}</span>
      <b>Regulated scopes</b><span>${(lz.regulated_scopes&&lz.regulated_scopes.length)? lz.regulated_scopes.join(", ") : "none"}</span>
    </div>
    <div class="chips">${(lz.spokes||[]).map(s=>`<span class="chip">${s.name} ${s.address_space||""}</span>`).join("")}</div>
    <p data-layout="color:var(--muted);font-size:12px;margin-top:10px">${lz.dr||""}</p>
    <div id="lzdiagram" data-layout="margin-top:10px"></div>${dcBlock}`));
  renderLZDiagram();

  // --- Azure Pricing Calculator POE (populated async from /dashboard/landing-zone)
  const poe=card("Azure landing zone — Pricing Calculator POE",null,
    `<p class="sub" id="poeBody">Checking for a Pricing Calculator estimate…</p>`);
  poe.id="poeCard"; grid.append(poe);

  // --- disposition
  const dp=sectionBody(pkg,"disposition"), bd=dp.by_disposition||{};
  const dispColors={Rehost:"var(--c1)",Replatform:"var(--c3)",Repurchase:"var(--c4)",Retire:"var(--c5)",Retain:"var(--c2)",Refactor:"var(--bad)"};
  const dtot=Object.values(bd).reduce((a,b)=>a+b,0)||1;
  grid.append(card("Application disposition (6R)",null, dp.note? `<p class="sub">${dp.note}</p>` : `
    <div class="bar" data-layout="height:20px;display:flex">
      ${Object.entries(bd).map(([k,v])=>`<i data-layout="width:${v/dtot*100}%;background:${dispColors[k]||"var(--c5)"};border-radius:0" title="${k}: ${v}"></i>`).join("")}
    </div>
    <div class="legend">${Object.entries(bd).map(([k,v])=>`<span><i data-layout="background:${dispColors[k]||"var(--c5)"}"></i>${k} ${v}</span>`).join("")}</div>
    ${(dp.needs_human_decision&&dp.needs_human_decision.length)? `<p data-layout="font-size:12px;color:var(--warn);margin-top:10px">Needs a business decision: ${dp.needs_human_decision.join(", ")}</p>`:""}`));

  // --- waves
  const wv=sectionBody(pkg,"waves");
  const sch=wv.schedule||null;
  grid.append(card("Migration wave plan","F14", wv.note? `<p class="sub">${wv.note}</p>` : `
    <table><thead><tr><th>Wave</th><th>Kind</th><th class="num">Apps</th><th class="num">Servers</th><th>Go-live</th><th>Risk</th></tr></thead><tbody>
    ${(wv.waves||[]).map(w=>`<tr>
      <td>${w.wave}</td><td>${w.kind}</td><td class="num">${w.app_count}</td><td class="num">${w.server_count}</td>
      <td data-layout="font-size:12px;color:var(--muted)">${w.go_live||"—"}${w.duration_weeks?` <span data-layout="font-size:11px">(${w.duration_weeks}w)</span>`:""}</td>
      <td><div class="bar risk-${w.risk_band}" data-layout="width:110px"><i data-layout="width:${Math.min(100,w.risk_score)}%"></i></div>
          <span data-layout="font-size:11px;color:var(--muted)">${w.risk_score} ${w.risk_band}</span></td>
    </tr>`).join("")}
    </tbody></table>
    ${sch? `<p data-layout="font-size:12px;color:var(--muted);margin-top:8px">
      <b>Schedule</b> ${sch.start} → ${sch.end} · ${sch.total_weeks} weeks · ${sch.parallel_waves} wave(s) in parallel<br>
      <b>Critical path</b> ${(sch.critical_path||[]).map(c=>"W"+c.wave).join(" → ")||"—"}</p>`:""}`));

  // --- effort
  const ef=sectionBody(pkg,"migration_effort");
  grid.append(card("Migration effort & services cost","F11", `
    <div data-layout="font-size:20px;font-weight:650">${fmt(ef.estimate_at_completion_pd)} <span data-layout="font-size:12px;color:var(--muted)">person-days (EAC)</span></div>
    <div data-layout="color:var(--muted);font-size:13px">range ${fmt(ef.range_pd?.low)}–${fmt(ef.range_pd?.high)} PD ·
      services ~${money(ef.services_cost?.expected, ef.services_cost?.currency)}
      (${money(ef.services_cost?.low, ef.services_cost?.currency)}–${money(ef.services_cost?.high, ef.services_cost?.currency)})</div>
    ${(()=>{const ws=(ef.workstreams||[]).slice().sort((a,b)=>b.pd-a.pd);const mx=Math.max(...ws.map(w=>w.pd),1);
      return `<div data-layout="margin-top:12px">${ws.slice(0,7).map(w=>`
        <div data-layout="display:flex;align-items:center;gap:8px;margin-top:5px">
          <span data-layout="width:210px;font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${w.workstream}</span>
          <div class="bar" data-layout="flex:1"><i data-layout="width:${w.pd/mx*100}%"></i></div>
          <span data-layout="width:52px;text-align:right;font-size:12px" class="num">${fmt(w.pd)}</span></div>`).join("")}</div>`;})()}
    ${(()=>{const rl=ef.resource_loading;if(!rl||!rl.curve)return"";
      const mx=Math.max(...rl.curve.map(c=>c.fte||0),1);
      return `<div data-layout="margin-top:14px">
        <div data-layout="font-size:12px;color:var(--muted)"><b>Resource loading</b> — peak ${rl.peak_fte} FTE (${rl.peak_month}) · avg ${rl.avg_fte} FTE · ${rl.months} months</div>
        <div data-layout="display:flex;align-items:flex-end;gap:2px;height:52px;margin-top:6px">
          ${rl.curve.map(c=>`<div title="${c.month}: ${c.fte} FTE (${fmt(c.pd)} PD)" data-layout="flex:1;background:var(--accent,#0078D4);opacity:.75;height:${Math.round((c.fte||0)/mx*100)}%;min-height:2px;border-radius:2px 2px 0 0"></div>`).join("")}
        </div>
        <div data-layout="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:2px"><span>${rl.curve[0]?.month||""}</span><span>${rl.curve[rl.curve.length-1]?.month||""}</span></div>
      </div>`;})()}
    <p data-layout="font-size:12px;color:var(--muted);margin-top:10px">${ef.basis||""}</p>`));

  // --- register + appendix (wide)
  const reg=pkg.register||{};
  const disc=reg.discovery||null;
  grid.append(card("Assumptions, exclusions & data gaps",null, `
    <div class="kv">
      <b>Assumptions</b><span>${(reg.assumptions||[]).length}</span>
      <b>Exclusions</b><span>${(reg.exclusions||[]).length}</span>
      <b>Data gaps</b><span>${(reg.data_gaps||[]).length}</span>
    </div>
    ${disc? `<p data-layout="font-size:12px;margin:6px 0 0"><b>Discovery questionnaire</b> — ${disc.headline||""}
      ${disc.must_open? `· <a href="/questionnaire">ask the client</a>`:``}</p>`:``}
    ${regList("Assumptions",reg.assumptions)}
    ${regList("Exclusions",reg.exclusions)}
    ${regList("Data gaps",reg.data_gaps)}`,true));

  const app=el("div","card wide");
  app.append(el("h2",null,"Calculation appendix — every figure, traceable"));
  const d=el("details"); d.append(el("summary",null,"Show the calculation appendix"));
  const tbl=el("table"); safeSetHTML(tbl,`<thead><tr><th>Ref</th><th>Figure</th><th class="num">Result</th>
    <th>Formula</th><th>Inputs</th><th>Assumptions</th><th>Conf.</th></tr></thead><tbody>${
    (pkg.calculation_appendix||[]).map(a=>`<tr>
      <td>${a.figure_id}</td><td>${a.label}</td><td class="num">${fmt(a.result)} ${a.unit||""}</td>
      <td><code>${a.formula||""}</code></td>
      <td>${Object.entries(a.inputs||{}).filter(([,v])=>v!=null).map(([k,v])=>`${k}=${fmt(v)}`).join(", ")||"—"}</td>
      <td>${(a.assumptions_applied||[]).join(", ")||"—"}</td><td>${a.confidence||""}</td>
    </tr>`).join("")}</tbody>`);
  d.append(tbl); app.append(d); grid.append(app);

  root.append(el("p","foot",
    (meta.watermark||"DRAFT — architect review required")
    + " · every figure on this page comes from the estimate package; references (F#) tie to the calculation appendix."));
}

function card(title,refId,html,wide){
  const c=el("div","card"+(wide?" wide":""));
  c.append(el("h2",null, title + (refId? ` <span class="ref">${refId}</span>`:"")));
  c.append(el("div",null,html));
  return c;
}
function barsFromObj(obj,title){
  if(!obj) return "";
  const max=Math.max(...Object.values(obj))||1;
  return `<div data-layout="margin-top:10px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em">${title}</div>`
    + Object.entries(obj).map(([k,v])=>`<div data-layout="display:flex;align-items:center;gap:8px;margin-top:5px">
        <span data-layout="width:70px;font-size:12px;color:var(--muted)">${k}</span>
        <div class="bar" data-layout="flex:1"><i data-layout="width:${v/max*100}%"></i></div>
        <span data-layout="width:38px;text-align:right;font-size:12px" class="num">${v}</span></div>`).join("");
}
function regList(label,items){
  if(!items||!items.length) return "";
  return `<details><summary>${label} (${items.length})</summary><ul data-layout="margin:6px 0 0;padding-left:18px">
    ${items.map(i=>`<li data-layout="margin:3px 0"><b>${i.id}</b> ${i.text}${i.source&&i.source!=="standing"?` <span data-layout="color:var(--muted)">(${i.source})</span>`:""}</li>`).join("")}
  </ul></details>`;
}

function renderLZDiagram(){
  const host=$("#lzdiagram"); if(!host) return;
  fetch(withScope("/dashboard/landing-zone-diagram?optional=1",{snap:false})).then(r=> r.ok? r.text() : null).then(txt=>{
    if(!txt){ host.innerHTML=""; return; }
    const dl=withScope("/dashboard/landing-zone-diagram",{snap:false})+"&fmt=drawio&download=1";
    let view;
    if(txt.trim().startsWith("<svg")){
      view=`<div data-layout="overflow:auto;border:1px solid var(--line);border-radius:8px;background:#fff;padding:6px">${txt}</div>`;
    } else {
      view='<p>Download the diagram below to open it in draw.io.</p>';
    }
    safeSetHTML(host,`<div data-layout="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;margin-bottom:4px">Target diagram</div>
      ${view}<a href="${dl}" data-layout="font-size:12px">Download .drawio</a>`);
  }).catch(()=>{ host.innerHTML=""; });
}

function renderPOE(){
  const body=$("#poeBody"); if(!body) return;
  fetch(withScope("/dashboard/landing-zone?optional=1",{snap:false})).then(r=> r.status===204 || r.status===404? null : r.json()).then(d=>{
    const cardEl=$("#poeCard");
    if(!d || d.status==="none"){ safeSetHTML(body,`Not built yet. Ask the estimator for
      <b>"Landing zone cost (Calculator POE)"</b> — it drives the real Azure Pricing
      Calculator and stores its Excel here for your Microsoft funding submission.`); return; }
    if(d.status==="building"){
      safeSetHTML(body,`<div data-layout="display:flex;align-items:center;gap:8px">
        <span class="spin" data-layout="width:14px;height:14px;border-width:2px"></span>
        <span>Driving the Azure Pricing Calculator… (${d.spec_line_count||d.line_count||"~50"} line items,
        a few minutes). This card refreshes automatically.</span></div>`);
      setTimeout(renderPOE, 15000); return;
    }
    if(d.status==="failed"){
      safeSetHTML(body,`<div data-layout="color:var(--warn)">The calculator run failed:
        ${d.error||"unknown error"}.</div>
        <p data-layout="font-size:12px;color:var(--muted)">Ask the estimator to try
        <b>"Landing zone cost (Calculator POE)"</b> again.</p>`);
      return;
    }
    const rc=d.reconciliation||{}, cur=d.currency||"USD";
    const flag = rc.delta_pct==null ? "" :
      `<span class="ref" data-layout="background:${rc.within_tolerance?'var(--ok,#0e7c3a)':'var(--warn)'}">
         vs internal ${rc.delta_pct>0?"+":""}${rc.delta_pct}%</span>`;
    if(cardEl) safeSetHTML(cardEl.querySelector("h2"), `Azure landing zone — Pricing Calculator POE ${flag}`);
    safeSetHTML(body,`
      <div data-layout="font-size:22px;font-weight:650">${money(d.monthly_total,cur)}
        <span data-layout="font-size:12px;color:var(--muted)">/ month · ~${money(d.annual,cur)} / yr</span></div>
      <div data-layout="color:var(--muted);font-size:12px;margin:2px 0 10px">
        ${d.line_count} line items · ${d.region||""} · created ${d.created_at||"?"} ·
        source: Azure Pricing Calculator export</div>
      <div class="dl" data-layout="display:flex;gap:8px;flex-wrap:wrap">
        <a href="${withScope('/dashboard/download/landing-zone-xlsx',{snap:false})}"><b>Download Excel (POE)</b></a>
        ${d.calculator_url?`<a href="${d.calculator_url}" target="_blank" rel="noopener">Open calculator ↗</a>`:""}
      </div>
      ${(d.skipped&&d.skipped.length)? `<details data-layout="margin-top:10px"><summary>Not in the calculator estimate (${d.skipped.length})</summary>
        <ul data-layout="margin:6px 0 0;padding-left:18px;font-size:12px;color:var(--muted)">
        ${d.skipped.map(s=>`<li>${(s.what||"")} — ${(s.why||"")}</li>`).join("")}</ul></details>`:""}
      <p data-layout="font-size:11px;color:var(--muted);margin-top:10px">${d.note||""}</p>`);
  }).catch(()=>{ if(body) body.textContent="Could not load the Pricing Calculator estimate."; });
}

function loadDashboard(){
 fetch(withScope("/dashboard/data")).then(r=>{
  if(r.status===404) throw new Error("no-estimate");
  if(!r.ok) throw new Error("http "+r.status);
  return r.json();
}).then(pkg=>{ render(pkg); renderPOE(); loadVersions(); }).catch(err=>{
  safeSetHTML($("#root"), err.message==="no-estimate"
    ? `<div class="empty"><h2 data-layout="margin:0 0 8px">No assessment published yet</h2>
       <p>Run the estimator and call <code>publish_estimate</code> (or the operator does it once).<br>
       The dashboard will show the current-state summary, right-sizing &amp; cost, landing zone,
       6R disposition, wave plan and migration effort — with Excel / Word / PowerPoint downloads.</p></div>`
    : `<div class="empty">Could not load the assessment (${err.message}).</div>`);
 });
}

function loadVersions(){
  const sel = $("#verSel"); if(!sel || !ENG) return;
  const [c,p] = ENG.split("/");
  fetch(`/api/engagements/${encodeURIComponent(c)}/${encodeURIComponent(p)}/history`)
    .then(r=> r.ok ? r.json() : {versions:[]}).then(j=>{
      const vs = j.versions||[];
      if(!vs.length){ sel.hidden = true; return; }
      sel.hidden = false;
      safeSetHTML(sel,`<option value="">Latest (current)</option>` + vs.map(v=>{
        const when = (v.published_at||v.stamp||"").replace("T"," ").replace("Z"," UTC");
        return `<option value="${v.stamp}"${v.stamp===SNAP?" selected":""}>${when}</option>`;
      }).join(""));
    }).catch(()=>{ sel.hidden = true; });
}
$("#verSel").addEventListener("change", e=>{
  SNAP = e.target.value;
  const u = new URL(location.href);
  if(SNAP) u.searchParams.set("snapshot", SNAP); else u.searchParams.delete("snapshot");
  history.replaceState(null,"",u);
  loadDashboard();
});

// keep the download links scoped to the engagement + selected version
["xlsx","docx","pptx"].forEach(f=>{
  const a = document.querySelector(`.dl a[href$="/${f}"]`);
  if(a) a.addEventListener("click", ev=>{ ev.preventDefault();
    location.href = withScope("/dashboard/download/"+f); });
});

loadDashboard();
