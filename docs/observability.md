# Answer-quality observability (E9.4)

*Can an operator see a bad answer, and does the tool error rate alert?*

Everything below runs against the deployment's **Application Insights** (name:
`appi-<token>`, wired to the Log Analytics workspace). Two signals:

- **`requests`** — Azure Functions emits one per tool invocation automatically:
  `operation_Name` (the tool), `success`, `duration`, `resultCode`. This gives
  volume, latency and error rate per tool with **no instrumentation**.
- **`traces`** — `src/api/obs.py::event()` writes structured lines that land as
  `traces` with a `customDimensions.event` tag:
  - `query_inventory` — `status` (`ok` / `rejected` / `text_to_sql_error` /
    `query_error`), `rows`, `shape`, `tables`, `ms`, hashed `engagement`
  - `estimate_assembled` — `status`, `overall_confidence`, `figures`,
    `low` / `medium` / `high` figure counts, hashed `engagement`

`engagement` is a SHA-256 prefix, never the raw customer/project — an operator
groups by it, but the client name is not in the logs.

## The workbook

`infra/workbook-answer-quality.json` deploys as the **"Landfall — answer quality"**
workbook (Application Insights → Workbooks). Tiles: tool calls / failures /
latency (24h), Function failure rate, `query_inventory` outcome mix, published
estimates with their confidence mix (7d), recent errors, failures by tool +
result code.

## Runbook — "is an answer bad?"

Paste into Application Insights → Logs:

```kql
// tools failing right now
requests | where timestamp > ago(1h)
| summarize calls=count(), failed=countif(success==false), p95=percentile(duration,95) by operation_Name
| where failed > 0 | order by failed desc

// query_inventory that could not produce a safe query
traces | where timestamp > ago(24h)
| where customDimensions.event == "query_inventory" and customDimensions.status != "ok"
| project timestamp, status=customDimensions.status, reason=customDimensions.reason, tables=customDimensions.tables

// estimates shipped at Low overall confidence
traces | where timestamp > ago(7d)
| where customDimensions.event == "estimate_assembled" and customDimensions.overall_confidence == "Low"
| project timestamp, engagement=customDimensions.engagement, low=customDimensions.low, figures=customDimensions.figures

// everything at Error severity, newest first
traces | where timestamp > ago(24h) | where severityLevel >= 3
| project timestamp, tool=operation_Name, message | order by timestamp desc
```

## The alert

`azd env set ALERT_EMAIL you@example.com` then `azd provision` creates an action
group + a scheduled-query-rule alert: **Function request failure rate > 5% over
15 minutes** (min 5 calls), evaluated every 5 min, severity 2, emails the action
group. With `ALERT_EMAIL` empty the workbook still deploys; no alert, no action
group.

## Not yet

- The **web tier** (`src/web`, FastAPI) has the App Insights connection string as
  an env var but does not forward its logs — the chat handler's telemetry would
  need `azure-monitor-opentelemetry` + `configure_azure_monitor()`. Tool-level
  telemetry covers answer quality because the chat path is agent → tools.
- No latency SLO / burn-rate alerting; the one alert is a blunt failure-rate gate.
