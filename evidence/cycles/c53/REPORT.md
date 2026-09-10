# C53 system validation — 2026-09-10

The [system test plan](../../../tests/SYSTEM-TEST-PLAN.md) is implemented for the
available local and live gates. The reproduced web defects are fixed and deployed.
This is not an assertion that every production journey or roadmap feature passed.

## Results

| Gate | Observed result | Evidence |
|---|---|---|
| Local pytest | 534 passed, 9 skipped, one dependency deprecation warning; 38.59 seconds | [unit log](local-final/unit.log), [JUnit](local-final/unit.xml) |
| Browser | 7 passed; actual JS, fetch, CSP and downloads; fake Azure/model dependencies | [log](local-final/browser.log), [screenshot](local-final/screenshots/create-upload-analysis.png) |
| Evals | SQL 32/32; faults 30/30; adversarial 74/74 (3 pre-existing pending categories); scenarios 8/8 | [eval log](local-final/evals.log) |
| Backtest / broken dumps / evidence drift | All pass; no scorecard content changes | [local results](local-final/RESULTS.json) |
| Real calculator DOM | 17 verified adapters pass; 2 additional unverified adapters resolve controls; 2 unverified adapters warn | [adapter observations](external/calculator.json), [log](external/calculator.log) |
| Post-deploy smoke | 8 pass, 0 fail, 0 skip | [smoke](live-final/smoke.json) |
| Azure registration/readiness | 10 checks pass, including all 27 Function registrations | [services](live-final/services.json) |
| Security probe | All configured checks pass; public endpoints enforce authentication | [security](live-final/security.json) |
| Authenticated service operations | Foundry agent definition retrieved; Search index count = 27; SVG renders to PNG (104 bytes) | [data plane](live-final/data-plane.json) |
| Live model/SQL tool round-trip | **BLOCKED:** CLI cannot obtain a delegated Function token; no query executed | [token prerequisite check](tool-roundtrip.json) |

The nine local skips are the seven browser cases run separately, the opt-in real
calculator smoke run separately, and LibreOffice recalculation (not installed
locally). The existing CI has the recalculation gate. CI now also runs the browser
suite and retains its XML/screenshots; remote GitHub execution was not attempted.

## Defects and PDCA evidence

1. Named engagements with missing artifacts returned the default estate's files.
   Scoped lookup now searches only the requested engagement.
2. Unknown/unreadable manifests and explicit or implicit default scope bypassed
   dashboard authorization. These reads now fail closed. The added empty-scope
   regression initially returned HTTP 200 for Bob reading Alice's default data;
   it now returns a denial.
3. `/dashboard/download/{fmt}` swallowed the calculator workbook route. Static
   `/dashboard/download/landing-zone-xlsx` now dispatches before the generic route.
4. ZIP import accepted another owner's overwrite and trusted imported ownership
   and visibility. It now requires an authenticated owner, preserves existing
   ACLs, and binds new imports to the caller with owner visibility.
5. ZIP import accepted unsafe paths and excessive expanded data. Complete
   preflight rejects traversal, duplicate entries, mismatched manifests, symlinks,
   bad formats/CRC and expanded-size violations before file writes. SQL backups
   are explicitly reported as not restored. Storage failures return 503 with the
   number of completed writes; import is not an atomic multi-blob transaction.
   A final concurrency regression also showed files being written before a
   competing engagement-create conflict. New imports now claim the manifest with
   a conditional create before any archive file writes; a conflict returns 409.
6. The first live availability run failed on a cold web connection timeout.
   Ordinary liveness now retries transient 0/502/503/504 responses at most three
   times and records every attempt. Persistent failures still fail; the separate
   cold-start timing check is unchanged. [Original failure](live-before/smoke.json)
   remains in the evidence.
7. A subsequent smoke run inspected the retiring revision during rollout and
   reported `running=Deprovisioning`, although the new revision was ready and HTTP
   requests succeeded. The probe now selects the newest non-retiring active
   revision; both healthy and unhealthy replacement cases are regression-tested.
   [Rollover observation](rollover-smoke-failure.json) is retained separately.

The initial new boundary run had 17 product-regression failures and two test-helper
argument errors. The helper errors were corrected separately. The final suite
includes 25 passing boundary cases. Two Function-test harness errors (enum method
formatting and Durable middleware invocation) were also corrected; neither was
reported as a deployed-service defect.

The initial Search probe could not import the SDK. Installing the version already
pinned in `scripts/requirements.txt` resolved that local prerequisite; retain
[before](data-plane-before.json) and [after](data-plane-after.json) observations.
No Search configuration or access policy was changed.

## Deployment

`azd deploy web --no-prompt` exited 0. Subscription
`f609eb5b-df3e-4fab-9a1b-9a8fea2f157f`, resource group `rg-landfall`, region
`swedencentral`. Active/ready revision:
`ca-web-tmglwfatwcsa2--azd-1789029091`, 100% latest-revision traffic.
Image: `crtmglwfatwcsa2.azurecr.io/landfall/web-landfall:azd-deploy-1789029005`.
No provisioning, schema application, paid-tier change or customer-data mutation.

## Still outstanding

- Signed-in production browser with two Entra principals, full live tool/SQL/RLS
  round-trip, upload/Event Grid/ingestion and calculator queue/export journey.
  `scripts/validate_tool_roundtrip.py --output <path>` provides a bounded model/SQL
  check when a delegated Function token is available; it was blocked here.
- Bastion and Application Gateway are already unverified adapters and still have
  missing DOM controls. Monitor and Load Balancer resolve controls but remain
  unverified for pricing/export correctness. The calculator gate only certifies
  its 17 verified adapters; it does not promote the others.
- LibreOffice recalc and the updated workflow on GitHub; scratch-environment
  teardown/rehydrate, clean-machine deployment and induced chaos.
- External pentest, human usability/comprehension and architect/FinOps review.

These remain mapped in the tracker. The overall evidence score and E13 completion
count are unchanged; functional test growth alone does not earn a 5/5 rating.
