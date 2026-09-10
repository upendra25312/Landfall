# C54 validation tail — 2026-09-10

## Completed checks and fixes

- Local regression: **543 passed, 9 skipped**; seven browser journeys and six real
  LibreOffice recalculation tests pass separately. [Results](local-final/RESULTS.json).
  Evals/backtests/broken dumps and scorecard drift remain green.
- All four previously unverified calculator adapters were exercised against real
  controls, non-default quantities, UI totals and actual Excel exports:
  [Sweden Central](calculator-final/controls.json),
  [West Europe variants](calculator-variants/controls.json).
- Application Gateway now uses V2 compute/connection/throughput capacity controls
  and separate transfer units, rather than obsolete V1 size/instance controls.
  Explicit zero Bastion transfer is preserved instead of being replaced by 5 GB.
- Incomplete calculator configurations now fail explicitly instead of exporting
  default prices. Missing regional selectors are distinguished from the global
  Bandwidth and DNS products, which have no regional selector.
- Bastion's missing Sweden Central transfer controls are a provider coverage
  limitation. Exactly the calculator's default 5 GB is accepted with a disclosed
  assumption because it is within the
  [published free allowance](https://azure.microsoft.com/en-us/pricing/details/azure-bastion/).
  Other quantities without controls fail. Premium/20 GB/non-default scale units
  were verified in West Europe; no other region is silently substituted.
- Foundry → managed-identity Function tool → SQL succeeded: **250** servers in
  the sample and **0** in an empty scope. [Actual tool-output verification](agent-verified.json).
  The first count request returned HTTP 400; its original observation is retained.
  This proves the agent tool path, not interactive web authentication.
- Those live responses exposed a web defect: `openapi_call_output` with nested
  `response` JSON was ignored by chat Excel export. The parser, regression and
  browser fixture now cover the actual deployed response format.
- Blob upload → Event Grid → Function → SQL → DQ report passed for one synthetic
  row in `validation-c54/pipeline-20260910090640`. [Evidence](ingestion/RESULTS.json).
  This synthetic engagement is retained; customer data was not changed.
- Installed LibreOffice and GitHub CLI. GitHub access uses the normal Git
  credential helper in memory; credentials are not written to evidence/source.

## Release checks

The complete **21/21 adapter smoke passes**: [results](external-final/RESULTS.json).
Web and calculator deployments both exited 0:

- Web: `ca-web-tmglwfatwcsa2--azd-1789031554`;
  image `web-landfall:azd-deploy-1789031478`; 100% latest-revision traffic.
- Calculator: `ca-calc-tmglwfatwcsa2--azd-1789031776`;
  image `calc-landfall:azd-deploy-1789031709`.
- [Final live checks](live-final/RESULTS.json): smoke 8/8, service readiness 10/10,
  security and authenticated service operations pass. The first security run
  experienced a connection timeout; [its failure is retained](live-first/security.json).
- The Azure user's direct queue-send attempt was denied by existing RBAC
  ([observation](queue/RESULTS.json)). No permissions were changed. The actual
  application path succeeded: **Foundry → Function → queue → deployed calculator
  worker → four-service Excel export**, using existing managed identities.
  [Queue proof](agent-queue/RESULTS.json), [actual workbook](agent-queue/calculator.xlsx).
  The second synthetic engagement, `validation-c54/pipeline-20260910091657`, is
  retained with its single inventory row and calculator artifacts.

Remote GitHub CI is **blocked by automatic approval review**: the attempted push
to the public repository was rejected because it includes C52–C54 Azure/SQL and
validation evidence without explicit public-publication approval. GitHub access
itself works. [Concrete publication review](PUBLICATION-REVIEW.md).

## External prerequisites

- Interactive production browser: [blocked](production-browser/RESULTS.json)
  because Entra sign-in was not completed. Two actual user identities and the full
  signed-in browser journey remain pending; a reusable interactive runner is in
  `scripts/validate_production_browser.py`.
- Full-stack scratch deployment/lifecycle/chaos: the current subscription already
  uses its one permitted free Search service (`srch-tmglwfatwcsa2`), and the
  clean-machine workflow has no OIDC secrets/variables. An authorized alternate
  subscription with free capacity was requested. No paid tier or destructive
  operation against `rg-landfall` was used.
- Independent security, usability/comprehension and architect/FinOps sign-off need
  actual reviewers. [Review handoff](REVIEW-HANDOFF.md) provides the existing
  protocols, acceptance and evidence to complete; reviewer details were requested.

These dependencies cannot be replaced by simulated sign-ins, invented reviewers,
or relabeling skipped workflows as passed.
