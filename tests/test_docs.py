"""D2 / E10.4 — the "How Landfall works" walkthrough + the trials kit are present
and internally consistent (the worked-example numbers match evals/pipeline.py).
"""
import os
import re
import sys

from conftest import ROOT

DOCS = os.path.join(ROOT, "docs")
TRIALS = os.path.join(ROOT, "evidence", "trials")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------- D2 doc

def test_how_landfall_works_exists_and_has_the_required_sections():
    html = _read(DOCS, "how-landfall-works.html")
    for anchor in ("what", "pipeline", "tools", "contract", "confidence", "draft", "worked"):
        assert f'id="{anchor}"' in html, f"missing section #{anchor}"
    # the load-bearing concepts a new consultant must leave with
    for phrase in ("agent orchestrates", "DRAFT", "confidence", "calculation appendix",
                   "capped at Low", "Row-Level Security"):
        assert phrase in html, f"missing concept: {phrase}"


def test_how_landfall_works_is_linked_from_the_docs_index():
    assert "how-landfall-works.html" in _read(DOCS, "index.html")


def test_worked_example_numbers_match_the_pipeline():
    """The doc quotes $113,911/mo etc. — regenerate SC1 and check they still hold,
    so a pricing-engine change can't silently make the walkthrough wrong."""
    sys.path[:0] = [os.path.join(ROOT, "evals"), os.path.join(ROOT, "src", "api")]
    import pipeline as P

    pkg = P.run()
    figs = {f["key"]: round(f["value"]) for f in pkg["figures"]
            if isinstance(f.get("value"), (int, float))}
    html = _read(DOCS, "how-landfall-works.html")

    def _quoted(n):
        return f"{n:,}" in html or f"${n:,}" in html

    assert _quoted(figs["run_rate_monthly"]), figs["run_rate_monthly"]
    assert _quoted(figs["compute_monthly"]) and _quoted(figs["storage_monthly"])
    assert _quoted(figs["run_rate_annual"])
    # server / vcpu counts
    assert "250 servers" in html and "1,940 current vCPU" in html


# --------------------------------------------------------------- E13.12 learning path

_TOP_DIRS = ("src/", "infra/", "evals/", "scripts/", "evidence/", "prd/",
             "docs/", "tests/", ".claude/", ".github/")


def test_learning_path_exists_and_is_linked():
    assert os.path.exists(os.path.join(DOCS, "learning-path.md"))
    assert "learning-path.md" in _read(DOCS, "index.html")


def test_learning_path_covers_the_three_goals_and_the_profiles_matrix():
    md = _read(DOCS, "learning-path.md")
    assert "Azure AI Foundry" in md
    assert "Azure Container Apps" in md
    assert "Enterprise-scale design" in md
    # the folded-in brief items (E14.6 + the lab->enterprise matrix)
    assert "system of record" in md and "projection" in md
    assert "Deployment profiles" in md
    for col in ("Lab", "Customer engagement", "Enterprise"):
        assert col in md


def test_learning_path_repo_references_resolve():
    """Every `backticked` repo path and every ../ markdown link in the learning
    path points at a file that exists, so the doc can't rot silently."""
    md = _read(DOCS, "learning-path.md")
    missing = []

    for tok in re.findall(r"`([^`]+)`", md):
        cand = tok.split()[0].strip("().,:;")          # first token, no trailing punct
        if cand.startswith(_TOP_DIRS) and "<" not in cand and "*" not in cand:
            if not os.path.exists(os.path.join(ROOT, cand)):
                missing.append(cand)

    for target in re.findall(r"\]\((\.\./[^)]+)\)", md):
        target = target.split("#")[0]
        if not os.path.exists(os.path.normpath(os.path.join(DOCS, target))):
            missing.append(target)

    assert not missing, f"broken references in learning-path.md: {sorted(set(missing))}"


# --------------------------------------------------------------- trials kit

def test_trials_kit_is_complete():
    for f in ("README.md", "protocol.md", "comprehension-answer-key.md",
              "results-template.md", "dry-run-2026-09-09.md"):
        assert os.path.exists(os.path.join(TRIALS, f)), f"missing evidence/trials/{f}"


def test_protocol_covers_both_trials_with_acceptance_bars():
    p = _read(TRIALS, "protocol.md")
    assert "Trial A — Comprehension" in p and "Trial B — Usability" in p
    assert "Acceptance" in p
    assert "median" in p and "< 1 day" in p            # the usability bar
    assert "unaided" in p                              # the comprehension bar


def test_answer_key_has_three_tasks_and_a_scoring_sheet():
    k = _read(TRIALS, "comprehension-answer-key.md")
    assert k.count("## Task ") == 3
    assert "Scoring sheet" in k
    # the trap the dry run caught: cost confidence is Low, not Medium
    assert "Low" in k and "not one who says \"Medium\"" in k


def test_scorecard_cites_the_new_evidence():
    sys.path.insert(0, os.path.join(ROOT, "evidence"))
    import scorecard

    rows = {r["dim"]: r for r in scorecard.build()["rows"]}
    assert rows["Understandability"]["score"] == 3.0
    paths = [p for _l, p in rows["Understandability"]["evidence"]]
    assert "../docs/how-landfall-works.html" in paths
    assert any("trials/" in p for p in paths)
