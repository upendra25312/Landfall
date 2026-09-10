# C54 independent review handoff

Automated checks do not substitute for independent security review, observation
of actual users, or architect/FinOps approval. No reviewers were contacted or
findings invented. Reviewer names and scheduling were requested from the user.

| Review | Ready-to-use material | Required completed evidence |
|---|---|---|
| Independent penetration test | [Scope/threat model](../../pentest/threat-model.md), [probe and process](../../pentest/README.md), C53/C54 negative tests | Named reviewer, approved scope, dates, findings/severity, remediation and retest |
| Usability and comprehension | [Trial protocol](../../trials/protocol.md), [results template](../../trials/results-template.md), [answer key](../../trials/comprehension-answer-key.md) | Real participants, task completion/time/errors, comprehension scores; distinguish observed results from scripted dry runs |
| Architect | [How Landfall works](../../../docs/how-landfall-works.html), representative deterministic exports and landing-zone/wave assumptions | Named reviewer and disposition of architecture, dependency, resiliency and migration recommendations |
| FinOps | [Backtest](../../backtest/RESULTS.md), actual calculator workbooks in this cycle | Reconcile quantities, region, tier, licensing and prices; sign off assumptions and unresolved pricing coverage |
| Lifecycle and chaos | [Clean-machine prerequisites](../../../docs/clean-machine-ci.md), [chaos scenarios](../../chaos/scenarios.md) | Isolated environment, actual failure/recovery observations, teardown/rehydrate and cleanup evidence |

The calculator's Bastion exception is intentionally narrow: the requested
transfer must equal the calculator's default **5 GB/month**, which is in the
[published free allowance](https://azure.microsoft.com/en-us/pricing/details/azure-bastion/).
If that control is unavailable for a different quantity, the run fails explicitly.
No other region or price is silently substituted. Include this limitation in
FinOps review and recheck it when the calculator changes.
