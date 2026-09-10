"""Execute the system test plan with bounded commands and retained evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def run_gate(name, command, output, env=None, timeout=900):
    started = time.monotonic()
    log = output / f"{name}.log"
    xml = output / f"{name}.xml"
    xml.unlink(missing_ok=True)  # never report a prior run's test results
    with log.open("w", encoding="utf-8") as stream:
        try:
            process = subprocess.run(command, cwd=ROOT, env={**os.environ, **(env or {})},
                                     stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            code = process.returncode
            status = "PASS" if code == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            code, status = None, "TIMEOUT"
        except OSError as exc:
            stream.write(f"{type(exc).__name__}: {exc}\n")
            code, status = None, "BLOCKED"
    result = {"gate": name, "status": status, "exit_code": code,
              "seconds": round(time.monotonic() - started, 2), "log": str(log.relative_to(output))}
    if xml.exists():
        root = ET.parse(xml).getroot()
        result["tests"] = len(root.findall(".//testcase"))
        result["skipped"] = [{"test": case.get("name"), "reason": case.find("skipped").get("message")}
                             for case in root.findall(".//testcase") if case.find("skipped") is not None]
    print(f"{name}: {status} ({result['seconds']}s)", flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="Run only live read-only probes")
    parser.add_argument("--external", action="store_true", help="Run the real calculator DOM smoke")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    gates, outstanding = [], []
    if args.live:
        commands = [
            ("smoke", [py, "scripts/smoke.py", "--json", str(output / "smoke.json")], {}),
            ("services", [py, "scripts/validate_live.py", "--output", str(output / "services.json")], {}),
            ("security", [py, "evidence/pentest/sec_probe.py", "--json", str(output / "security.json")], {}),
            ("data-plane", [py, "scripts/validate_data_plane.py", "--output", str(output / "data-plane.json")], {}),
        ]
        outstanding += ["Authenticated production browser and all tool data-plane calls",
                        "Scratch-environment teardown/rehydrate, clean-machine CI and induced chaos",
                        "External penetration test and human usability/comprehension trials"]
    elif args.external:
        commands = [("calculator", [py, "src/calc/smoke.py", "--json", str(output / "calculator.json")], {})]
    else:
        commands = [
            ("unit", [py, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider",
                      f"--junitxml={output / 'unit.xml'}"], {"BROWSER": "0", "RECALC": "0", "CALC_SMOKE": "0"}),
            ("evals", [py, "evals/runner.py"], {}),
            ("backtest", [py, "evidence/backtest/backtest.py"], {}),
            ("broken-dumps", [py, "evidence/broken-dumps/check.py"], {}),
            ("browser", [py, "-m", "pytest", "tests/browser", "-q", "-p", "no:cacheprovider",
                         f"--junitxml={output / 'browser.xml'}"],
             {"BROWSER": "1", "C53_SCREENSHOT_DIR": str(output / "screenshots")}),
        ]
        if shutil.which("soffice"):
            commands.append(("recalc", [py, "-m", "pytest", "tests/test_xlsx_recalc.py", "-q",
                                        "-p", "no:cacheprovider", f"--junitxml={output / 'recalc.xml'}"], {"RECALC": "1"}))
        else:
            outstanding.append("LibreOffice recalculation: soffice not installed (CI has this gate)")
        commands.append(("evidence-drift", ["git", "diff", "--exit-code", "--", "evals/SCORECARD.md",
                                            "evidence/SCORECARD.md", "evidence/backtest/RESULTS.md",
                                            "evidence/broken-dumps/RESULTS.md"], {}))
        outstanding += ["Live Azure checks: run --live", "Real calculator DOM checks: run --external"]
    for name, command, env in commands:
        gates.append(run_gate(name, command, output, env))
    if args.external and (output / "calculator.json").exists():
        calculator = json.loads((output / "calculator.json").read_text(encoding="utf-8"))
        for row in calculator.get("rows", []):
            if not row.get("verified"):
                outstanding.append(f"Unverified calculator adapter: {row['service']}; "
                                   f"missing controls={row.get('missing', [])}; error={row.get('error')}")
    result = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "selected_gates_passed": all(g["status"] == "PASS" for g in gates),
              "gates": gates, "not_validated_by_this_run": outstanding}
    (output / "RESULTS.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["selected_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
