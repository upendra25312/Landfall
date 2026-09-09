# Operability evidence (PRD E9 / scorecard "Operability")

## `smoke-live.json`

A captured run of `scripts/smoke.py` against the live `rg-landfall` deployment.
Point-in-time — **not** drift-gated (SQL status flips Online/Paused, the blob
container list grows). Regenerate with:

```bash
python scripts/smoke.py --json evidence/ops/smoke-live.json
```

What it proves: the deployed stack is serving — all 20 expected resources present,
the Function host answers (401 = Easy Auth enforcing), the web container revision
is Healthy/Provisioned/Running, SQL is reachable, the `raw` + `answers` containers
exist, and (`--deep`) the Foundry agent name resolves.

## Clean-machine CI

`.github/workflows/clean-machine.yml` runs `azd up → smoke.py → azd down` on
Linux + Windows. Dormant until the OIDC secrets + `CLEAN_MACHINE_CI=true` repo
variable are added — see `DEPLOY.md` § "Clean-machine CI". Once armed, its
per-OS `smoke-*.json` artifacts belong here too.

## Still open (Operability → 5/5)

- arm the clean-machine CI (one-time secret add) and get it green on both OSes
- E9.3 `--tier prod` parameter set + cost-delta doc
- E9.4 answer-quality observability (traces + dashboard + alerts)
- E9.5 export-before-teardown step
- a logged chaos drill (`evidence/chaos/`) — kill a dependency, show it degrades cleanly
- fold the `web` Container App Easy Auth into Bicep (drift the CI would catch)
