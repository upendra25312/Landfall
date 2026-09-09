"""
Data-quality report over one or more NormResults (PRD E1.3).

    report = build_report([norm_servers, norm_apps], existing_keys={...})
    md = render_markdown(report)

The report is written to `answers/_ingest/` so the pre-sales team can (a) see what
loaded, (b) see what is missing that the estimate needs, and (c) send the client a
concrete "we need X, Y, Z to firm this up" list. Pure logic — no Azure imports.
"""
from __future__ import annotations

from .core import NormResult

# columns the estimate genuinely depends on, per table
CRITICAL = {
    "servers": ["vcpu", "ram_gb", "os_name", "app_id", "cpu_peak_pct", "provisioned_disk_gb"],
    "applications": ["app_name", "criticality", "compliance_scope", "business_owner"],
    "dependencies": ["src_id", "dst_id"],
    "storage": ["server_id", "size_gb", "type"],
    "performance": ["server_id", "sample_date", "cpu_avg_pct", "mem_avg_pct"],
}
PERF_COLS = ["cpu_avg_pct", "cpu_peak_pct", "ram_avg_pct"]


def _rate(rows, col):
    if not rows:
        return 0.0
    missing = sum(1 for r in rows if r.get(col) in (None, ""))
    return round(missing / len(rows), 3)


def _dupes(rows, key):
    seen, dup = set(), set()
    for r in rows:
        v = r.get(key)
        if v in seen:
            dup.add(v)
        seen.add(v)
    return sorted(x for x in dup if x is not None)


def build_report(results: list[NormResult], existing_keys: dict | None = None) -> dict:
    existing_keys = existing_keys or {}
    tables: dict[str, dict] = {}

    # group normalised results by target table; several files can feed one table
    grouped: dict[str, list[NormResult]] = {}
    unrecognised: list[NormResult] = []
    for res in results:
        if res.table:
            grouped.setdefault(res.table, []).append(res)
        else:
            unrecognised.append(res)

    server_ids = set(existing_keys.get("servers", set()))
    app_ids = set(existing_keys.get("applications", set()))
    for r in grouped.get("servers", []):
        server_ids |= {row.get("server_id") for row in r.rows}
    for r in grouped.get("applications", []):
        app_ids |= {row.get("app_id") for row in r.rows}

    for table, reslist in grouped.items():
        rows = [row for r in reslist for row in r.rows]
        issues = [i for r in reslist for i in r.issues]
        pk = {"servers": "server_id", "applications": "app_id", "storage": "storage_id",
              "dependencies": None, "performance": None}.get(table)
        entry = {
            "profile": ", ".join(sorted({r.profile for r in reslist if r.profile})),
            "rows_in": sum(r.row_count_in for r in reslist),
            "rows_normalised": len(rows),
            "unmapped_headers": sorted({h for r in reslist for h in r.unmapped_headers}),
            "duplicate_keys": _dupes(rows, pk) if pk else [],
            "null_rate": {c: _rate(rows, c) for c in CRITICAL.get(table, [])},
            "errors": [i._asdict() for i in issues if i.level == "error"],
            "warnings": [i._asdict() for i in issues if i.level == "warning"],
        }

        if table == "servers":
            entry["no_perf_data"] = sum(
                1 for r in rows if all(r.get(c) in (None, "") for c in PERF_COLS)
            )
            entry["no_app_mapping"] = sum(1 for r in rows if not r.get("app_id"))
            entry["orphan_app_id"] = sorted(
                {r.get("app_id") for r in rows
                 if r.get("app_id") and r.get("app_id") not in app_ids}
            )
            entry["powered_off"] = sum(
                1 for r in rows if (r.get("powerstate") or "").lower() == "poweredoff"
            )
        elif table == "storage":
            entry["orphan_server_id"] = sorted(
                {r.get("server_id") for r in rows
                 if r.get("server_id") and r.get("server_id") not in server_ids}
            )
        elif table == "dependencies":
            eps = {r.get("src_id") for r in rows} | {r.get("dst_id") for r in rows}
            entry["endpoints_not_servers"] = sorted(
                {e for e in eps if e and e not in server_ids}
            )
        tables[table] = entry

    if unrecognised:
        tables["_unrecognised"] = {
            "files": [{"issues": [i._asdict() for i in r.issues]} for r in unrecognised]
        }

    return {
        "tables": tables,
        "findings": _findings(tables),
        "confidence_hint": _confidence(tables),
    }


def _findings(tables: dict) -> list[str]:
    out = []

    # a recognised file that carried no data rows — loaded nothing, say so loudly
    for name, t in tables.items():
        if name != "_unrecognised" and not t.get("rows_normalised"):
            out.append(f"The {name} file was recognised but contained no data rows — "
                       f"nothing was loaded for {name}. Re-export and re-upload.")

    # duplicate primary keys — the loader upserts, so silent last-write-wins
    for name, t in tables.items():
        if name != "_unrecognised" and t.get("duplicate_keys"):
            d = t["duplicate_keys"]
            out.append(f"{len(d)} duplicate key(s) in {name} "
                       f"({', '.join(str(x) for x in d[:5])}"
                       + (" …" if len(d) > 5 else "") + ") — the loader keeps the last row "
                       "for each; de-duplicate the source so the count is trustworthy.")

    s = tables.get("servers")
    if s:
        n = s["rows_normalised"] or 1
        for col, label in (("vcpu", "vCPU"), ("ram_gb", "RAM")):
            if s["null_rate"].get(col, 0) > 0.3:
                pct = round(100 * s["null_rate"][col])
                out.append(f"{label} is missing or unparseable on {pct}% of servers — "
                           f"compute sizing cannot run for those rows. Check the source "
                           f"column and its units (a plain number, no 'GB'/'N/A').")
        if s.get("no_perf_data"):
            pct = round(100 * s["no_perf_data"] / n)
            out.append(
                f"{s['no_perf_data']} of {n} servers ({pct}%) have no CPU/RAM utilisation "
                f"history — compute right-sizing for those will be LOW confidence. "
                f"Ask the client for a vCenter performance export (30+ days)."
            )
        if s.get("no_app_mapping"):
            pct = round(100 * s["no_app_mapping"] / n)
            out.append(
                f"{s['no_app_mapping']} servers ({pct}%) are not mapped to an application "
                f"— wave planning will group by infrastructure role only. "
                f"Ask the client for a server-to-application mapping."
            )
        if s["null_rate"].get("os_name", 0) > 0.1:
            out.append("OS is missing on >10% of servers — EOL exposure and licensing "
                       "cannot be assessed for those. Ask for an OS inventory.")
        if s.get("orphan_app_id"):
            out.append(f"{len(s['orphan_app_id'])} app_id values on servers have no row in "
                       f"applications: {', '.join(s['orphan_app_id'][:8])}"
                       + (" …" if len(s['orphan_app_id']) > 8 else "")
                       + " — upload the application portfolio.")
    if "dependencies" not in tables:
        out.append("No dependency data loaded — move groups will be inferred from the "
                   "application mapping only, not from observed network flow. "
                   "Ask the client for a dependency / netflow export if available.")
    elif tables["dependencies"].get("endpoints_not_servers"):
        ep = tables["dependencies"]["endpoints_not_servers"]
        out.append(f"{len(ep)} dependency endpoints are not known servers "
                   f"(e.g. {', '.join(str(x) for x in ep[:5])}) — external / unmodelled nodes.")
    a = tables.get("applications")
    if a and a["null_rate"].get("criticality", 0) > 0.2:
        out.append("Business criticality is missing on >20% of applications — "
                   "wave sequencing and resiliency tiers will use defaults.")
    if "_unrecognised" in tables:
        out.append(f"{len(tables['_unrecognised']['files'])} uploaded file(s) could not be "
                   f"recognised and were NOT loaded — see the errors above.")
    if not out:
        out.append("No blocking data-quality issues found. The estimate can proceed at "
                   "the stated confidence.")
    return out


def _confidence(tables: dict) -> str:
    s = tables.get("servers")
    if not s or not s["rows_normalised"]:
        return "Low"
    n = s["rows_normalised"]
    perf_gap = s.get("no_perf_data", n) / n
    app_gap = s.get("no_app_mapping", n) / n
    os_gap = s["null_rate"].get("os_name", 1.0)
    if "_unrecognised" in tables or s["errors"]:
        return "Low"
    if s["null_rate"].get("vcpu", 0) > 0.5 or s["null_rate"].get("ram_gb", 0) > 0.5:
        return "Low"                       # can't size the fleet without vCPU/RAM
    if perf_gap > 0.5 or app_gap > 0.4 or os_gap > 0.2 or "dependencies" not in tables:
        return "Medium"
    if perf_gap > 0.2 or app_gap > 0.15:
        return "Medium"
    return "High"


def render_markdown(report: dict, title: str = "Inventory data-quality report") -> str:
    L = [f"# {title}", "", f"**Overall confidence:** {report['confidence_hint']}", ""]
    L.append("## What this means for the estimate")
    for f in report["findings"]:
        L.append(f"- {f}")
    L.append("")
    L.append("## Per-table detail")
    for name, t in report["tables"].items():
        if name == "_unrecognised":
            L += ["", f"### Unrecognised files ({len(t['files'])})"]
            for f in t["files"]:
                for iss in f["issues"]:
                    L.append(f"- **{iss['level']}** {iss['where']}: {iss['message']}")
            continue
        L += ["", f"### `{name}` — profile `{t['profile']}`",
              f"- rows in file: {t['rows_in']}  ·  normalised: {t['rows_normalised']}"]
        if t["duplicate_keys"]:
            L.append(f"- **duplicate keys ({len(t['duplicate_keys'])}):** "
                     + ", ".join(str(x) for x in t["duplicate_keys"][:10]))
        if t["unmapped_headers"]:
            L.append(f"- unmapped source columns: {', '.join(t['unmapped_headers'])}")
        gaps = [f"{c} {int(r*100)}%" for c, r in t["null_rate"].items() if r > 0]
        if gaps:
            L.append(f"- missing values (critical columns): {', '.join(gaps)}")
        for extra in ("no_perf_data", "no_app_mapping", "powered_off"):
            if t.get(extra):
                L.append(f"- {extra.replace('_', ' ')}: {t[extra]}")
        for extra in ("orphan_app_id", "orphan_server_id", "endpoints_not_servers"):
            if t.get(extra):
                L.append(f"- {extra.replace('_', ' ')} ({len(t[extra])}): "
                         + ", ".join(str(x) for x in t[extra][:10]))
        for iss in t["errors"][:20]:
            L.append(f"- **error** {iss['where']}: {iss['message']}")
    L.append("")
    L.append("_Generated by the Landfall ingestion pipeline. DRAFT — for discovery "
             "scoping, not a bid._")
    return "\n".join(L)
