# Chaos drill — degrade predictably when a dependency is down (PRD E9, Operability 5/5 bar)

Six failure modes on the critical path. For each: what should happen, the code
that makes it happen, and how to induce it for a live drill. `RESULTS.md` records
the last run.

The design principle throughout: **a dependency being down produces a slow or
partial answer with a clear reason — never a wrong answer and never a silent
half-result** (the same rule as E1.4 for broken inputs).

| # | Failure | Expected degradation | Must NOT happen |
|---|---|---|---|
| C1 | **Azure SQL auto-paused** (serverless, 1 h idle) | First query throws "database is not currently available"; the caller retries and the DB resumes in ~40 s; the answer is just slow | A hard failure with no retry; a 0-row answer presented as real |
| C2 | **`ca-drawio` scaled to zero** (minReplicas 0) | The first diagram build after idle cold-starts the container (45 s + one retry). If it still isn't up, the `.png` is skipped — the `.drawio` + `.svg` still ship | The whole diagram build fails; the deck/doc export fails because a raster is missing |
| C3 | **`ca-calc` container down / queue not drained** | `build_calculator_estimate` still returns 202; `landing_zone.json` stays `status: building`; the poll tool + dashboard say "building" | A 5xx to the agent; a published estimate that claims a POE number it never got |
| C4 | **Azure Retail Prices API unreachable** | Cost tools fall back to the injected/estimation rate book; the figure carries an assumption noting the rate source and date | An exception that fails the whole estimate; a price silently invented by the model |
| C5 | **`AGENT_ID` unset / agent version deleted** | `/api/chat` returns `503` with "AGENT_ID not set - run the postprovision hook"; the dashboard + deterministic tools are unaffected | A 500 with a stack trace; a blank page |
| C6 | **Foundry model throttled (429)** | `/api/chat` returns the upstream error text with a 500; the conversation pointer is not advanced, so a retry resumes cleanly | A partial answer saved to the transcript; the response-id chain corrupted |

## Inducing each (for a full live drill)

- **C1** — `az sql db update -g <rg> -s <server> -n <db> --auto-pause-delay 15`, wait
  15 min idle, then hit `/dashboard/data`. (Or just observe it — the DB
  auto-pauses on its own.)
- **C2** — it is *already* at zero when idle. `az containerapp replica list` shows
  0; trigger `build_landing_zone_diagram` and watch the cold start.
- **C3** — `az containerapp update -g <rg> -n ca-calc-<token> --min-replicas 0
  --max-replicas 0`, then `publish_estimate {build_poe:true}`; restore after.
- **C4** — block egress to `prices.azure.com` (or point `AZURE_RETAIL_PRICES_URL`
  at a dead host) and run a cost tool.
- **C5** — `az functionapp config appsettings delete ... --setting-names AGENT_ID`
  on a scratch env (never the live one); hit `/api/chat`.
- **C6** — hammer `/api/chat` past the model TPM, or set `MODEL_CAPACITY 1`.

`probe.py` runs the **non-destructive** subset: it reads the current state
(replica counts, SQL status, the retry constants, the 503 path) and confirms the
mitigations are in place, without inducing an outage on the shared env.
