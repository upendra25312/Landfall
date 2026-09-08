"""
score_dispositions (PRD E4.2) — deterministic 6R candidate per application.

    result = score_dispositions(applications, server_rollup, cfg)

Inputs per app: criticality, internet_facing, db_engine, tech_stack, app_name,
users, plus a server rollup (server count, EOL-OS count). Output: a candidate
disposition (Rehost / Replatform / Repurchase / Retire / Retain / Refactor), a
confidence, a plain-English rationale, the signals used, and the alternatives
considered — so the agent can explain the call and never has to invent one.

Pure. All thresholds/keyword lists from estimation_config.json ["disposition"].
"""
from __future__ import annotations

from cost.config import load_config

_APPETITE = {
    # crit_relax lowers the replatform criticality floor (lets more-critical apps replatform)
    "rehost_first": {"crit_relax": 0, "refactor": False},
    "replatform_where_easy": {"crit_relax": 1, "refactor": False},
    "aggressive": {"crit_relax": 2, "refactor": True},
}


def _low(v) -> str:
    return str(v or "").lower()


def _hit(text: str, markers) -> str | None:
    t = _low(text)
    for m in markers:
        if m in t:
            return m
    return None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def score_one(app: dict, roll: dict | None, cfg: dict) -> dict:
    d = cfg["disposition"]
    roll = roll or {}
    appetite = _APPETITE.get(d.get("appetite", "rehost_first"), _APPETITE["rehost_first"])

    name = app.get("app_name") or app.get("app_id") or ""
    stack = app.get("tech_stack") or ""
    crit = _int(app.get("criticality")) or 3
    inet = str(app.get("internet_facing")).strip() in ("1", "true", "True", "yes")
    engine = app.get("db_engine") or ""
    users = _int(app.get("users"))
    servers = _int(roll.get("servers") if roll.get("servers") is not None else app.get("server_count")) or 0
    eol = _int(roll.get("eol_servers") if roll.get("eol_servers") is not None else app.get("eol_servers")) or 0

    signals = {"criticality": crit, "internet_facing": inet, "servers": servers,
               "eol_servers": eol, "db_engine": engine or None, "users": users}
    clustered = _hit(stack + " " + engine, d.get("clustered_markers", []))
    container = _hit(stack, d.get("container_markers", []))
    repurchase = next(((m, tgt) for m, tgt in d.get("repurchase_markers", {}).items()
                       if m in _low(name) or m in _low(stack)), None)
    retire_marker = _hit(name + " " + (app.get("notes") or ""), d.get("retire_markers", []))
    paas = next(((k, v) for k, v in d.get("paas_db_engines", {}).items() if k in _low(engine)), None)

    rmin = d.get("replatform_min_criticality", 3) - appetite["crit_relax"]   # replatform if crit >= rmin
    smax = d.get("replatform_max_servers", 6)
    alternatives: list[str] = []

    # ---- decision cascade (first match wins) ----------------------------
    if servers == 0 and not paas:
        disp, conf = "Retire", "high"
        rationale = ["No servers map to this application in the inventory — it is either "
                     "already decommissioned, mis-recorded, or a candidate to retire."]
        alternatives = ["Retain (if it is a SaaS/managed service tracked as an app)"]
    elif retire_marker:
        disp, conf = "Retire", "medium"
        rationale = [f"Name/notes flag it as retirable (matched \"{retire_marker}\") — "
                     f"confirm with the business owner before the wave plan locks."]
        alternatives = ["Rehost for an interim period, then retire post-cutover"]
    elif repurchase:
        disp, conf = "Repurchase", "low"
        rationale = [f"\"{repurchase[0]}\" is a commodity capability — {repurchase[1]} is "
                     f"usually cheaper than migrating. Business validation required."]
        alternatives = ["Rehost as-is if a SaaS move is out of scope this programme"]
    elif container and crit >= rmin:
        disp, conf = "Replatform", "medium"
        rationale = [f"Stack is container-ready (matched \"{container}\") and criticality "
                     f"{crit} is within the replatform appetite — target Azure Kubernetes Service."]
        alternatives = ["Rehost the VMs if the container platform isn't production-proven"]
    elif paas and not clustered and crit >= rmin and servers <= smax:
        disp, conf = "Replatform", "medium" if crit >= rmin + 1 else "low"
        rationale = [f"Single {paas[0]} database, no clustering markers, criticality {crit}, "
                     f"{servers} server(s) — a low-lift move to {paas[1]}."]
        alternatives = ["Rehost the DB VM if the cutover window is too tight"]
    elif appetite["refactor"] and crit >= 3 and users and users > 50000 and not clustered:
        disp, conf = "Refactor", "low"
        rationale = ["Aggressive appetite + large user base + no cluster constraint — a "
                     "refactor to managed/serverless services may pay back. Needs an architecture spike."]
        alternatives = ["Rehost now, refactor in a follow-on programme"]
    else:
        disp, conf = "Rehost", "high"
        rationale = ["Default path — lift-and-shift to IaaS VMs, preserving the current topology."]
        if paas and clustered:
            rationale.append(f"DB stays IaaS: clustering detected (\"{clustered}\") — preserve the cluster.")
            alternatives.append("Replatform the DB to a PaaS HA tier in a later phase")
        elif paas:
            rationale.append(f"{paas[0]} could move to {paas[1]} later (criticality {crit} "
                             f"or server count kept it IaaS this programme).")
            alternatives.append(f"Replatform to {paas[1]} once tier-{crit} apps are eligible")
        if crit == 1:
            rationale.append("Tier-1 application — rehost to minimise change during the DC exit.")
        if eol:
            rationale.append(f"{eol} server(s) past OS end-of-support — rehost as-is, then "
                             f"in-place upgrade or apply ESU after the move.")

    return {
        "app_id": app.get("app_id"),
        "app_name": name,
        "disposition": disp,
        "confidence": conf,
        "rationale": rationale,
        "alternatives": alternatives,
        "signals": signals,
        "needs_human_decision": conf == "low" or disp in ("Repurchase", "Refactor", "Retire"),
    }


def score_dispositions(applications: list[dict], server_rollup: dict | None = None,
                       cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    rollup = server_rollup or {}
    scored = [score_one(a, rollup.get(a.get("app_id")), cfg) for a in applications]

    counts: dict[str, int] = {}
    for s in scored:
        counts[s["disposition"]] = counts.get(s["disposition"], 0) + 1

    return {
        "dispositions": scored,
        "summary": {
            "applications": len(scored),
            "by_disposition": dict(sorted(counts.items())),
            "needs_human_decision": [s["app_id"] for s in scored if s["needs_human_decision"]],
            "low_confidence": sum(1 for s in scored if s["confidence"] == "low"),
        },
        "assumptions": [
            f"Appetite: {cfg['disposition'].get('appetite')} "
            f"(replatform only criticality {cfg['disposition'].get('replatform_min_criticality')}+ "
            f"apps, <= {cfg['disposition'].get('replatform_max_servers')} servers, no clustering).",
            "6R candidate is rule-derived from the inventory — it is an input to the "
            "architecture board, not a decision. Repurchase / Refactor / Retire always "
            "need business sign-off.",
            "Refactor is " + ("enabled" if cfg["disposition"].get("allow_refactor")
                              or cfg["disposition"].get("appetite") == "aggressive"
                              else "off (no refactoring this programme)") + ".",
        ],
        "config": {"source": cfg.get("_source"), "disposition": cfg["disposition"]},
    }
