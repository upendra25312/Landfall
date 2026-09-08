"""
assemble_estimate (PRD E5.1 / E5.2 / E5.3) — one structured estimate package.

    package = assemble_estimate(inputs, cfg)

`inputs` carries an inventory summary plus the outputs of the other tools
(compute_cost, storage_cost, run_rate_extras, landing_zone, dispositions, waves).
Every one is optional — a missing tool output just leaves its section marked
"not run". The package has:

  * 8 sections (config-driven list)
  * a stable ID on every headline figure, each with a calculation-appendix entry
    (source tool, inputs, formula, assumptions applied, confidence)   -- E5.2
  * a machine-built assumptions / exclusions / data-gaps register collected from
    every tool's own caveats + the data-quality report                -- E5.3
  * a markdown render

Deterministic and pure. `generated_on` comes from inputs (or is left null) so the
package is reproducible.
"""
from __future__ import annotations

from cost.config import load_config
from .effort import estimate_effort

_SECTION_TITLES = {
    "current_state": "Current-state summary",
    "landing_zone": "Landing-zone scope",
    "disposition": "Application disposition (6R)",
    "waves": "Migration wave plan",
    "run_rate_cost": "Azure run-rate cost",
    "migration_effort": "Migration effort & services cost",
    "assumptions_register": "Assumptions, exclusions & data gaps",
    "next_steps": "Next steps",
}


def _money(v):
    return None if v is None else round(float(v), 2)


class _Reg:
    """Accumulates the assumptions / exclusions / data-gaps register (E5.3)."""

    def __init__(self):
        self.items: list[dict] = []
        self._seen: set = set()

    def add(self, text, category, source, impact=None):
        key = (category, text.strip().lower())
        if not text or key in self._seen:
            return None
        self._seen.add(key)
        pfx = {"assumption": "A", "exclusion": "X", "data_gap": "G"}[category]
        rid = f"{pfx}{sum(1 for i in self.items if i['category'] == category) + 1}"
        self.items.append({"id": rid, "category": category, "text": text.strip(),
                           "source": source, "impact": impact})
        return rid

    def ids_from(self, source):
        return [i["id"] for i in self.items if i["source"] == source]

    def by_category(self, category):
        return [i for i in self.items if i["category"] == category]


def assemble_estimate(inputs: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    dv = cfg["deliverable"]
    inv = inputs.get("inventory_summary") or {}
    dq = inputs.get("data_quality") or {}
    cc = inputs.get("compute_cost") or {}
    sc = inputs.get("storage_cost") or {}
    rr = inputs.get("run_rate_extras") or {}
    lz = inputs.get("landing_zone") or {}
    disp = inputs.get("dispositions") or {}
    wav = inputs.get("waves") or {}
    generated_on = inputs.get("generated_on")

    reg = _Reg()
    dq_conf = dq.get("confidence") or "Medium"

    # --- fold every tool's own caveats into the register (E5.3) -----------
    for text in dq.get("findings", []) or []:
        reg.add(text, "data_gap", "data_quality")
    for text in cc.get("assumptions", []) or []:
        reg.add(text, "assumption", "compute_cost")
    for sk in cc.get("missing_prices", []) or []:
        reg.add(f"No retail price found for SKU {sk} — line estimated from catalogue nearest",
                "data_gap", "compute_cost")
    for text in sc.get("caveats", []) or []:
        reg.add(text, "assumption", "storage_cost")
    for text in sc.get("not_costed", []) or []:
        reg.add(f"Storage row not costed: {text}", "data_gap", "storage_cost")
    for text in rr.get("assumptions", []) or []:
        reg.add(text, "assumption", "run_rate_extras")
    for text in lz.get("assumptions", []) or []:
        reg.add(text, "assumption", "landing_zone")
    for text in disp.get("assumptions", []) or []:
        reg.add(text, "assumption", "dispositions")
    for aid in (disp.get("summary", {}) or {}).get("needs_human_decision", []) or []:
        reg.add(f"Disposition for {aid} needs a business decision before the plan locks",
                "data_gap", "dispositions")
    for text in wav.get("assumptions", []) or []:
        reg.add(text, "assumption", "waves")

    # standing exclusions (always true for a Landfall estimate)
    for x in ["ExpressRoute / VPN circuit charges and any carrier fees",
              "Landing-zone fixed platform services beyond the build effort",
              "Database compute and licensing for replatformed PaaS databases",
              "Software licences carried forward (OS ESU, middleware, third-party agents)",
              "Organisational change management, training, and end-user comms",
              "Post-migration managed-run / operate services (separate engagement)"]:
        reg.add(x, "exclusion", "standing")
    reg.add("All figures are DRAFT pending named-architect review; not a fixed price.",
            "assumption", "standing")

    # --- effort (E6.2 basic) --------------------------------------------
    spokes = len(lz.get("spokes", []) or [])
    effort = estimate_effort(
        server_count=_int(inv.get("servers")),
        app_count=_int(inv.get("applications")) or len(disp.get("dispositions", []) or []),
        dispositions=disp.get("dispositions"),
        dq_confidence=dq_conf,
        spokes=spokes,
        regulated=bool(lz.get("regulated")),
        waves=len(wav.get("waves", []) or []),
        cfg=cfg,
    )

    # --- figures + calculation appendix (E5.2) ---------------------------
    figs = _Figs(reg)
    cur = "current_state"

    figs.add("servers_total", "Servers in scope", _int(inv.get("servers")), "count", cur,
             "inventory", {"table": "servers"}, "COUNT(servers)", dq_conf)
    figs.add("vcpu_total", "Current vCPU", _int(inv.get("total_vcpu")), "vCPU", cur,
             "inventory", {"table": "servers"}, "SUM(servers.vcpu)", dq_conf)
    figs.add("apps_total", "Applications", _int(inv.get("applications")), "count", cur,
             "inventory", {"table": "applications"}, "COUNT(applications)", dq_conf)
    figs.add("eol_servers", "Servers past OS end-of-support", _int(inv.get("eol_servers")),
             "count", cur, "inventory", {"table": "servers"},
             "COUNT(servers WHERE os_eol_date < today)", dq_conf)

    ct = cc.get("totals", {}) or {}
    if ct:
        figs.add("compute_monthly", "Compute + managed disk / month",
                 _money(ct.get("monthly")), cc.get("currency", "USD"), "run_rate_cost",
                 "estimate_compute_cost",
                 {"region": cc.get("region"), "reserved_term": cc.get("reserved_term"),
                  "price_date": cc.get("price_date"), "servers": len(cc.get("line_items", []))},
                 "sum(line_items.total_monthly)", _conf_from(cc.get("rightsize_summary", {})))
    st = sc.get("totals", {}) or {}
    if st:
        figs.add("storage_monthly", "File / DB / object storage / month",
                 _money(st.get("monthly")), sc.get("currency", "USD"), "run_rate_cost",
                 "estimate_storage_cost",
                 {"file": st.get("file_monthly"), "db": st.get("db_monthly"),
                  "object": st.get("object_monthly"),
                  "block_excluded": (sc.get("excluded", {}) or {}).get("block_volumes")},
                 "file_monthly + db_monthly + object_monthly", "Medium")
    rt = (rr.get("run_rate_monthly", {}) or {})
    if rt:
        figs.add("extras_monthly", "Backup / egress / monitoring / support / month",
                 _money(rt.get("total_monthly")), rr.get("currency", "USD"), "run_rate_cost",
                 "estimate_run_rate_extras",
                 {"backup": (rt.get("backup", {}) or {}).get("monthly"),
                  "egress": (rt.get("egress", {}) or {}).get("monthly"),
                  "monitoring": (rt.get("monitoring", {}) or {}).get("monthly"),
                  "support": (rt.get("support", {}) or {}).get("monthly")},
                 "backup + egress + monitoring + support", "Low")

    total_monthly = sum(x for x in (ct.get("monthly"), st.get("monthly"),
                                    rt.get("total_monthly")) if x) or None
    one_time = (rr.get("one_time", {}) or {}).get("total")
    if total_monthly is not None:
        figs.add("run_rate_monthly", "Total Azure run-rate / month", _money(total_monthly),
                 cc.get("currency", "USD"), "run_rate_cost", "assemble_estimate",
                 {"compute": ct.get("monthly"), "storage": st.get("monthly"),
                  "extras": rt.get("total_monthly")},
                 "compute + storage + extras", _worst(dq_conf, "Low"))
        figs.add("run_rate_annual", "Total Azure run-rate / year",
                 _money(total_monthly * 12), cc.get("currency", "USD"), "run_rate_cost",
                 "assemble_estimate", {"monthly": _money(total_monthly)}, "monthly x 12",
                 _worst(dq_conf, "Low"))
    if one_time is not None:
        figs.add("one_time_cost", "One-time migration cost (dual-run, tooling)",
                 _money(one_time), rr.get("currency", "USD"), "run_rate_cost",
                 "estimate_run_rate_extras",
                 {"dual_run": (rr.get("one_time", {}).get("dual_run", {}) or {}).get("cost"),
                  "tooling": (rr.get("one_time", {}).get("migration_tooling", {}) or {}).get("cost")},
                 "dual_run + tooling + replication_egress", "Low")

    figs.add("effort_pd", "Migration effort (person-days, EAC)",
             effort["estimate_at_completion_pd"], "PD", "migration_effort", "estimate_effort",
             {"delivery_subtotal": effort["delivery_subtotal_pd"],
              "contingency_pct": effort["contingency_pct"]},
             "delivery + PM% + governance% + contingency%", dq_conf)
    figs.add("services_cost", "Migration services cost (expected)",
             effort["services_cost"]["expected"], effort["services_cost"]["currency"],
             "migration_effort", "estimate_effort",
             {"eac_pd": effort["estimate_at_completion_pd"],
              "blended_day_rate": effort["blended_day_rate"]},
             "EAC person-days x blended day rate", dq_conf)

    if lz.get("spokes"):
        figs.add("lz_spokes", "Landing-zone spokes", spokes, "count", "landing_zone",
                 "design_landing_zone", {"zones": lz.get("zone_counts")},
                 "one per (zone x environment) + regulated + sandbox", "Medium")
    if wav.get("waves"):
        figs.add("wave_count", "Migration waves", len(wav["waves"]), "count", "waves",
                 "plan_waves", {"move_groups": len(wav.get("move_groups", []))},
                 "risk-ordered packing of move-groups", "Medium")

    # --- top cost drivers (E2.5) ----------------------------------------
    drivers = _top_drivers(cc, sc, rt, dv.get("top_cost_drivers", 3))

    # --- sections -------------------------------------------------------
    section_ids = dv.get("sections") or list(_SECTION_TITLES)
    bodies = {
        "current_state": _body_current_state(inv, dq),
        "landing_zone": _body_lz(lz),
        "disposition": _body_disp(disp),
        "waves": _body_waves(wav),
        "run_rate_cost": {"currency": cc.get("currency", "USD"),
                          "region": cc.get("region") or lz.get("region"),
                          "price_date": cc.get("price_date"),
                          "reserved_term": cc.get("reserved_term"),
                          "monthly": _money(total_monthly),
                          "annual": _money(total_monthly * 12) if total_monthly else None,
                          "one_time": _money(one_time),
                          "range": (cc.get("totals", {}) or {}).get("range"),
                          "top_cost_drivers": drivers},
        "migration_effort": effort,
        "assumptions_register": {
            "assumptions": reg.by_category("assumption"),
            "exclusions": reg.by_category("exclusion"),
            "data_gaps": reg.by_category("data_gap"),
        },
        "next_steps": {"actions": _next_steps(reg, disp, dq_conf)},
    }
    sections = []
    for sid in section_ids:
        sections.append({
            "id": f"S{len(sections) + 1}",
            "key": sid,
            "title": _SECTION_TITLES.get(sid, sid),
            "figures": [f["id"] for f in figs.items if f["section"] == sid],
            "body": bodies.get(sid, {"note": "not run — tool output not supplied"}),
        })

    confidences = [f["confidence"] for f in figs.items if f["confidence"]]
    overall = _worst(*(confidences or ["Medium"]))

    package = {
        "meta": {
            "package_id": inputs.get("package_id", "landfall-estimate"),
            "generated_on": generated_on,
            "status": "DRAFT",
            "watermark": dv.get("watermark"),
            "firm_name": dv.get("firm_name"),
            "region": cc.get("region") or lz.get("region"),
            "currency": cc.get("currency", cfg["pricing"].get("currency", "USD")),
            "price_date": cc.get("price_date"),
            "overall_confidence": overall,
            "config_source": cfg.get("_source"),
            "tools_run": [k for k in ("compute_cost", "storage_cost", "run_rate_extras",
                                      "landing_zone", "dispositions", "waves")
                          if inputs.get(k)],
        },
        "sections": sections,
        "figures": figs.items,
        "calculation_appendix": figs.appendix,
        "register": {
            "assumptions": reg.by_category("assumption"),
            "exclusions": reg.by_category("exclusion"),
            "data_gaps": reg.by_category("data_gap"),
        },
    }
    package["summary_markdown"] = render_markdown(package)
    return package


# --- figure builder ------------------------------------------------------

class _Figs:
    def __init__(self, reg: _Reg):
        self.reg = reg
        self.items: list[dict] = []
        self.appendix: list[dict] = []

    def add(self, key, label, value, unit, section, source_tool, inputs, formula, confidence):
        fid = f"F{len(self.items) + 1}"
        applied = self.reg.ids_from(source_tool)
        fig = {"id": fid, "key": key, "label": label, "value": value, "unit": unit,
               "section": section, "source_tool": source_tool, "confidence": confidence}
        self.items.append(fig)
        self.appendix.append({
            "figure_id": fid, "label": label, "result": value, "unit": unit,
            "source_tool": source_tool, "inputs": inputs, "formula": formula,
            "assumptions_applied": applied, "confidence": confidence,
        })
        return fid


# --- section bodies ----------------------------------------------------

def _body_current_state(inv, dq):
    return {
        "servers": _int(inv.get("servers")),
        "servers_powered_on": inv.get("servers_powered_on"),
        "applications": _int(inv.get("applications")),
        "total_vcpu": inv.get("total_vcpu"),
        "total_ram_gb": inv.get("total_ram_gb"),
        "provisioned_disk_tb": inv.get("provisioned_disk_tb"),
        "used_disk_tb": inv.get("used_disk_tb"),
        "os_mix": inv.get("os_mix"),
        "by_env": inv.get("by_env"),
        "criticality_spread": inv.get("criticality_spread"),
        "eol_servers": inv.get("eol_servers"),
        "no_perf_data_servers": inv.get("no_perf_data_servers"),
        "data_quality_confidence": dq.get("confidence"),
        "data_quality_findings": dq.get("findings"),
    }


def _body_lz(lz):
    if not lz:
        return {"note": "design_landing_zone not run"}
    return {
        "summary": lz.get("summary"),
        "region": lz.get("region"), "dr_region": lz.get("dr_region"),
        "regulated": lz.get("regulated"),
        "regulated_scopes": lz.get("regulated_scopes_present"),
        "management_groups": lz.get("management_groups"),
        "subscriptions": lz.get("subscriptions"),
        "spokes": [{"name": s.get("name"), "zone": s.get("zone"),
                    "address_space": s.get("address_space")} for s in lz.get("spokes", [])],
        "identity": lz.get("identity", {}).get("model"),
        "connectivity": lz.get("connectivity", {}).get("model"),
        "policy_overlay": lz.get("policy", {}).get("regulated_overlay"),
        "dr": lz.get("dr", {}).get("strategy"),
    }


def _body_disp(disp):
    if not disp:
        return {"note": "score_dispositions not run"}
    return {
        "by_disposition": (disp.get("summary", {}) or {}).get("by_disposition"),
        "needs_human_decision": (disp.get("summary", {}) or {}).get("needs_human_decision"),
        "applications": [{"app_id": d.get("app_id"), "app_name": d.get("app_name"),
                          "disposition": d.get("disposition"), "confidence": d.get("confidence"),
                          "rationale": d.get("rationale")} for d in disp.get("dispositions", [])],
    }


def _body_waves(wav):
    if not wav:
        return {"note": "plan_waves not run"}
    return {
        "graph": wav.get("graph"),
        "waves": [{"wave": w.get("wave"), "kind": w.get("kind"),
                   "app_count": w.get("app_count"), "server_count": w.get("server_count"),
                   "risk_score": w.get("risk_score"), "risk_band": w.get("risk_band"),
                   "risk_factors": w.get("risk_factors"),
                   "blocking_dependencies": w.get("blocking_dependencies")}
                  for w in wav.get("waves", [])],
    }


def _next_steps(reg, disp, dq_conf):
    out = ["Named architect reviews and owns every figure in this package."]
    gaps = reg.by_category("data_gap")
    if gaps:
        out.append(f"Close the {len(gaps)} data gap(s) in the register with the client "
                   f"(send the data-quality report).")
    nh = (disp.get("summary", {}) or {}).get("needs_human_decision") or []
    if nh:
        out.append(f"Business owners confirm the disposition for {len(nh)} application(s): "
                   + ", ".join(nh[:8]) + ("..." if len(nh) > 8 else "") + ".")
    if dq_conf == "Low":
        out.append("Data-quality confidence is Low — propose a short paid discovery to "
                   "tighten the estimate before the SoW.")
    out.append("Map the register to the RFP working-assumptions (AS-*) and risk (RK-*) sections.")
    out.append("Apply the firm's rate card; the services cost here uses the blended day rate.")
    return out


# --- helpers ---------------------------------------------------------

_CONF_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def _worst(*confs):
    vals = [c for c in confs if c in _CONF_ORDER]
    return min(vals, key=lambda c: _CONF_ORDER[c]) if vals else "Medium"


def _conf_from(rightsize_summary):
    lc = (rightsize_summary or {}).get("low_confidence", 0)
    n = (rightsize_summary or {}).get("servers", 0) or 1
    return "Low" if lc / n > 0.25 else "Medium"


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _top_drivers(cc, sc, rt, n):
    """cc/sc are the full estimate_compute_cost / estimate_storage_cost outputs;
    rt is run_rate_extras['run_rate_monthly']."""
    ct = cc.get("totals", {}) or {}
    st = sc.get("totals", {}) or {}
    rows = [
        ("Compute — effective (right-sized, reserved)", ct.get("compute_effective_monthly")),
        ("Managed disk (per-VM block)", ct.get("storage_monthly")),
        ("File shares (Files / NetApp)", st.get("file_monthly")),
        ("PaaS-DB storage", st.get("db_monthly")),
        ("Monitoring (Log Analytics + Defender)", (rt.get("monitoring", {}) or {}).get("monthly")),
        ("Backup", (rt.get("backup", {}) or {}).get("monthly")),
        ("Internet egress", (rt.get("egress", {}) or {}).get("monthly")),
    ]
    rows = [(name, round(float(v), 2)) for name, v in rows if v]
    rows.sort(key=lambda r: -r[1])
    total = sum(v for _, v in rows) or 1
    return [{"driver": name, "monthly": v, "share_pct": round(100 * v / total, 1)}
            for name, v in rows[:n]]


# --- markdown render -------------------------------------------------

def render_markdown(package: dict) -> str:
    m = package["meta"]
    L = [f"# Migration estimate — {m.get('package_id')}", ""]
    L.append(f"> **{m.get('watermark')}**")
    L.append("")
    L.append(f"- Region: **{m.get('region') or 'n/a'}**  ·  Currency: {m.get('currency')}  "
             f"·  Prices as of: {m.get('price_date') or 'n/a'}")
    L.append(f"- Overall confidence: **{m.get('overall_confidence')}**  ·  "
             f"Tools run: {', '.join(m.get('tools_run') or []) or 'none'}")
    if m.get("generated_on"):
        L.append(f"- Generated: {m['generated_on']}")
    L.append("")

    key_figs = [f for f in package["figures"]
                if f["key"] in ("run_rate_monthly", "run_rate_annual", "one_time_cost",
                                "effort_pd", "services_cost")]
    if key_figs:
        L += ["## Headline numbers", "", "| Figure | Value | Confidence | Ref |",
              "|---|---:|---|---|"]
        for f in key_figs:
            L.append(f"| {f['label']} | {_fmt(f['value'])} {f['unit']} | {f['confidence']} | {f['id']} |")
        L.append("")

    for s in package["sections"]:
        L.append(f"## {s['id']}. {s['title']}")
        L.append("")
        L += _render_body(s["key"], s["body"])
        if s["figures"]:
            L.append("")
            L.append("_Figures: " + ", ".join(s["figures"]) + "_")
        L.append("")

    L += ["## Calculation appendix", "",
          "| Ref | Figure | Result | Formula | Inputs | Assumptions | Confidence |",
          "|---|---|---:|---|---|---|---|"]
    for a in package["calculation_appendix"]:
        L.append(f"| {a['figure_id']} | {a['label']} | {_fmt(a['result'])} {a['unit']} | "
                 f"`{a['formula']}` | {_kv(a['inputs'])} | "
                 f"{', '.join(a['assumptions_applied']) or '—'} | {a['confidence']} |")
    L.append("")

    r = package["register"]
    for cat, title in (("assumptions", "Assumptions"), ("exclusions", "Exclusions"),
                       ("data_gaps", "Data gaps")):
        L.append(f"## Register — {title}")
        L.append("")
        for i in r[cat]:
            src = f" _(from {i['source']})_" if i.get("source") and i["source"] != "standing" else ""
            L.append(f"- **{i['id']}** {i['text']}{src}")
        if not r[cat]:
            L.append("- (none)")
        L.append("")
    return "\n".join(L)


def _render_body(key, body):
    if body.get("note"):
        return [f"_{body['note']}_"]
    if key == "current_state":
        return [f"- {body.get('servers')} servers ({body.get('servers_powered_on') or '?'} powered on), "
                f"{body.get('applications')} applications",
                f"- {body.get('total_vcpu')} vCPU · {body.get('total_ram_gb')} GB RAM · "
                f"{body.get('provisioned_disk_tb')} TB provisioned disk",
                f"- {body.get('eol_servers')} servers past OS end-of-support · "
                f"{body.get('no_perf_data_servers') or 0} without performance history",
                f"- Data-quality confidence: **{body.get('data_quality_confidence') or 'n/a'}**"]
    if key == "landing_zone":
        return [f"- {body.get('summary')}",
                f"- {len(body.get('spokes', []))} spokes · identity: {body.get('identity')} · "
                f"connectivity: {body.get('connectivity')}",
                f"- DR: {body.get('dr')}"]
    if key == "disposition":
        bd = body.get("by_disposition") or {}
        return ["- " + ", ".join(f"{v} {k}" for k, v in bd.items()),
                f"- Needs a business decision: {', '.join(body.get('needs_human_decision') or []) or 'none'}"]
    if key == "waves":
        rows = ["| Wave | Kind | Apps | Servers | Risk |", "|---|---|---:|---:|---:|"]
        for w in body.get("waves", []):
            rows.append(f"| {w['wave']} | {w['kind']} | {w['app_count']} | "
                        f"{w['server_count']} | {w['risk_score']} ({w['risk_band']}) |")
        return rows
    if key == "run_rate_cost":
        d = [f"- **{_fmt(body.get('monthly'))} {body.get('currency')} / month**  "
             f"(~{_fmt(body.get('annual'))} / year), region {body.get('region')}, "
             f"{body.get('reserved_term')} reserved, prices {body.get('price_date') or 'n/a'}"]
        if body.get("one_time"):
            d.append(f"- One-time migration cost: ~{_fmt(body['one_time'])} {body.get('currency')}")
        if body.get("top_cost_drivers"):
            d.append("- Top drivers: " + "; ".join(
                f"{x['driver']} ({x['share_pct']}%)" for x in body["top_cost_drivers"]))
        return d
    if key == "migration_effort":
        return [f"- **{body.get('estimate_at_completion_pd')} person-days** "
                f"(range {body['range_pd']['low']}–{body['range_pd']['high']})",
                f"- Services cost ~{_fmt(body['services_cost']['expected'])} "
                f"{body['services_cost']['currency']} "
                f"({_fmt(body['services_cost']['low'])}–{_fmt(body['services_cost']['high'])})",
                f"- {body.get('basis')}"]
    if key == "assumptions_register":
        return [f"- {len(body.get('assumptions', []))} assumptions, "
                f"{len(body.get('exclusions', []))} exclusions, "
                f"{len(body.get('data_gaps', []))} data gaps — see the Register sections below"]
    if key == "next_steps":
        return [f"1. {a}" for a in body.get("actions", [])]
    return [f"```", str(body), "```"]


def _fmt(v):
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, int) or (isinstance(v, float) and v == int(v)):
        return f"{int(v):,}"
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"
    return str(v)


def _kv(d):
    return ", ".join(f"{k}={_fmt(v)}" for k, v in (d or {}).items() if v is not None) or "—"
