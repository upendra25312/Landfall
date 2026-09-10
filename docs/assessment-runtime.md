# Assessment execution and agent limits

`POST /api/run_assessment` executes a fixed sequence: validate engagement, ingest,
read scoped inventory, check DQ, rightsize, compute/storage cost, run-rate extras,
dispositions, waves, schedule, landing zone, diagram, assemble, effort and publish.
It uses the existing deterministic engines. A stage failure stops the sequence;
its run record retains completed outputs and the failed stage. Missing prices or
inventory are never silently promoted into a completed full estimate.

Records are stored under `answers/engagements/<customer>/<project>/assessment/`.
The record ID distinguishes attempts; the input hash identifies the inventory,
configuration, assessment date and actual pricing results. Dates are fixed within
one run. Identical published packages preserve the existing baseline bytes and
publication time. Price changes are new inputs. Calendar roll-forward is a new
assessment date, not a byte-identical replay of the prior assessment.

The full-estimate agent instruction calls this tool once. Focused questions still
use individual tools. The function is synchronous; its stage record survives an
interrupted HTTP request, but it is not yet a Durable Functions resumable workflow.
Do not retry an uncertain publication blindly. Artifact uploads are separate blob
operations; `latest.json` is written after exports, not an atomic multi-blob commit.

`src/web/agent_limits.py` is the chat limit configuration surface:

| Setting | Default |
|---|---:|
| MAX_AGENT_RUNTIME_SECONDS | 180 |
| MAX_TOOL_CALLS_PER_TURN | 16 |
| MAX_TOOL_RETRIES | 0 |
| MAX_CONVERSATION_TURNS | 20 |
| MAX_OUTPUT_TOKENS | 4000 |
| MAX_INPUT_CHARACTERS | 16000 |

Automatic SDK retries remain disabled because a response can invoke write tools.
The web process requests a background response, polls without blocking its event
loop, and attempts remote cancellation on timeout. A network failure before the
response ID is returned, or a failed cancellation, cannot guarantee remote work
has stopped; inspect saved outputs. Cancellation also cannot undo a tool's writes.
Server tool-call caps must be verified against the deployed Foundry runtime.
Completed/partial status and available token usage accompany the chat telemetry.

Reference: [Foundry Responses API](https://ai.azure.com/api-reference/responses/).
