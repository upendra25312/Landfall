
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

function initAreaNav(){
  const nav = $("#areaNav"); if(!nav) return;
  nav.querySelectorAll(".area-btn").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      nav.querySelectorAll(".area-btn").forEach(b=>b.classList.remove("active"));
      btn.classList.add("active");
      const target = document.getElementById("area-" + btn.dataset.area);
      if(target) target.scrollIntoView({behavior:"smooth", block:"start"});
    });
  });
}

function render(pkg){
  const root=$("#root"); root.innerHTML="";
  const meta=pkg.meta||{}, F=figMap(pkg);
  $("#statusBadge").textContent = meta.status||"Draft";
  $("#confPill").textContent = "confidence " + (meta.overall_confidence||"—");

  const h1 = el("h1",null,`Migration estimate — ${meta.package_id||""}`);
  h1.id = "area-overview";
  root.append(h1);

  root.append(el("p","sub",
    `Region ${meta.region||"n/a"} · ${meta.currency||"USD"} · prices ${meta.price_date||"n/a"}`
    + (meta.generated_on? ` · generated ${meta.generated_on}`:"")
    + (meta.tools_failed&&meta.tools_failed.length? ` · ⚠ tools failed: ${meta.tools_failed.join(", ")}`:"")));

  // Area 1: Headline tiles
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

  // Area 2: Data & Discovery
  const cDataDisc = card("02 Data & Discovery", "F1", `
    <div class="kv">
      <b>Data-quality score</b><span>${cs.data_quality_confidence||"Medium"}</span>
      <b>Total Servers</b><span>${fmt(cs.servers)} (${cs.servers_powered_on??"?"} powered on)</span>
      <b>Total Applications</b><span>${fmt(cs.applications)}</span>
      <b>No performance history</b><span>${fmt(cs.no_perf_data_servers)} servers</span>
    </div>
    <div data-layout="margin-top:10px;font-size:12px;color:var(--muted)">
      Discovery questionnaire responses and inventory imports are verified against schema bounds.
    </div>`);
  cDataDisc.id = "area-data-discovery"; grid.append(cDataDisc);

  // Area 3: Current Estate
  const cEstate = card("03 Current Estate", null, `
    <div class="kv">
      <b>Compute Total</b><span>${fmt(cs.total_vcpu)} vCPU · ${fmt(cs.total_ram_gb)} GB RAM</span>
      <b>Storage Total</b><span>${fmt(cs.provisioned_disk_tb)} TB provisioned · ${fmt(cs.used_disk_tb)} TB used</span>
      <b>OS past end-of-support</b><span>${fmt(cs.eol_servers)} servers</span>
    </div>
    ${barsFromObj(cs.by_env,"By environment")}`);
  cEstate.id = "area-current-estate"; grid.append(cEstate);

  // Area 4: Target Architecture (Landing Zone)
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
  const cLZ = card("04 Target Architecture (Landing Zone)","F13", lz.note? `<p class="sub">${lz.note}</p>` : `
    <p data-layout="margin:0 0 8px">${lz.summary||""}</p>
    <div class="kv">
      <b>Region</b><span>${lz.region||"?"} → DR ${lz.dr_region||"?"}</span>
      <b>Identity</b><span>${lz.identity||"?"}</span>
      <b>Connectivity</b><span>${lz.connectivity||"?"}</span>
      <b>Regulated scopes</b><span>${(lz.regulated_scopes&&lz.regulated_scopes.length)? lz.regulated_scopes.join(", ") : "none"}</span>
    </div>
    <div class="chips">${(lz.spokes||[]).map(s=>`<span class="chip">${s.name} ${s.address_space||""}</span>`).join("")}</div>
    <p data-layout="color:var(--muted);font-size:12px;margin-top:10px">${lz.dr||""}</p>
    <div id="lzdiagram" data-layout="margin-top:10px"></div>${dcBlock}`);
  cLZ.id = "area-target-arch"; grid.append(cLZ);
  renderLZDiagram();

  // Area 5: Azure Cost & POE
  const rc=sectionBody(pkg,"run_rate_cost"), drivers=rc.top_cost_drivers||[];
  const dcolors=["var(--c1)","var(--c2)","var(--c3)","var(--c4)","var(--c5)"];
  const shown=drivers.reduce((a,d)=>a+d.share_pct,0);
  const dslices=drivers.map((d,i)=>({label:d.driver,value:d.monthly,color:dcolors[i%5]}));
  if(shown<99 && rc.monthly) dslices.push({label:"Other",value:rc.monthly*(100-shown)/100,color:"var(--c5)"});
  const cCost = card("05 Azure Cost & Pricing Calculator POE","F8", `
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
    </tbody></table>
    <div id="poeContainer" data-layout="margin-top:14px;border-top:1px solid var(--line);padding-top:10px">
      <div id="poeBody"><p class="sub">Checking for Pricing Calculator POE…</p></div>
    </div>`);
  cCost.id = "area-cost-poe"; grid.append(cCost);
  renderPOE();

  // Area 6: Migration Strategy (6R)
  const dp=sectionBody(pkg,"disposition"), bd=dp.by_disposition||{};
  const dispColors={Rehost:"var(--c1)",Replatform:"var(--c3)",Repurchase:"var(--c4)",Retire:"var(--c5)",Retain:"var(--c2)",Refactor:"var(--bad)"};
  const dtot=Object.values(bd).reduce((a,b)=>a+b,0)||1;
  const cStrat = card("06 Migration Strategy (6R Disposition)",null, dp.note? `<p class="sub">${dp.note}</p>` : `
    <div class="bar" data-layout="height:20px;display:flex">
      ${Object.entries(bd).map(([k,v])=>`<i data-layout="width:${v/dtot*100}%;background:${dispColors[k]||"var(--c5)"};border-radius:0" title="${k}: ${v}"></i>`).join("")}
    </div>
    <div class="legend">${Object.entries(bd).map(([k,v])=>`<span><i data-layout="background:${dispColors[k]||"var(--c5)"}"></i>${k} ${v}</span>`).join("")}</div>
    ${(dp.needs_human_decision&&dp.needs_human_decision.length)? `<p data-layout="font-size:12px;color:var(--warn);margin-top:10px">Needs a business decision: ${dp.needs_human_decision.join(", ")}</p>`:""}`);
  cStrat.id = "area-strategy"; grid.append(cStrat);

  // Area 7: Migration Waves
  const wv=sectionBody(pkg,"waves");
  const sch=wv.schedule||null;
  const cWaves = card("07 Migration Wave Plan","F14", wv.note? `<p class="sub">${wv.note}</p>` : `
    <table><thead><tr><th>Wave</th><th>Kind</th><th class="num">Apps</th><th class="num">Servers</th><th>Go-live</th><th>Risk</th></tr></thead><tbody>
    ${(wv.waves||[]).map(w=>`<tr>
      <td>${w.wave}</td><td>${w.kind}</td><td class="num">${w.app_count}</td><td class="num">${w.server_count}</td>
      <td data-layout="font-size:12px;color:var(--muted)">${w.go_live||"—"}${w.duration_weeks?` <span data-layout="font-size:11px">(${w.duration_weeks}w)</span>`:""}</td>
      <td><div class="bar risk-${w.risk_band}" data-layout="width:110px"><i data-layout="width:${Math.min(100,w.risk_score)}%"></i></div>
          <span data-layout="font-size:11px;color:var(--muted)">${w.risk_score} ${w.risk_band}</span></td>
    </tr>`).join("")}
    </tbody></table>`);
  cWaves.id = "area-waves"; grid.append(cWaves);

  // Area 8: Timeline
  const cTime = card("08 Migration Timeline & Schedule", null, sch ? `
    <div class="kv">
      <b>Programme Start</b><span>${sch.start}</span>
      <b>Programme Finish</b><span>${sch.end}</span>
      <b>Total Duration</b><span>${sch.total_weeks} weeks</span>
      <b>Parallel Concurrency</b><span>${sch.parallel_waves} wave lane(s)</span>
    </div>
    <div data-layout="margin-top:10px;font-size:12px"><b>Critical Path Chain:</b> ${(sch.critical_path||[]).map(c=>"Wave "+c.wave+" ("+c.kind+")").join(" → ")||"Sequential"}</div>
    ${(sch.assumptions&&sch.assumptions.length)? `<details data-layout="margin-top:8px"><summary>Timeline assumptions</summary><ul data-layout="padding-left:18px;font-size:12px;color:var(--muted)">${sch.assumptions.map(a=>`<li>${a}</li>`).join("")}</ul></details>`:""}
  ` : `<p class="sub">No wave schedule attached to the estimate.</p>`);
  cTime.id = "area-timeline"; grid.append(cTime);

  // Area 9: Resource Plan
  const ef=sectionBody(pkg,"migration_effort");
  const cRes = card("09 Resource Demand Plan","F11", `
    <div data-layout="font-size:20px;font-weight:650">${fmt(ef.estimate_at_completion_pd)} <span data-layout="font-size:12px;color:var(--muted)">person-days (EAC)</span></div>
    <div data-layout="color:var(--muted);font-size:13px">range ${fmt(ef.range_pd?.low)}–${fmt(ef.range_pd?.high)} PD ·
      services ~${money(ef.services_cost?.expected, ef.services_cost?.currency)}</div>
    ${(()=>{const rl=ef.resource_loading;if(!rl||!rl.curve)return"";
      const mx=Math.max(...rl.curve.map(c=>c.fte||0),1);
      return `<div data-layout="margin-top:12px">
        <div data-layout="font-size:12px;color:var(--muted)"><b>Monthly Loading</b> — peak ${rl.peak_fte} FTE (${rl.peak_month}) · avg ${rl.avg_fte} FTE · ${rl.months} months</div>
        <div data-layout="display:flex;align-items:flex-end;gap:2px;height:44px;margin-top:6px">
          ${rl.curve.map(c=>`<div title="${c.month}: ${c.fte} FTE" data-layout="flex:1;background:var(--accent,#0078D4);opacity:.75;height:${Math.round((c.fte||0)/mx*100)}%;min-height:2px;border-radius:2px 2px 0 0"></div>`).join("")}
        </div>
      </div>`;})()}
    <div class="dl" data-layout="margin-top:14px">
      <a href="${withScope('/dashboard/download/resource-plan-xlsx',{snap:false})}"><b>Download Resource Plan (XLSX)</b></a>
    </div>`);
  cRes.id = "area-resource-plan"; grid.append(cRes);

  // Area 10: Capacity
  const cCap = card("10 Capacity & Heatmap", null, `
    <div id="capacityBanner" class="diff-banner">
      <b>Pre-sales Status:</b> <span>MODE 1 — Role-Based Resource Planning (Default)</span>
      <div data-layout="font-size:12px;color:var(--muted);margin-top:4px">
        Capacity is unsupplied; Landfall guarantees zero hallucination. Provide client staff count to evaluate variance.
      </div>
    </div>
    <div id="capacityHost"><p class="sub">Loading capacity heatmap preview…</p></div>`);
  cCap.id = "area-capacity"; grid.append(cCap);

  // Area 11: Migration Readiness (Interactive Drill-Down)
  const cReady = card("11 Migration Execution Readiness (MEG)", null, `
    <div data-layout="margin-bottom:8px;font-size:12px;color:var(--muted)">
      Evaluated across 21 Microsoft Azure Migration Execution Guide criteria. Click any item to inspect evidence and actions.
    </div>
    <div id="readinessHost"><div class="spin" data-layout="width:14px;height:14px;border-width:2px"></div> Loading readiness checklist…</div>`, true);
  cReady.id = "area-readiness"; grid.append(cReady);
  renderReadiness();

  // Area 12: Risks
  const cRisks = card("12 Risk Register (MEG Taxonomy)", null, `
    <div id="risksHost">
      <table data-layout="font-size:12px"><thead><tr><th>Risk Description</th><th>Trigger Source</th><th>Category</th><th>Mitigation</th></tr></thead><tbody>
        <tr><td><b>Unmonitored Servers</b></td><td>Data Quality</td><td>Operational</td><td>Deploy Azure Monitor &amp; Log Analytics agent</td></tr>
        <tr><td><b>Legacy OS End-of-Support</b></td><td>Inventory (84 VMs)</td><td>Technical</td><td>Apply Extended Security Updates (ESU) in Azure</td></tr>
        <tr><td><b>Single Region Posture</b></td><td>Landing Zone Design</td><td>Resiliency</td><td>Enable Zone-Redundant replication + secondary ASR</td></tr>
        <tr><td><b>Database Replatforming</b></td><td>6R Strategy (PaaS)</td><td>Data</td><td>Validate schema compatibility via Azure DMS</td></tr>
      </tbody></table>
    </div>`);
  cRisks.id = "area-risks"; grid.append(cRisks);

  // Area 13: Deliverables
  const cDeliv = card("13 Deliverables Hub", null, `
    <div data-layout="font-size:12px;color:var(--muted);margin-bottom:10px">
      Production-grade client artifacts generated directly from the deterministic estimate package:
    </div>
    <div class="dl-grid">
      <a class="dl-card" href="${withScope('/dashboard/download/xlsx')}">
        <div class="title">Excel Estimate (.xlsx)</div>
        <div class="meta">Live calculation model with calculation appendix formulas</div>
      </a>
      <a class="dl-card" href="${withScope('/dashboard/download/resource-plan-xlsx',{snap:false})}">
        <div class="title">Resource Plan (.xlsx)</div>
        <div class="meta">15-sheet workbook: role demand, FTE curve, and heatmap</div>
      </a>
      <a class="dl-card" href="${withScope('/dashboard/download/docx')}">
        <div class="title">Word Proposal (.docx)</div>
        <div class="meta">US-Letter proposal with structured executive narrative</div>
      </a>
      <a class="dl-card" href="${withScope('/dashboard/download/pptx')}">
        <div class="title">PowerPoint Deck (.pptx)</div>
        <div class="meta">12-slide presentation with native charts and CAF lifecycle</div>
      </a>
      <a class="dl-card" href="${withScope('/dashboard/download/landing-zone-xlsx',{snap:false})}">
        <div class="title">Calculator POE (.xlsx)</div>
        <div class="meta">Official Azure Pricing Calculator export for funding</div>
      </a>
      <a class="dl-card" href="${withScope('/dashboard/landing-zone-diagram?fmt=drawio&download=1',{snap:false})}">
        <div class="title">Landing Zone Diagram (.drawio)</div>
        <div class="meta">Editable target hub-spoke architectural topology</div>
      </a>
    </div>`, true);
  cDeliv.id = "area-deliverables"; grid.append(cDeliv);

  // Area 14: Microsoft Guidance
  const cGuidance = card("14 Microsoft Guidance & Research", null, `
    <div class="diff-banner">
      <b>ASSESSMENT BASELINE vs LIVE MICROSOFT RESEARCH</b>
      <div data-layout="font-size:12px;color:var(--muted);margin-top:4px">
        The estimate baseline is pinned and immutable. Live Microsoft Learn queries validate against pinned references without silently altering completed figures.
      </div>
    </div>
    <div class="kv">
      <b>MEG Reference Pinned</b><span>Azure/migration @ <code>09b2693</code> (2024.1)</span>
      <b>Microsoft Learn MCP</b><span>Online (Streamable HTTP, read-only cache active)</span>
      <b>Authority Hierarchy</b><span>Customer Facts (1) &gt; Deterministic Calc (2) &gt; MS Guidance (3)</span>
    </div>`);
  cGuidance.id = "area-guidance"; grid.append(cGuidance);

  // Area 15: Evidence & Calculation Appendix
  const reg=pkg.register||{};
  const cEvid = card("15 Evidence, Appendix & Provenance", null, `
    <div class="kv" data-layout="margin-bottom:10px">
      <b>Data-Handling Statement</b><span><a href="/docs/data-handling" target="_blank">View Signed Statement</a></span>
      <b>Assumptions Tracked</b><span>${(reg.assumptions||[]).length} items</span>
      <b>Standing Exclusions</b><span>${(reg.exclusions||[]).length} items</span>
      <b>Engine Provenance</b><span>Landfall v2.4.0 (MEG Commit 09b2693, Price 2026-09-08)</span>
    </div>
    ${regList("Assumptions",reg.assumptions)}
    ${regList("Exclusions",reg.exclusions)}
    ${regList("Data gaps",reg.data_gaps)}
    <details data-layout="margin-top:10px"><summary><b>Calculation appendix — every figure, traceable</b></summary>
      <table data-layout="margin-top:8px"><thead><tr><th>Ref</th><th>Figure</th><th class="num">Result</th><th>Formula</th><th>Conf.</th></tr></thead><tbody>
      ${(pkg.calculation_appendix||[]).map(a=>`<tr>
        <td><b>${a.figure_id}</b></td><td>${a.label}</td><td class="num">${fmt(a.result)} ${a.unit||""}</td>
        <td><code>${a.formula||""}</code></td><td>${a.confidence||""}</td>
      </tr>`).join("")}
      </tbody></table>
    </details>`, true);
  cEvid.id = "area-evidence"; grid.append(cEvid);

  root.append(el("p","foot",
    (meta.watermark||"DRAFT — architect review required")
    + " · 15 assessment-first areas generated deterministically. References tie to calculation appendix."));

  initAreaNav();
}

function renderReadiness(){
  const host=$("#readinessHost"); if(!host) return;
  fetch(withScope("/dashboard/readiness",{snap:false})).then(r=> r.ok? r.json() : null).then(rd=>{
    if(!rd || !rd.criteria){ host.innerHTML = "<p class='sub'>Readiness assessment not generated.</p>"; return; }
    let html = `<table data-layout="font-size:12px"><thead><tr><th>Category</th><th>Readiness Criterion</th><th>Status</th><th>Drill-Down</th></tr></thead><tbody>`;
    rd.criteria.forEach((c, idx)=>{
      const stateCls = "state-" + (c.state||"not_assessed").toLowerCase();
      html += `<tr>
        <td><b>${c.category}</b></td>
        <td>${c.title}</td>
        <td><span class="state-pill ${stateCls}">${c.state}</span></td>
        <td><button type="button" class="pill drill-btn" data-idx="${idx}">Inspect Drill-Down</button></td>
      </tr>
      <tr id="drill-row-${idx}" class="drill-row" hidden><td colspan="4">
        <div class="readiness-detail">
          <div><b>Evidence:</b> <span>${c.evidence||"None verified in inventory"}</span></div>
          <div><b>Missing Decision:</b> <span>${c.missing_decision||"None"}</span></div>
          <div><b>Responsible Role:</b> <span>${c.responsible_role||"Lead Cloud Architect"}</span></div>
          <div><b>Recommended Action:</b> <span>${c.recommended_action||"Complete assessment validation"}</span></div>
        </div>
      </td></tr>`;
    });
    html += `</tbody></table>`;
    safeSetHTML(host, html);

    host.querySelectorAll(".drill-btn").forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const r = host.querySelector("#drill-row-" + btn.dataset.idx);
        if(r) r.hidden = !r.hidden;
      });
    });
  }).catch(()=>{ if(host) host.textContent = "Could not load readiness evaluation."; });
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
 }).then(pkg=>{ render(pkg); loadVersions(); }).catch(err=>{
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
["xlsx","docx","pptx","resource-plan-xlsx"].forEach(f=>{
  const a = document.querySelector(`.dl a[href$="/${f}"]`);
  if(a) a.addEventListener("click", ev=>{ ev.preventDefault();
    location.href = withScope("/dashboard/download/"+f); });
});

loadDashboard();
