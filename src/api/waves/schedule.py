"""
build_schedule (PRD E4.3) — turn the wave plan into a dated schedule + critical path.

    sched = build_schedule(wave_plan, cfg, start_date="2026-01-05")

Deterministic. Each wave's execution duration is servers / throughput (weeks),
floored at `min_wave_weeks`, with a prep lead-in and a soak tail. Waves run
sequentially by default; `parallel_waves > 1` runs that many wave execution
windows at once (each wave takes the earliest free lane). Blackout windows push a
wave's prep start past the window. The **critical path** is the ordered chain of
waves whose finish drives the programme end date — for a sequential plan that is
every wave; with parallel lanes it is the lane that finishes last, with the
platform wave prepended because every spoke depends on it.

Pure — `datetime.date` only, no calendar library, no Azure.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from cost.config import load_config

_DEF = {
    "throughput_servers_per_week": 12,
    "wave_prep_weeks": 2,
    "wave_soak_weeks": 1,
    "min_wave_weeks": 2,
    "gap_weeks_between_waves": 1,
    "parallel_waves": 1,
    "mobilisation_weeks": 3,
    "programme_hypercare_weeks": 4,
    "blackout_windows": [],          # [{"name": "...", "start": "2026-12-15", "end": "2027-01-05"}]
    "default_start": None,           # ISO date; None => next Monday from the anchor
}


def _sched_cfg(cfg: dict | None) -> dict:
    c = dict(_DEF)
    for k, v in ((cfg or {}).get("schedule", {}) or {}).items():
        if not str(k).startswith("$"):
            c[k] = v
    return c


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _next_monday(anchor: date) -> date:
    return anchor + timedelta(days=(7 - anchor.weekday()) % 7 or 7)


def _weeks(d1: date, d2: date) -> float:
    return round((d2 - d1).days / 7.0, 1)


def _blackouts(sc: dict) -> list[tuple[date, date, str]]:
    out = []
    for w in sc.get("blackout_windows", []) or []:
        s, e = _d(w.get("start")), _d(w.get("end"))
        if s and e and e > s:
            out.append((s, e, w.get("name") or "blackout"))
    return sorted(out)


def _clear_blackout(start: date, span_days: int, blocks: list[tuple[date, date, str]]) -> tuple[date, list[str]]:
    """Push `start` forward so [start, start+span] clears every blackout window."""
    hit: list[str] = []
    moved = True
    while moved:
        moved = False
        for bs, be, name in blocks:
            if start < be and (start + timedelta(days=span_days)) > bs:
                start = be
                if name not in hit:
                    hit.append(name)
                moved = True
    return start, hit


def build_schedule(wave_plan: dict, cfg: dict | None = None,
                   start_date: str | None = None) -> dict:
    cfg = cfg or load_config()
    sc = _sched_cfg(cfg)
    waves = list((wave_plan or {}).get("waves", []) or [])

    anchor = _d(start_date) or _d(sc.get("default_start")) or date.today()
    start = anchor if (start_date or sc.get("default_start")) else _next_monday(anchor)

    tput = max(1.0, float(sc.get("throughput_servers_per_week", 12) or 12))
    prep_w = int(sc.get("wave_prep_weeks", 2) or 0)
    soak_w = int(sc.get("wave_soak_weeks", 1) or 0)
    min_w = int(sc.get("min_wave_weeks", 2) or 1)
    gap_w = int(sc.get("gap_weeks_between_waves", 1) or 0)
    lanes_n = max(1, int(sc.get("parallel_waves", 1) or 1))
    mob_w = int(sc.get("mobilisation_weeks", 3) or 0)
    hyper_w = int(sc.get("programme_hypercare_weeks", 4) or 0)
    blocks = _blackouts(sc)

    mob = {"start": start.isoformat(),
           "end": (start + timedelta(weeks=mob_w)).isoformat(),
           "weeks": mob_w,
           "note": "mobilisation, discovery finalisation, landing-zone build kickoff"}
    wave_ready = start + timedelta(weeks=mob_w)

    lanes = [wave_ready] * lanes_n          # each lane free-at date
    rows: list[dict] = []
    for w in waves:
        servers = int(w.get("server_count") or 0)
        exec_weeks = max(min_w, math.ceil(servers / tput)) if servers else min_w
        lane = min(range(lanes_n), key=lambda i: (lanes[i], i))
        earliest = max(wave_ready, lanes[lane])
        prep_start, hit = _clear_blackout(earliest, (prep_w + exec_weeks + soak_w) * 7, blocks)
        exec_start = prep_start + timedelta(weeks=prep_w)
        exec_end = exec_start + timedelta(weeks=exec_weeks)
        soak_end = exec_end + timedelta(weeks=soak_w)
        lanes[lane] = exec_end + timedelta(weeks=gap_w)
        rows.append({
            "wave": w.get("wave"),
            "kind": w.get("kind"),
            "servers": servers,
            "apps": w.get("app_count"),
            "lane": lane,
            "prep_start": prep_start.isoformat(),
            "exec_start": exec_start.isoformat(),
            "go_live": exec_end.isoformat(),
            "soak_end": soak_end.isoformat(),
            "prep_weeks": prep_w,
            "exec_weeks": exec_weeks,
            "soak_weeks": soak_w,
            "duration_weeks": prep_w + exec_weeks + soak_w,
            "throughput_basis": (f"{servers} servers ÷ {int(tput)}/wk = {math.ceil(servers / tput)} wk"
                                 f"{' (floored at %d)' % min_w if servers and math.ceil(servers / tput) < min_w else ''}"
                                 if servers else f"no server count — {min_w} wk minimum"),
            "blackout_shift": hit,
        })

    last_soak = max((_d(r["soak_end"]) for r in rows), default=wave_ready)
    end = last_soak + timedelta(weeks=hyper_w)

    # ---- critical path -------------------------------------------------
    crit = _critical_path(rows)

    milestones = [{"date": start.isoformat(), "label": "Programme start / mobilisation"}]
    milestones.append({"date": wave_ready.isoformat(), "label": "Landing zone ready — waves begin"})
    for r in rows:
        milestones.append({"date": r["go_live"],
                           "label": f"Wave {r['wave']} ({r['kind']}) go-live — {r['servers']} servers"})
    milestones.append({"date": end.isoformat(), "label": "Programme complete (hypercare closed)"})
    milestones.sort(key=lambda m: m["date"])

    assumptions = [
        f"Migration throughput {int(tput)} servers/week/wave; each wave carries a "
        f"{prep_w}-week prep lead-in and a {soak_w}-week soak, floored at {min_w} weeks of execution.",
        f"{lanes_n} wave{'s' if lanes_n > 1 else ''} run in parallel; "
        f"{gap_w}-week gap between consecutive waves on a lane.",
        f"{mob_w}-week mobilisation before the first wave (landing-zone build overlaps it); "
        f"{hyper_w}-week programme hypercare after the last wave.",
        "Calendar weeks — no holiday calendar beyond the configured blackout windows; "
        "wave dates shift as a block if a window is hit.",
        "Dates are indicative for planning; the wave runbook sets the actual cutover date "
        "within each window.",
    ]
    if blocks:
        assumptions.append("Blackout windows: "
                           + "; ".join(f"{n} ({s}…{e})" for s, e, n in blocks))

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_weeks": _weeks(start, end),
        "wave_execution_start": wave_ready.isoformat(),
        "mobilisation": mob,
        "waves": rows,
        "critical_path": crit,
        "milestones": milestones,
        "parallel_waves": lanes_n,
        "assumptions": assumptions,
        "config": {"source": cfg.get("_source"), "schedule": sc},
    }


def _critical_path(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    # the lane that finishes last drives the end date
    by_lane: dict[int, list[dict]] = {}
    for r in rows:
        by_lane.setdefault(r["lane"], []).append(r)
    crit_lane = max(by_lane, key=lambda ln: max(x["soak_end"] for x in by_lane[ln]))
    chain = sorted(by_lane[crit_lane], key=lambda r: r["exec_start"])

    out: list[dict] = []
    platform = next((r for r in rows if r["kind"] == "platform"), None)
    if platform and platform not in chain:
        out.append({"wave": platform["wave"], "kind": "platform",
                    "go_live": platform["go_live"],
                    "reason": "platform / shared-services wave — every spoke depends on it"})
    for i, r in enumerate(chain):
        if i == 0 and r["kind"] == "platform":
            reason = "platform / shared-services wave — every spoke depends on it"
        elif r["kind"] == "pilot":
            reason = "pilot wave — proves the migration factory before scale-out"
        elif r["kind"] == "regulated":
            reason = "regulated wave — audit-witnessed, cannot overlap other cutovers"
        else:
            reason = "sequential on the critical lane — its finish moves the end date"
        out.append({"wave": r["wave"], "kind": r["kind"], "go_live": r["go_live"], "reason": reason})
    return out
