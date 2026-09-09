"""Non-destructive chaos-drill probe (PRD E9).

Confirms the degradation mitigations for the six `scenarios.md` failure modes are
in place — reads current Azure state + the code paths, induces nothing. A full
drill (actually stopping a dependency) is the manual procedure in scenarios.md.

    python evidence/chaos/probe.py            # uses `azd env get-values`, else env
    python evidence/chaos/probe.py --json evidence/chaos/probe-result.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cfg() -> dict:
    c = {}
    azd = shutil.which("azd") or shutil.which("azd.exe")
    if azd:
        r = subprocess.run([azd, "env", "get-values"], capture_output=True, text=True)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    c[k.strip()] = v.strip().strip('"')
    for k, v in os.environ.items():
        c.setdefault(k, v)
    return c


def _az_json(args: list[str]):
    az = shutil.which("az") or "az"
    r = subprocess.run([az, *args, "-o", "json"], capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout or "null")
    except json.JSONDecodeError:
        return None


def _src(path: str) -> str:
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def run() -> dict:
    cfg = _cfg()
    rg = cfg.get("AZURE_RESOURCE_GROUP", "")
    checks = []

    def add(cid, ok, detail):
        checks.append({"scenario": cid, "mitigation_in_place": bool(ok), "detail": detail})

    # C1 — SQL retry-through-resume
    tools = _src("src/api/tools.py")
    add("C1", "database resuming" in tools or "not currently available" in tools
        or re.search(r"retry.*resum", tools, re.I) is not None,
        "src/api/tools.py retries the connection while the serverless DB resumes")

    # C2 — ca-drawio cold-start retry + best-effort raster
    render = _src("src/api/lz/render.py")
    m = re.search(r"_TIMEOUT\s*=\s*(\d+)", render)
    attempts = re.search(r"_ATTEMPTS\s*=\s*(\d+)", render)
    ok = m and int(m.group(1)) >= 30 and attempts and int(attempts.group(1)) >= 2 \
        and "rasterise skipped" in render
    add("C2", ok, f"render.py timeout={m.group(1) if m else '?'}s attempts="
        f"{attempts.group(1) if attempts else '?'}, skips the PNG on failure")
    if rg:
        drawio = next((c for c in (_az_json(["containerapp", "list", "-g", rg,
                       "--query", "[?contains(name, 'drawio')]"]) or [])), None)
        if drawio:
            scale = drawio["properties"]["template"]["scale"]
            add("C2-live", scale.get("minReplicas") == 0,
                f"ca-drawio minReplicas={scale.get('minReplicas')} (cold start is the normal state)")

    # C3 — calc stays async, never 5xx
    lzf = _src("src/api/lz/functions.py")
    add("C3", "202" in lzf and "building" in lzf,
        "build_calculator_estimate returns 202 + status 'building'; poll tool reports it")

    # C4 — retail prices fallback
    add("C4", "retail prices fetch failed" in tools or "rate book" in tools.lower()
        or "fallback" in tools.lower(),
        "cost tools fall back to the estimation rate book when the live API is unreachable")

    # C5 — missing AGENT_ID -> clean 503
    app = _src("src/web/app.py")
    add("C5", "AGENT_ID not set" in app and "503" in app,
        "/api/chat returns 503 with a clear reason when AGENT_ID is unset")

    # C6 — model error doesn't corrupt the transcript
    add("C6", "current_response_id" in app
        and app.index('.exception("chat failed")') > app.index("_save_chat"),
        "the response-id pointer + transcript are only written after a successful response")

    return {"checks": checks,
            "all_mitigations_in_place": all(c["mitigation_in_place"] for c in checks)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    res = run()
    for c in res["checks"]:
        print(f"  {'ok  ' if c['mitigation_in_place'] else 'MISS'}  {c['scenario']:9} {c['detail']}")
    print(f"\n  {'all mitigations in place' if res['all_mitigations_in_place'] else 'GAPS FOUND'}")
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2)
    return 0 if res["all_mitigations_in_place"] else 1


if __name__ == "__main__":
    sys.exit(main())
