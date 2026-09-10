# Clean-machine validation prerequisites

The workflow `.github/workflows/clean-machine.yml` provisions, deploys, probes,
and deletes a **separate disposable environment**, on Windows and Linux. It must
never target populated `rg-landfall` or reuse its azd environment.

C54 found no repository secrets or variables configured for this workflow. The
current subscription also already contains `srch-tmglwfatwcsa2` on the Free tier.
[Azure permits one free Search service per subscription](https://learn.microsoft.com/en-us/azure/search/search-sku-tier?tabs=basic).
The $40–50/month project constraint excludes solving this by upgrading Search.

To execute the pending lifecycle proof:

1. Supply an authorized scratch subscription with an unused free Search slot,
   appropriate model capacity and the region the workflow will use.
2. Configure a dedicated OIDC application/principal and GitHub federated identity
   for this repository. Scope its deployment rights to the scratch environment.
3. Set workflow secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`, and `AZURE_PRINCIPAL_ID`. Use the repository's standard
   secret UI/CLI; never put credentials in source or test evidence.
4. Set `CLEAN_MACHINE_LOCATION` and arm `CLEAN_MACHINE_CI=true` only after checking
   the subscription, free-tier parameters and cleanup permissions.
5. Dispatch `clean-machine`; retain both OS job logs, smoke JSON and cleanup
   results. A skipped workflow is not a successful lifecycle test.
6. Confirm the scratch resource groups have been removed and check remaining
   resources/cost. Run teardown/rehydrate and induced-chaos cases only there.

The ordinary `evals` workflow requires no Azure credentials and includes Python
3.11 tests, browser journeys, LibreOffice recalculation, evals and evidence drift.
It runs on `main` and `cycle-*` pushes, enabling review before merging a cycle.
