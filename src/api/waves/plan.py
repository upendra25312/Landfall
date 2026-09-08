"""
plan_waves (PRD E4.1) — deterministic wave / move-group engine.

    result = plan_waves(applications, servers, dependencies, cfg)

1. Build the server dependency graph (drop stale / low-confidence edges).
2. Roll it up to application-to-application edges.
3. Cluster into affinity move-groups (connected components of the app graph).
4. Score each group's migration risk and order the groups low-risk-first into
   waves, capped by servers/apps per wave, regulated groups last, with a pilot
   wave (wave 0) for the lowest-risk group + retire candidates.
5. Emit entry/exit criteria and cross-wave blocking dependencies.

Pure — no Azure, no external graph library.
"""
from __future__ import annotations

from datetime import date

from cost.config import load_config
from .disposition import score_dispositions

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def _parse_date(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class _DSU:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def plan_waves(applications: list[dict], servers: list[dict],
               dependencies: list[dict], cfg: dict | None = None,
               dispositions: list[dict] | None = None) -> dict:
    cfg = cfg or load_config()
    w = cfg["waves"]
    reg_scopes = {s.upper() for s in w.get("regulated_scopes_last", [])}
    commodity_proto = {p.upper() for p in w.get("commodity_protocols", [])}
    commodity_ports = {int(p) for p in w.get("commodity_ports", [])}
    infra_markers = [m.lower() for m in w.get("infra_app_markers", [])]

    apps = {a.get("app_id"): a for a in applications if a.get("app_id")}
    infra_apps = {aid for aid, a in apps.items()
                  if any(m in (str(a.get("app_name", "")) + " " + str(a.get("tech_stack", ""))).lower()
                         for m in infra_markers)}
    srv_app = {s.get("server_id"): s.get("app_id") for s in servers}
    srv = {s.get("server_id"): s for s in servers}

    # --- per-app server rollup (for disposition + risk) --------------------
    rollup: dict[str, dict] = {aid: {"servers": 0, "eol_servers": 0, "envs": set()} for aid in apps}
    for s in servers:
        aid = s.get("app_id")
        if aid not in rollup:
            continue
        rollup[aid]["servers"] += 1
        rollup[aid]["envs"].add((s.get("env") or "").lower())
        if _parse_date(s.get("os_eol_date")) and _parse_date(s.get("os_eol_date")) < date.today():
            rollup[aid]["eol_servers"] += 1
    for r in rollup.values():
        r["envs"] = sorted(x for x in r["envs"] if x)

    disp_list = dispositions or score_dispositions(
        applications, {k: v for k, v in rollup.items()}, cfg)["dispositions"]
    disp_by_app = {d["app_id"]: d for d in disp_list}

    # --- dependency graph: stale / low-confidence filter ------------------
    min_rank = _CONF_RANK.get(w.get("min_edge_confidence", "low"), 0)
    window_end = _parse_date(w.get("observation_window_end")) or _max_last_seen(dependencies)
    stale_days = int(w.get("stale_after_days", 21))

    app_edges: dict[tuple, dict] = {}
    soft_edges: dict[tuple, str] = {}          # dropped edges, app-rolled — reported as soft blocks
    stale_excluded = 0
    lowconf_excluded = 0
    commodity_excluded = 0
    for e in dependencies:
        s1, s2 = e.get("src_id"), e.get("dst_id")
        a1, a2 = srv_app.get(s1), srv_app.get(s2)
        if a1 == a2 and a1:
            continue
        if (s1 in srv or s2 in srv) and (not a1 or not a2):
            # one endpoint is an unmapped (shared-infrastructure) server -> platform dep
            commodity_excluded += 1
            continue
        if not a1 or not a2:
            continue
        proto = (e.get("protocol") or "").upper()
        port = _int(e.get("port"), -1)
        if a1 in infra_apps or a2 in infra_apps or proto in commodity_proto or port in commodity_ports:
            # platform / commodity dependency — real, but it doesn't bind two apps into
            # the same wave (everything depends on the platform, which moves first).
            commodity_excluded += 1
            if a1 not in infra_apps and a2 not in infra_apps:
                soft_edges.setdefault(tuple(sorted((a1, a2))), f"platform/commodity ({proto or port})")
            continue
        if _CONF_RANK.get((e.get("confidence") or "low").lower(), 0) < min_rank:
            lowconf_excluded += 1
            soft_edges.setdefault(tuple(sorted((a1, a2))), "below-confidence-threshold")
            continue
        seen = _parse_date(e.get("last_seen"))
        if window_end and seen and (window_end - seen).days > stale_days:
            stale_excluded += 1
            soft_edges.setdefault(tuple(sorted((a1, a2))), "stale flow (may be dead)")
            continue
        key = tuple(sorted((a1, a2)))
        rec = app_edges.setdefault(key, {"flows": 0, "confidence": "low", "count": 0})
        rec["flows"] += _int(e.get("flows_30d"))
        rec["count"] += 1
        if _CONF_RANK.get((e.get("confidence") or "low").lower(), 0) > _CONF_RANK[rec["confidence"]]:
            rec["confidence"] = (e.get("confidence") or "low").lower()

    # --- affinity move-groups = connected components --------------------
    dsu = _DSU(apps)
    for (a1, a2) in app_edges:
        dsu.union(a1, a2)
    groups: dict[str, list[str]] = {}
    for aid in apps:
        groups.setdefault(dsu.find(aid), []).append(aid)

    move_groups = []
    for i, (root, members) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
        members.sort()
        internal = [k for k in app_edges if k[0] in members and k[1] in members]
        gservers = sum(rollup[m]["servers"] for m in members)
        is_platform = bool(set(members) & infra_apps)
        move_groups.append({
            "group_id": f"mg-{i:02d}",
            "apps": members,
            "app_names": [apps[m].get("app_name") for m in members],
            "servers": gservers,
            "internal_edges": len(internal),
            "platform": is_platform,
            "driver": ("platform / shared-infrastructure services — migrate first"
                       if is_platform else
                       "chatty app-to-app dependencies — must move together"
                       if len(internal) else "no strong cross-app dependency — standalone"),
        })

    # --- risk score per group -----------------------------------------
    gq = {g["group_id"]: g for g in move_groups}
    for g in move_groups:
        g["risk_score"], g["risk_factors"], g["regulated"] = _risk(g, apps, rollup, disp_by_app, reg_scopes, w)

    # order: platform first, regulated last, then ascending risk, then smaller first
    ordered = sorted(move_groups,
                     key=lambda g: (not g.get("platform"), g["regulated"], g["risk_score"], g["servers"]))
    platform_groups = [g for g in ordered if g.get("platform")]
    app_groups = [g for g in ordered if not g.get("platform")]

    # --- pack into waves ------------------------------------------
    max_srv = int(w.get("max_servers_per_wave", 40))
    max_apps = int(w.get("max_apps_per_wave", 6))
    retire_apps = [d["app_id"] for d in disp_list if d["disposition"] == "Retire"]

    waves: list[dict] = []
    cur = {"groups": [], "apps": [], "servers": 0}

    def _flush(kind):
        if not cur["groups"] and kind != "pilot":
            return
        waves.append(_wave_record(len(waves), kind, cur, gq, apps, disp_by_app, retire_apps, w))
        cur["groups"], cur["apps"], cur["servers"] = [], [], 0

    def _add(g):
        cur["groups"].append(g["group_id"])
        cur["apps"] += g["apps"]
        cur["servers"] += g["servers"]

    # wave 0 — platform / foundation (shared-infra apps), if any
    if platform_groups:
        for g in platform_groups:
            _add(g)
        _flush("platform")

    # next — pilot: the lowest-risk non-regulated app group + retire apps
    pilot = next((g for g in app_groups if not g["regulated"]), None)
    if pilot:
        _add(pilot)
    _flush("pilot")

    for g in app_groups:
        if pilot and g["group_id"] == pilot["group_id"]:
            continue
        over = (cur["servers"] + g["servers"] > max_srv or
                len(cur["apps"]) + len(g["apps"]) > max_apps)
        if over and cur["groups"]:
            _flush("regulated" if _all_regulated(cur, gq) else "standard")
        _add(g)
    if cur["groups"]:
        _flush("regulated" if _all_regulated(cur, gq) else "standard")

    # --- cross-wave blocking dependencies -----------------------
    # real edges only cross waves when a large move-group was split; soft (dropped)
    # edges are surfaced too — "we filtered this out, but check it before you cut".
    wave_of_app = {a: wv["wave"] for wv in waves for a in wv["apps"]}
    edge_src = ([(k, app_edges[k]["confidence"]) for k in app_edges]
                + [(k, f"unverified — {why}") for k, why in soft_edges.items()])
    for wv in waves:
        blocks = []
        for (a1, a2), conf in edge_src:
            for src, dst in ((a1, a2), (a2, a1)):
                if src in wv["apps"] and dst not in wv["apps"]:
                    dw = wave_of_app.get(dst)
                    if dw is not None and dw > wv["wave"]:
                        blocks.append({"app": src, "depends_on": dst,
                                       "in_wave": dw, "confidence": conf})
        wv["blocking_dependencies"] = _dedupe(blocks)

    return {
        "move_groups": move_groups,
        "waves": waves,
        "graph": {
            "app_nodes": len(apps),
            "app_edges": len(app_edges),
            "components": len(groups),
            "stale_edges_excluded": stale_excluded,
            "low_confidence_edges_excluded": lowconf_excluded,
            "commodity_edges_excluded": commodity_excluded,
            "platform_apps": sorted(infra_apps),
            "observation_window_end": str(window_end) if window_end else None,
        },
        "disposition_summary": _disp_counts(disp_list),
        "assumptions": [
            f"Platform / commodity dependencies (AD, DNS, NTP, monitoring — "
            f"{commodity_excluded} edges) don't bind apps into a wave; the platform "
            f"group migrates in the pilot wave and everything may depend on it.",
            f"Edges below '{w.get('min_edge_confidence')}' confidence and flows not seen "
            f"in {stale_days} days are excluded ({lowconf_excluded} + {stale_excluded} dropped) — "
            "confirm the move-groups against application SMEs.",
            f"Move-groups are connected components of the app dependency graph; groups are "
            f"ordered low-risk-first, capped at {max_srv} servers / {max_apps} apps per wave, "
            f"regulated scopes ({', '.join(sorted(reg_scopes))}) last.",
            "Non-production servers migrate ahead of production within each wave (5-day "
            "soak) — a scheduling note, not a separate wave.",
            "Wave dates come from the duration model (E4.3), not this tool; blackout "
            "windows still apply.",
        ],
        "config": {"source": cfg.get("_source"), "waves": w},
    }


# --- helpers ----------------------------------------------------------

def _max_last_seen(deps):
    ds = [_parse_date(e.get("last_seen")) for e in deps]
    ds = [d for d in ds if d]
    return max(ds) if ds else None


def _risk(group, apps, rollup, disp_by_app, reg_scopes, w):
    wt = w.get("risk_weights", {})
    crits, factors = [], []
    inet = comp = eol_ratio = change = 0.0
    regulated = False
    for aid in group["apps"]:
        a = apps[aid]
        c = _int(a.get("criticality"), 3)
        crits.append(c)
        if str(a.get("internet_facing")).strip() in ("1", "true", "True", "yes"):
            inet = 1.0
        scopes = [s.strip().upper() for s in str(a.get("compliance_scope") or "").replace(",", ";").split(";") if s.strip()]
        if scopes:
            comp = 1.0
        if any(s in reg_scopes for s in scopes):
            regulated = True
        r = rollup.get(aid, {})
        if r.get("servers"):
            eol_ratio = max(eol_ratio, r.get("eol_servers", 0) / r["servers"])
        d = disp_by_app.get(aid, {})
        if d.get("disposition") in ("Replatform", "Refactor"):
            change = max(change, 1.0)
        if d.get("confidence") == "low":
            change = max(change, 0.5)

    best_crit = min(crits) if crits else 3            # 1 = most critical = most risk
    crit_f = {1: 1.0, 2: 0.65, 3: 0.35, 4: 0.15}.get(best_crit, 0.35)
    size_f = min(1.0, group["servers"] / 50.0)
    dq_f = 1.0 if group["internal_edges"] == 0 and group["servers"] > 3 else 0.3

    score = (crit_f * wt.get("criticality", 40) + inet * wt.get("internet_facing", 12) +
             comp * wt.get("compliance", 22) + size_f * wt.get("size", 14) +
             eol_ratio * wt.get("eol_os", 6) + change * wt.get("change", 10) +
             dq_f * wt.get("data_quality", 8))

    if best_crit == 1:
        factors.append("contains a tier-1 application")
    if inet:
        factors.append("internet-facing")
    if regulated:
        factors.append("regulated compliance scope")
    elif comp:
        factors.append("in-scope for a compliance framework")
    if size_f > 0.6:
        factors.append(f"large ({group['servers']} servers)")
    if eol_ratio > 0.3:
        factors.append("significant EOL-OS estate")
    if change:
        factors.append("replatform / low-confidence disposition in the group")
    return round(score, 1), factors, regulated


def _wave_record(idx, kind, cur, gq, apps, disp_by_app, retire_apps, w):
    app_ids = list(dict.fromkeys(cur["apps"]))
    if kind == "pilot":
        app_ids = list(dict.fromkeys(app_ids + retire_apps))
    scores = [gq[g]["risk_score"] for g in cur["groups"]] or [0]
    risk = round(sum(scores) / len(scores), 1)
    band = "low" if risk < 30 else "medium" if risk < 55 else "high"
    dcounts: dict[str, int] = {}
    for aid in app_ids:
        d = disp_by_app.get(aid, {}).get("disposition", "Rehost")
        dcounts[d] = dcounts.get(d, 0) + 1
    factors = sorted({f for g in cur["groups"] for f in gq[g]["risk_factors"]})

    entry = ["Landing-zone spoke for this wave's zone is live and security-reviewed",
             "Wave runbook rehearsed in non-production",
             "Rollback-to-on-prem validated for every app in the wave"]
    exit_ = ["All wave servers migrated; non-prod stable 5 business days, prod 5 business days",
             "Application owner sign-off; monitoring + backup confirmed in Azure",
             "Source VMs powered off (not decommissioned until the wave clears hypercare)"]
    notes = []
    if kind == "platform":
        notes.append("Platform / foundation wave — shared infrastructure services (AD, DNS, "
                     "monitoring, backup, file). Everything else depends on this; migrate first.")
        entry.insert(0, "Hub landing zone live: connectivity, identity subscription, "
                     "Azure Firewall, Private DNS")
        exit_.insert(0, "Replica DCs promoted and healthy; DNS + monitoring cut over; "
                     "hybrid identity validated")
    if kind == "pilot":
        notes.append("Pilot wave — prove the factory: lowest-risk group first, retire "
                     "candidates decommissioned here.")
        entry.insert(0, "Migration tooling (Azure Migrate / ASR) configured and tested end-to-end")
    if kind == "regulated" or "regulated compliance scope" in factors:
        exit_.insert(1, "QSA-witnessed / auditor-witnessed test passed for regulated apps")
        notes.append("Regulated wave — schedule outside audit windows; security sign-off gate.")
    if band == "high":
        notes.append("High-risk wave — extend hypercare, add a go/no-go checkpoint mid-wave.")

    return {
        "wave": idx,
        "kind": kind,
        "groups": list(cur["groups"]),
        "apps": app_ids,
        "app_count": len(app_ids),
        "server_count": cur["servers"],
        "risk_score": risk,
        "risk_band": band,
        "risk_factors": factors,
        "dispositions": dict(sorted(dcounts.items())),
        "entry_criteria": entry,
        "exit_criteria": exit_,
        "notes": notes,
    }


def _all_regulated(cur, gq):
    return bool(cur["groups"]) and all(gq[g]["regulated"] for g in cur["groups"])


def _dedupe(rows):
    seen, out = set(), []
    for r in rows:
        k = (r["app"], r["depends_on"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _disp_counts(disp_list):
    c: dict[str, int] = {}
    for d in disp_list:
        c[d["disposition"]] = c.get(d["disposition"], 0) + 1
    return dict(sorted(c.items()))
