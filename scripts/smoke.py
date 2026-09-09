"""Landfall post-deploy smoke test (PRD E9.2).

Runs after `azd up` (or against any live deployment) and asserts the stack is
actually serving: every expected resource exists, the Function host and the web
container answer, SQL is reachable, the blob containers are there. Exits non-zero
on the first hard failure so a CI job (`.github/workflows/clean-machine.yml`) can
gate on it.

Stdlib only — no pip install needed before it runs. `az` must be on PATH and
logged in (the CI service principal, or `az login` locally).

Usage:
    python scripts/smoke.py                 # read config from `azd env get-values`, else os.environ
    python scripts/smoke.py --json out.json # also write the structured result
    python scripts/smoke.py --deep          # + agent-resolves + (with SMOKE_API_TOKEN) a live query_inventory call
    python scripts/smoke.py --from-env      # skip azd, use os.environ only

Config keys (from `azd env get-values` or the environment):
    AZURE_RESOURCE_GROUP  SERVICE_API_NAME  SERVICE_WEB_URI  SERVICE_WEB_NAME
    AZURE_SQL_SERVER_FQDN  AZURE_SQL_DATABASE  AZURE_STORAGE_ACCOUNT
    AGENT_ID  FOUNDRY_PROJECT_ENDPOINT           (only used by --deep)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

# HTTP statuses that mean "the host is up and reachable" for an unauthenticated
# probe — 401/403 mean EasyAuth is enforcing, 302 is a login redirect, 404 means
# the host routed us. Anything else (000 connect error, 5xx, 503) is a failure.
_HOST_UP = {200, 204, 301, 302, 303, 307, 308, 400, 401, 403, 404}


# ---------------------------------------------------------------- config

def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} timed out after {timeout}s"


def _az(args: list[str], timeout: int = 90) -> tuple[int, object, str]:
    """`az <args> -o json` -> (rc, parsed-or-raw, stderr)."""
    az = shutil.which("az") or ("az.cmd" if os.name == "nt" else "az")
    rc, out, err = _run([az, *args, "-o", "json"], timeout=timeout)
    if rc != 0:
        return rc, None, err
    try:
        return rc, json.loads(out) if out else None, err
    except json.JSONDecodeError:
        return rc, out, err


def load_config(from_env: bool = False) -> dict[str, str]:
    cfg: dict[str, str] = {}
    if not from_env and (shutil.which("azd") or shutil.which("azd.exe")):
        rc, out, _ = _run([shutil.which("azd") or "azd", "env", "get-values"], timeout=30)
        if rc == 0:
            for line in out.splitlines():
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip().strip('"')
    for k, v in os.environ.items():                      # environ overrides / fills gaps
        if k.startswith(("AZURE_", "SERVICE_", "FOUNDRY_", "AGENT_")) and v:
            cfg.setdefault(k, v)
        if from_env and k.startswith(("AZURE_", "SERVICE_", "FOUNDRY_", "AGENT_")) and v:
            cfg[k] = v
    return cfg


def _host(uri_or_name: str, suffix_env: str = "") -> str:
    """A bare host from either a full URI or a resource name (+ known suffix)."""
    if uri_or_name.startswith("http"):
        return uri_or_name.split("://", 1)[1].split("/", 1)[0]
    return uri_or_name


def _http_status(url: str, method: str = "GET", timeout: int = 20,
                 headers: dict | None = None, body: bytes | None = None) -> int:
    req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


# ---------------------------------------------------------------- checks

class Result:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append({"check": name, "status": status, "detail": detail})

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if c["status"] == FAIL]

    def to_dict(self) -> dict:
        return {"ok": not self.failed,
                "counts": {s: sum(c["status"] == s for c in self.checks) for s in (PASS, FAIL, SKIP)},
                "checks": self.checks}


def _need(cfg: dict, *keys: str) -> str | None:
    return next((k for k in keys if not cfg.get(k)), None)


def run_checks(cfg: dict, deep: bool = False) -> Result:
    r = Result()
    rg = cfg.get("AZURE_RESOURCE_GROUP", "")

    # 1 — config completeness
    missing = [k for k in ("AZURE_RESOURCE_GROUP", "SERVICE_API_NAME", "SERVICE_WEB_URI",
                           "AZURE_SQL_SERVER_FQDN", "AZURE_SQL_DATABASE", "AZURE_STORAGE_ACCOUNT")
               if not cfg.get(k)]
    r.add("config", FAIL if missing else PASS,
          f"missing: {', '.join(missing)}" if missing else "all deploy outputs present")

    # 2 — every expected resource type is in the group
    if rg:
        rc, res, err = _az(["resource", "list", "-g", rg, "--query", "[].type"])
        if rc != 0 or not isinstance(res, list):
            r.add("resources", FAIL, f"az resource list failed: {err[:200]}")
        else:
            types = {t.lower() for t in res}
            want = {
                "function app": "microsoft.web/sites",
                "container app(s)": "microsoft.app/containerapps",
                "sql server": "microsoft.sql/servers",
                "storage": "microsoft.storage/storageaccounts",
                "ai services": "microsoft.cognitiveservices/accounts",
                "ai search": "microsoft.search/searchservices",
                "container registry": "microsoft.containerregistry/registries",
            }
            gaps = [label for label, t in want.items() if t not in types]
            r.add("resources", FAIL if gaps else PASS,
                  f"absent: {', '.join(gaps)}" if gaps else f"{len(res)} resources, all expected types present")
    else:
        r.add("resources", SKIP, "no resource group")

    # 3 — Function host is registered in ARM + the host answers HTTP
    #     (Flex Consumption reports `state: null`, so liveness is the HTTP probe)
    func = cfg.get("SERVICE_API_NAME", "")
    if func and rg:
        rc, show, err = _az(["functionapp", "show", "-g", rg, "-n", func,
                             "--query", "{kind:kind,host:defaultHostName}"])
        registered = rc == 0 and isinstance(show, dict) and "functionapp" in (show.get("kind") or "")
        host = (show or {}).get("host") or f"{func}.azurewebsites.net"
        r.add("function_registered", PASS if registered else FAIL,
              f"kind={ (show or {}).get('kind')!r}" if rc == 0 else f"az failed: {err[:160]}")
        code = _http_status(f"https://{host}/api/engagements")
        r.add("function_host", PASS if code in _HOST_UP and code != 0 else FAIL,
              f"GET /api/engagements -> {code}" + (" (EasyAuth enforcing)" if code in (401, 403) else ""))
    else:
        r.add("function_registered", SKIP, "no function app name")
        r.add("function_host", SKIP, "no function app name")

    # 4 — web container: an active revision that is Healthy + Provisioned + Running
    web_name = cfg.get("SERVICE_WEB_NAME", "")
    if web_name and rg:
        rc, revs, err = _az(["containerapp", "revision", "list", "-g", rg, "-n", web_name])
        active = [v for v in revs if v.get("properties", {}).get("active")] if isinstance(revs, list) else []
        if active:
            p = active[0]["properties"]
            healthy = (p.get("healthState") in ("Healthy", "None")
                       and p.get("provisioningState") in ("Provisioned", "Succeeded")
                       and p.get("runningState") in ("Running", "RunningAtMaxScale", "ScaledToZero", None))
            r.add("web_revision", PASS if healthy else FAIL,
                  f"health={p.get('healthState')} prov={p.get('provisioningState')} "
                  f"running={p.get('runningState')}")
        else:
            r.add("web_revision", FAIL, f"no active revision ({len(revs) if isinstance(revs, list) else '?'} total): {err[:120]}")
    else:
        r.add("web_revision", SKIP, "no web container name")

    web_uri = cfg.get("SERVICE_WEB_URI", "").rstrip("/")
    if web_uri:
        code = _http_status(f"{web_uri}/healthz")
        r.add("web_up", PASS if code in _HOST_UP else FAIL,
              f"GET /healthz -> {code}" + (" (EasyAuth enforcing)" if code in (401, 403) else ""))
    else:
        r.add("web_up", SKIP, "no web uri")

    # 5 — SQL database reachable (serverless may be Paused/AutoClosed — still 'up')
    server = cfg.get("AZURE_SQL_SERVER_FQDN", "").split(".")[0]
    dbname = cfg.get("AZURE_SQL_DATABASE", "")
    if server and dbname and rg:
        rc, status, err = _az(["sql", "db", "show", "-g", rg, "-s", server, "-n", dbname,
                               "--query", "status"])
        ok = status in ("Online", "Paused", "AutoClosed", "Standby")
        r.add("sql_database", PASS if ok else FAIL,
              f"status={status!r}" if rc == 0 else f"az sql db show failed: {err[:160]}")
    else:
        r.add("sql_database", SKIP, "no sql server/database")

    # 6 — blob containers exist (data-plane; SKIP if the caller lacks RBAC here)
    acct = cfg.get("AZURE_STORAGE_ACCOUNT", "")
    if acct:
        rc, names, err = _az(["storage", "container", "list", "--account-name", acct,
                              "--auth-mode", "login", "--query", "[].name"], timeout=60)
        if rc == 0 and isinstance(names, list):
            want = {"raw", "answers"}
            gaps = want - set(names)
            r.add("blob_containers", FAIL if gaps else PASS,
                  f"missing: {', '.join(sorted(gaps))}" if gaps else f"{sorted(names)}")
        else:
            r.add("blob_containers", SKIP, f"cannot list containers (data-plane RBAC?): {err[:120]}")
    else:
        r.add("blob_containers", SKIP, "no storage account")

    # 7 — deep: the agent name resolves in the Foundry project
    if deep:
        _deep_agent(cfg, r)
        _deep_query(cfg, r)

    return r


def _deep_agent(cfg: dict, r: Result) -> None:
    endpoint, agent = cfg.get("FOUNDRY_PROJECT_ENDPOINT"), cfg.get("AGENT_ID")
    if not (endpoint and agent):
        r.add("agent_resolves", SKIP, "no FOUNDRY_PROJECT_ENDPOINT / AGENT_ID")
        return
    try:
        from azure.ai.projects import AIProjectClient           # type: ignore
        from azure.identity import DefaultAzureCredential        # type: ignore
    except ImportError:
        r.add("agent_resolves", SKIP, "azure-ai-projects not installed")
        return
    try:
        proj = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
        got = proj.agents.get(agent)                             # raises if the name is unknown
        name = getattr(got, "name", None) or (got.get("name") if hasattr(got, "get") else None)
        r.add("agent_resolves", PASS, f"{name or agent!r} exists in the Foundry project")
    except Exception as e:                                       # noqa: BLE001
        r.add("agent_resolves", FAIL, f"{type(e).__name__}: {str(e)[:160]}")


def _deep_query(cfg: dict, r: Result) -> None:
    token = os.environ.get("SMOKE_API_TOKEN")
    func = cfg.get("SERVICE_API_NAME")
    if not (token and func):
        r.add("query_inventory_live", SKIP, "no SMOKE_API_TOKEN / function name")
        return
    body = json.dumps({"engagement": "_default_/_default_",
                       "question": "How many servers are in the inventory?"}).encode()
    code = _http_status(f"https://{func}.azurewebsites.net/api/query_inventory", method="POST",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        body=body, timeout=45)
    r.add("query_inventory_live", PASS if code == 200 else FAIL, f"POST -> {code}")


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Landfall post-deploy smoke test (E9.2)")
    ap.add_argument("--json", metavar="PATH", help="write the structured result here")
    ap.add_argument("--deep", action="store_true", help="also run agent-resolve + live query_inventory checks")
    ap.add_argument("--from-env", action="store_true", help="ignore `azd`, take config from the environment")
    args = ap.parse_args(argv)

    cfg = load_config(from_env=args.from_env)
    result = run_checks(cfg, deep=args.deep)
    d = result.to_dict()

    width = max(len(c["check"]) for c in result.checks)
    for c in result.checks:
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "SKIP": "--  "}[c["status"]]
        print(f"  {mark}  {c['check'].ljust(width)}  {c['detail']}")
    n = d["counts"]
    print(f"\n  {n[PASS]} passed, {n[FAIL]} failed, {n[SKIP]} skipped")

    if args.json:
        parent = os.path.dirname(args.json)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2)
        print(f"  wrote {args.json}")

    if result.failed:
        print("\n  SMOKE FAILED: " + ", ".join(c["check"] for c in result.failed))
        return 1
    print("\n  smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
