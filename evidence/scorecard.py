"""
E10.6 — regenerate `evidence/SCORECARD.md`: the 5/5 rubric, the current score per
dimension, and a link to every piece of evidence.

    python evidence/scorecard.py

The nine dimensions and their 5/5 bars come from `audits/path-to-5x5.md` §3. Per-
dimension scores are hand-set here (they need judgement) but the numbers that back
the "done" dimensions are pulled live from the other evidence artefacts, so a
regression there shows up in the scorecard. `main()` also snapshots the eval
scorecard into `evidence/evals/history/` (E10.3).
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "src", "api"),
                os.path.join(ROOT, "evidence", "backtest"),
                os.path.join(ROOT, "evidence", "broken-dumps")]


def _live() -> dict:
    """Pull the current numbers from the finished evidence artefacts."""
    out: dict = {}
    try:
        from backtest import run as _bt
        r = _bt()
        out["backtest"] = {
            "estates": r["corpus_size"] if "corpus_size" in r else len(r["estates"]),
            "max_spread": max(e["spread_pct"] for e in r["estates"]),
            "pass": r["all_within_tolerance"], "tol": r["tolerance_pct"],
        }
    except Exception as exc:                       # noqa: BLE001
        out["backtest"] = {"error": str(exc)}
    try:
        from check import run as _dumps
        r = _dumps()
        out["broken_dumps"] = {"files": r["corpus_size"], "pass": r["all_handled"]}
    except Exception as exc:                       # noqa: BLE001
        out["broken_dumps"] = {"error": str(exc)}
    out["evals"] = _parse_eval_scorecard()
    return out


def _parse_eval_scorecard() -> dict:
    path = os.path.join(ROOT, "evals", "SCORECARD.md")
    try:
        txt = open(path, encoding="utf-8").read()
    except OSError:
        return {"error": "evals/SCORECARD.md not found"}
    def _grab(label):
        m = re.search(rf"\|\s*{re.escape(label)}[^|]*\|\s*([^|]+?)\s*\|", txt)
        return m.group(1).strip() if m else "?"
    return {
        "golden_sql": _grab("Golden text-to-SQL"),
        "scenarios": _grab("Full-estimate scenarios"),
        "faults": _grab("Fault injection"),
        "overall": "PASS" if "**Overall** | **PASS**" in txt else "?",
    }


def rubric(live: dict) -> list[dict]:
    bt = live.get("backtest", {})
    bd = live.get("broken_dumps", {})
    ev = live.get("evals", {})
    bt_ok = bt.get("pass") and not bt.get("error")
    bd_ok = bd.get("pass") and not bd.get("error")
    ev_ok = ev.get("overall") == "PASS"

    return [
        {"dim": "Correctness", "score": 5.0 if bt_ok else 3.0,
         "bar": "Portfolio totals agree with independent methods within ±15%; variances "
                "explained; re-run identical.",
         "basis": (f"3 synthetic estates × 3 pricing methods converge at "
                   f"≤{bt.get('max_spread', '?')}% spread (bar ±{bt.get('tol', 15)}%); "
                   f"deterministic; per-estate variance analysis."
                   if bt_ok else f"back-test not passing: {bt}"),
         "evidence": [("back-test", "backtest/RESULTS.md"),
                      ("harness", "backtest/backtest.py"),
                      ("live POE cross-check", "../src/api/lz/functions.py")],
         "gap": None if bt_ok else "make the back-test pass"},

        {"dim": "Defensibility", "score": 4.0,
         "bar": "Any figure → source rows + transform + assumptions + confidence, in the "
                "delivered doc.",
         "basis": "Every figure carries an F* id + a calculation appendix (formula, inputs, "
                  "assumptions applied, confidence); the assumptions/exclusions/data-gaps "
                  "register is generated across the run (E5.2 / E5.3).",
         "evidence": [("assemble", "../src/api/deliverable/assemble.py"),
                      ("export", "../src/api/deliverable/export.py"),
                      ("tests", "../tests/test_deliverable.py")],
         "gap": "architect review board formally confirms 10 random figures are each "
                "traceable using only the delivered document."},

        {"dim": "Completeness", "score": 4.0,
         "bar": "All 8 proposal sections present and data-driven; architect board signs "
                "\"edit, not author\".",
         "basis": "assemble_estimate emits all 8 sections, each rendered from tool output "
                  "(current state, landing zone, disposition, waves, run-rate cost, effort, "
                  "assumptions register, next steps); the deck + workbook + doc all derive "
                  "from the same package.",
         "evidence": [("sections", "../src/api/deliverable/assemble.py"),
                      ("deliverable tests", "../tests/test_deliverable.py")],
         "gap": "architect review-board sign-off that the package needs editing, not "
                "authoring, on a real estate."},

        {"dim": "Robustness", "score": 5.0 if bd_ok else 3.0,
         "bar": "Broken-dump corpus (6+): each yields a valid outcome + a DQ report naming "
                "every defect — never a silent partial load.",
         "basis": (f"{bd.get('files', '?')}-file corpus; every file handled per E1.4 "
                   f"(unrecognised / rejected / degraded-with-the-gap-named)."
                   if bd_ok else f"corpus not clean: {bd}"),
         "evidence": [("corpus", "broken-dumps/RESULTS.md"),
                      ("dumps", "broken-dumps/dumps/"),
                      ("contract", "broken-dumps/EXPECTED.json")],
         "gap": None if bd_ok else "make every dump handled per E1.4"},

        {"dim": "Usability", "score": 2.0,
         "bar": "3 pre-sales people, 3 estates, no engineer, median < 1 day, all accepted.",
         "basis": "The no-code path exists end-to-end — engagements home, upload panel, "
                  "\"start analysis\", embedded chat + prompt cards, in-page export, "
                  "history versions (E11.6 / E11.7 / E11.8). The timed trial kit is ready "
                  "(evidence/trials/protocol.md Trial B + results-template.md + 3 distinct "
                  "estates from the back-test generator) but the trial has not been run "
                  "with real pre-sales users.",
         "evidence": [("dashboard", "../src/web/dashboard.html"),
                      ("operating SOP", "../docs/operating-sop.html"),
                      ("trial kit", "trials/protocol.md")],
         "gap": "run the timed usability trial (3 pre-sales × 3 fresh estates + an "
                "architect reviewer, protocol.md Trial B); record in evidence/trials/."},

        {"dim": "Understandability", "score": 3.0,
         "bar": "3 new consultants, 60 min with the docs, then succeed at a real task "
                "unaided.",
         "basis": "The Build half is done: docs match what's built; the D2 \"how Landfall "
                  "works\" walkthrough (docs/how-landfall-works.html v1.0 — pipeline, 12 "
                  "tools, answer contract, confidence model incl. the cost-capped-at-Low "
                  "rule, DRAFT boundary) + a worked example over the sample estate "
                  "reconciled to evals/pipeline.py. The comprehension task set + answer "
                  "key are apparatus-validated (evidence/trials/dry-run-2026-09-09.md). "
                  "The Proof half — the 3-person trial — is designed and ready but not run.",
         "evidence": [("how Landfall works (D2)", "../docs/how-landfall-works.html"),
                      ("operating SOP", "../docs/operating-sop.html"),
                      ("comprehension tasks + key", "trials/comprehension-answer-key.md"),
                      ("apparatus dry run", "trials/dry-run-2026-09-09.md")],
         "gap": "run the 60-minute comprehension test with 3 consultants new to Landfall "
                "(protocol.md Trial A); record in evidence/trials/."},

        {"dim": "Operability", "score": 3.75,
         "bar": "CI `azd up → smoke → azd down` on Linux + Windows every PR; chaos drill "
                "degrades cleanly.",
         "basis": "Deploy hooks are self-contained (no azd-on-PATH, SQL grant via Python — "
                  "E9.1); every PDCA cycle deploys api/web to the live rg-landfall and "
                  "verifies. E9.2: `scripts/smoke.py` (8 checks) passes green against the "
                  "live deployment (evidence/ops/smoke-live.json), unit-tested; the "
                  "`.github/workflows/clean-machine.yml` matrix (`azd up→smoke→down` on "
                  "Linux + Windows) is written but DORMANT until the OIDC secrets are added "
                  "— not yet proven green in CI. E9.3: `DEPLOYMENT_TIER=prod` — one Bicep "
                  "switch moves off every Free tier (Search basic + SLA, SQL without the "
                  "free-limit cap, ZRS storage, warm web app, 90-day retention), cost delta "
                  "documented in DEPLOY.md; `az bicep build` compiles both branches. No "
                  "observability dashboard, no logged chaos drill.",
         "evidence": [("smoke test", "../scripts/smoke.py"),
                      ("smoke run (live)", "ops/smoke-live.json"),
                      ("clean-machine CI", "../.github/workflows/clean-machine.yml"),
                      ("tier switch + cost delta", "../DEPLOY.md"),
                      ("tier tests", "../tests/test_infra_tier.py")],
         "gap": "arm + green the clean-machine CI on both OSes (one-time secret add); E9.4 "
                "answer-quality observability; E9.5 export-before-teardown; a chaos drill "
                "logged to evidence/chaos/."},

        {"dim": "Security", "score": 3.5,
         "bar": "External pen test passes; isolation test passes; data-handling statement "
                "signed.",
         "basis": "Function EasyAuth on (anon → 401); SQL Row-Level Security fail-closed by "
                  "SESSION_CONTEXT; SQL allow-list guard + statement timeout; no client SQL "
                  "in logs; per-engagement access control (visibility + audit trail); chat "
                  "threads bound to the caller's visibility — a leaked response id is inert "
                  "(E8.6); per-engagement isolation tests in the suite (E8.2–8.4, E11.3, "
                  "E11.10). Data-handling statement drafted.",
         "evidence": [("SQL guard", "../src/api/sqlguard.py"),
                      ("access control", "../src/api/engagement.py"),
                      ("isolation + chat-binding tests", "../tests/test_access_control.py"),
                      ("audit trail", "../src/api/audit.py"),
                      ("data-handling statement", "data-handling-statement.md")],
         "gap": "external pen test (evidence/pentest/); CISO/security-officer signature on "
                "the data-handling statement (E8.7); private endpoints + drop the all-Azure "
                "SQL firewall rule (E8.5)."},

        {"dim": "Reliability", "score": 5.0 if ev_ok else 2.0,
         "bar": "Eval CI gate: ≥95% text-to-SQL, 0 un-sourced numbers, byte-identical "
                "re-runs, 100% fail-loud.",
         "basis": (f"CI gate on every push/PR — golden SQL {ev.get('golden_sql', '?')}, "
                   f"scenarios + output guard {ev.get('scenarios', '?')}, fault injection "
                   f"{ev.get('faults', '?')}; numeric output is tool-computed and "
                   f"deterministic; SCORECARD drift fails the build."
                   if ev_ok else f"eval suite not green: {ev}"),
         "evidence": [("eval scorecard", "../evals/SCORECARD.md"),
                      ("history", "evals/history/"),
                      ("CI", "../.github/workflows/evals.yml"),
                      ("output guard", "../evals/output_guard.py")],
         "gap": None if ev_ok else "make the eval suite green"},
    ]


def _bar(score: float, width: int = 10) -> str:
    filled = round(score / 5 * width)
    return "█" * filled + "░" * (width - filled)


def build() -> dict:
    live = _live()
    rows = rubric(live)
    overall = round(sum(r["score"] for r in rows) / len(rows), 2)
    return {"generated": _dt.date.today().isoformat(), "overall": overall,
            "rows": rows, "live": live}


def _md(sc: dict) -> str:
    L = ["# Landfall — 5/5 scorecard",
         "",
         "_Regenerated by `python evidence/scorecard.py`; CI fails if it drifts "
         "(the committed copy is the record — see its git history for the timeline). "
         "This file **is** the production-readiness claim — hand it to anyone who asks._",
         "",
         f"## Overall: {sc['overall']} / 5",
         "",
         "> **4/5 is \"built\". 5/5 is \"built + verified + evidenced.\"** "
         "Phase 1 (engine) is complete; Phase 2 (evidence) is in progress — the "
         "dimensions below at < 5 are built but not yet independently proven.",
         "",
         "| Dimension | Score | | 5/5 bar |",
         "|---|--:|:--|---|"]
    for r in sc["rows"]:
        L.append(f"| **{r['dim']}** | {r['score']:.1f} | `{_bar(r['score'])}` | {r['bar']} |")
    L += ["", f"| **Mean** | **{sc['overall']:.2f}** | `{_bar(sc['overall'])}` | |", ""]

    L += ["## Dimension detail", ""]
    for r in sc["rows"]:
        L += [f"### {r['dim']} — {r['score']:.1f} / 5", "",
              f"**5/5 bar:** {r['bar']}", "",
              f"**Where it stands:** {r['basis']}", ""]
        L.append("**Evidence:** " + " · ".join(f"[{lbl}]({path})" for lbl, path in r["evidence"]))
        if r["gap"]:
            L += ["", f"**To reach 5/5:** {r['gap']}"]
        L.append("")

    ev = sc["live"].get("evals", {})
    bt = sc["live"].get("backtest", {})
    bd = sc["live"].get("broken_dumps", {})
    bt_s = (f"✅ {bt.get('estates')} estates, ≤{bt.get('max_spread')}% spread"
            if bt.get("pass") else f"❌ {bt}")
    bd_s = (f"✅ {bd.get('files')} files, all per E1.4" if bd.get("pass") else f"❌ {bd}")
    ev_s = (f"✅ {ev.get('overall')} — SQL {ev.get('golden_sql')}, scenarios "
            f"{ev.get('scenarios')}, faults {ev.get('faults')}"
            if ev.get("overall") == "PASS" else f"❌ {ev}")
    L += ["## Evidence pack index", "",
          "| Artefact | Tracker | Status |",
          "|---|---|---|",
          f"| [`backtest/`](backtest/) | E10.1 | {bt_s} |",
          f"| [`broken-dumps/`](broken-dumps/) | E10.2 | {bd_s} |",
          f"| [`evals/`](evals/) → [`../evals/SCORECARD.md`](../evals/SCORECARD.md) | E10.3 / E7 | {ev_s} |",
          "| `pentest/` | E10.4 / E8 | ⬜ not started |",
          "| `trials/` | E10.4 / Usability + Understandability | ⬜ not started |",
          "| `chaos/` | E10.4 / Operability | ⬜ not started |",
          "| [`data-handling-statement.md`](data-handling-statement.md) | E8.7 | 🟡 drafted — pending signature |",
          "",
          "## Residual risk",
          "",
          "- Agent determinism holds only while the output guard + eval suite are enforced — "
          "treat the guard as load-bearing.",
          "- ±15% correctness is a modelling estimate, not a discovery-grade number; the "
          "output must keep saying so.",
          "- Reference estates and prices age; without Phase 3 (quarterly re-benchmark) the "
          "score decays.",
          ""]
    return "\n".join(L)


def _snapshot_evals() -> str | None:
    src = os.path.join(ROOT, "evals", "SCORECARD.md")
    if not os.path.exists(src):
        return None
    dst_dir = os.path.join(HERE, "evals", "history")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{_dt.date.today().isoformat()}.md")
    shutil.copyfile(src, dst)
    return dst


def main() -> int:
    sc = build()
    with open(os.path.join(HERE, "SCORECARD.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_md(sc))
    snap = _snapshot_evals()
    for r in sc["rows"]:
        ascii_bar = "#" * round(r["score"] / 5 * 10) + "-" * (10 - round(r["score"] / 5 * 10))
        print(f"  {r['dim']:20s} {r['score']:.1f}/5  {ascii_bar}")
    print(f"\n  OVERALL {sc['overall']}/5")
    if snap:
        print(f"  eval snapshot -> {os.path.relpath(snap, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
