"""Run GitHub validation commands using the normal Git credential helper, in memory."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    gh = shutil.which("gh") or str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "GitHub CLI/gh.exe")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    if not (env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")):
        auth = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                              text=True, capture_output=True, env=env, timeout=30)
        values = dict(line.split("=", 1) for line in auth.stdout.splitlines() if "=" in line)
        if auth.returncode or not values.get("password"):
            print("BLOCKED: no GitHub CLI token or Git credential-helper login available")
            return 1
        env["GH_TOKEN"] = values["password"]
    return subprocess.run([gh, *args.args], env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
