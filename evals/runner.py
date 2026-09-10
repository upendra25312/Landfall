"""
Landfall eval harness (PRD E7.1 / E7.2). Offline — no Azure, no live model.

  python evals/runner.py            # run all, print the scorecard, write SCORECARD.md
  python evals/runner.py --quiet    # scorecard only

Exit code 0 iff the golden-SQL exact-match rate >= GOLDEN_GATE (0.95) and every
full-estimate scenario passes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "src", "api"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools import _safe_select                       # noqa: E402
from sample_db import build_sqlite, run_tsql          # noqa: E402
import pipeline as P                                  # noqa: E402
from faults import run_faults                          # noqa: E402
from adversarial import run_adversarial                 # noqa: E402
from output_guard import check_message, sourced_from_package  # noqa: E402

GOLDEN_GATE = 0.95


def _norm(rows):
    out = []
    for r in rows:
        out.append([round(v, 2) if isinstance(v, float) else v for v in r])
    return out


def run_golden(verbose=True):
    data = json.load(open(os.path.join(HERE, "golden_sql.json"), encoding="utf-8"))
    conn = build_sqlite()
    results = []
    for c in data["cases"]:
        rec = {"id": c["id"], "q": c["q"], "guard_ok": False, "match": False, "error": None}
        try:
            _safe_select(c["sql"])
            rec["guard_ok"] = True
        except Exception as exc:                      # noqa: BLE001
            rec["error"] = f"guard rejected: {exc}"
        if rec["guard_ok"]:
            try:
                got = _norm(run_tsql(conn, c["sql"]))
                want = _norm([list(x) for x in c["expected"]])
                rec["match"] = got == want
                if not rec["match"]:
                    rec["error"] = f"got {got} want {want}"
            except Exception as exc:                  # noqa: BLE001
                rec["error"] = f"exec failed: {exc}"
        results.append(rec)
        if verbose and (not rec["match"] or not rec["guard_ok"]):
            print(f"  FAIL {rec['id']}: {rec['error']}")
    passed = sum(1 for r in results if r["match"] and r["guard_ok"])
    return {"total": len(results), "passed": passed,
            "rate": passed / len(results) if results else 0.0, "results": results}


def _slice(spec):
    servers = P.load("servers")
    if spec == "all" or not spec:
        return None
    if spec.startswith("env="):
        return [s for s in servers if s.get("env") == spec.split("=", 1)[1]]
    if spec.startswith("first="):
        return servers[: int(spec.split("=", 1)[1])]
    return None


def run_scenarios(verbose=True):
    data = json.load(open(os.path.join(HERE, "scenarios.json"), encoding="utf-8"))
    results = []
    for sc in data["scenarios"]:
        rec = {"id": sc["id"], "name": sc["name"], "checks": [], "ok": True}
        try:
            pkg = P.run(servers=_slice(sc.get("servers")),
                        overrides=sc.get("overrides"),
                        dq_confidence=sc.get("dq_confidence", "Medium"))
            pkg2 = P.run(servers=_slice(sc.get("servers")),
                         overrides=sc.get("overrides"),
                         dq_confidence=sc.get("dq_confidence", "Medium"))
            if pkg != pkg2:
                rec["checks"].append(("determinism", False, "re-run differs"))
                rec["ok"] = False
            untraced = [f["id"] for f in pkg["figures"]
                        if not any(a["figure_id"] == f["id"] and a["formula"]
                                   for a in pkg["calculation_appendix"])]
            if untraced:
                rec["checks"].append(("traceability", False, f"no formula: {untraced}"))
                rec["ok"] = False
            for key, (lo, hi) in sc["expect"].items():
                val = P.figure(pkg, key)
                ok = val is not None and lo <= val <= hi
                rec["checks"].append((key, ok, f"{val} not in [{lo}, {hi}]" if not ok else f"{val}"))
                rec["ok"] = rec["ok"] and ok
            # E7.4 — the package's own render must carry no un-sourced number
            guard = check_message(pkg.get("summary_markdown", ""), sourced_from_package(pkg))
            if not guard["ok"]:
                rec["checks"].append(("output_guard", False,
                                      f"un-sourced: {[v['claim'] for v in guard['violations']][:5]}"))
                rec["ok"] = False
        except Exception as exc:                      # noqa: BLE001
            rec["ok"] = False
            rec["checks"].append(("run", False, str(exc)))
        results.append(rec)
        if verbose:
            mark = "ok  " if rec["ok"] else "FAIL"
            print(f"  {mark} {rec['id']} {rec['name']}")
            for name, ok, detail in rec["checks"]:
                if not ok:
                    print(f"        {name}: {detail}")
    passed = sum(1 for r in results if r["ok"])
    return {"total": len(results), "passed": passed, "results": results}


def scorecard(golden, scenarios, faults=None, adversarial=None) -> str:
    g_ok = golden["rate"] >= GOLDEN_GATE
    s_ok = scenarios["passed"] == scenarios["total"]
    f_ok = faults is None or faults["passed"] == faults["total"]
    a_ok = adversarial is None or adversarial["passed"] == adversarial["total"]

    def ok(b):
        return "PASS" if b else "FAIL"

    L = ["# Landfall eval scorecard", "",
         "_Regenerated by the offline harness: `python evals/runner.py`. "
         "Committed; CI fails if it drifts._", "",
         "| Suite | Result | Gate |", "|---|---|---|",
         f"| Golden text-to-SQL (E7.1) | {golden['passed']}/{golden['total']} "
         f"({golden['rate'] * 100:.0f}%) | >={GOLDEN_GATE * 100:.0f}% -> {ok(g_ok)} |",
         f"| Full-estimate scenarios + output guard (E7.2/E7.4) | "
         f"{scenarios['passed']}/{scenarios['total']} | all pass -> {ok(s_ok)} |"]
    if faults is not None:
        L.append(f"| Fault injection (E7.3) | {faults['passed']}/{faults['total']} | "
                 f"all pass -> {ok(f_ok)} |")
    if adversarial is not None:
        L.append(f"| Adversarial guardrails (E13.3) | "
                 f"{adversarial['passed']}/{adversarial['total']} "
                 f"({len(adversarial['pending'])} pending) | all pass -> {ok(a_ok)} |")
    L += [f"| **Overall** | **{ok(g_ok and s_ok and f_ok and a_ok)}** | |", "",
          "## Golden SQL", "", "| Case | Question | Result |", "|---|---|---|"]
    for r in golden["results"]:
        L.append(f"| {r['id']} | {r['q']} | "
                 f"{'PASS' if r['match'] and r['guard_ok'] else 'FAIL - ' + (r['error'] or '')} |")
    L += ["", "## Scenarios", "", "| Scenario | Result | Checks |", "|---|---|---|"]
    for r in scenarios["results"]:
        checks = ", ".join(f"{n}={d}" for n, _ok, d in r["checks"])
        L.append(f"| {r['id']} {r['name']} | {ok(r['ok'])} | {checks} |")
    if faults is not None:
        L += ["", "## Fault injection", "", "| Tool | Bad request | Result |", "|---|---|---|"]
        for r in faults["results"]:
            L.append(f"| {r['tool']} | `{r['body']}` | "
                     f"{ok(r['ok']) + (' ' + r['detail'] if r['detail'] else '')} |")
    if adversarial is not None:
        L += ["", "## Adversarial guardrails", "",
              "| Category | Case | Result |", "|---|---|---|"]
        for r in adversarial["results"]:
            L.append(f"| {r['category']} | {r['case']} | "
                     f"{ok(r['ok']) + (' ' + r['detail'] if r['detail'] else '')} |")
        L += ["", "_Pending — needs the live model / E15.1 Microsoft Learn MCP; "
              "listed, not gated:_", ""]
        for p in adversarial["pending"]:
            L.append(f"- **{p['category']}** — {p['case']} _(needs {p['needs']})_")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    v = not args.quiet
    if v:
        print("Golden text-to-SQL (E7.1):")
    golden = run_golden(verbose=v)
    if v:
        print(f"  {golden['passed']}/{golden['total']} ({golden['rate'] * 100:.0f}%)\n")
        print("Fault injection (E7.3):")
    faults = run_faults(verbose=v)
    if v:
        print(f"  {faults['passed']}/{faults['total']}\n")
        print("Adversarial guardrails (E13.3):")
    adversarial = run_adversarial(verbose=v)
    if v:
        print(f"  {adversarial['passed']}/{adversarial['total']} "
              f"({len(adversarial['pending'])} pending)\n")
        print("Full-estimate scenarios + output guard (E7.2/E7.4):")
    scenarios = run_scenarios(verbose=v)
    if v:
        print(f"  {scenarios['passed']}/{scenarios['total']}\n")

    card = scorecard(golden, scenarios, faults, adversarial)
    with open(os.path.join(HERE, "SCORECARD.md"), "w", encoding="utf-8") as fh:
        fh.write(card)
    print(card if args.quiet else "Wrote evals/SCORECARD.md")

    ok = (golden["rate"] >= GOLDEN_GATE and scenarios["passed"] == scenarios["total"]
          and faults["passed"] == faults["total"]
          and adversarial["passed"] == adversarial["total"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
