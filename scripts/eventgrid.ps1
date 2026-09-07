# Landfall postdeploy - wire the questions/ container to the `start` function via
# Event Grid. On the Flex Consumption plan a blob trigger must be driven by Event
# Grid, and the subscription's webhook URL needs the function app's
# `blobs_extension` system key, which only exists once `azd deploy` has published
# the function - hence postdeploy. Idempotent: safe to re-run.
$ErrorActionPreference = 'Stop'

Write-Host "==> Loading azd environment"
foreach ($line in (azd env get-values)) {
  if ($line -match '^\s*([A-Z0-9_]+)="?(.*?)"?\s*$') {
    [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
  }
}

az extension add --name eventgrid --only-show-errors --yes 2>$null | Out-Null

$rg    = $env:AZURE_RESOURCE_GROUP
$func  = $env:SERVICE_API_NAME
$topic = $env:AZURE_EVENTGRID_SYSTEM_TOPIC

Write-Host "==> Fetching the blob-extension system key (waiting for the function host)"
$key = ""
for ($i = 0; $i -lt 20 -and [string]::IsNullOrWhiteSpace($key); $i++) {
  $key = (az functionapp keys list -g $rg -n $func --query 'systemKeys.blobs_extension' -o tsv 2>$null)
  if ([string]::IsNullOrWhiteSpace($key)) { Start-Sleep -Seconds 15 }
}
if ([string]::IsNullOrWhiteSpace($key)) {
  Write-Warning "blobs_extension key not available - re-run 'azd hooks run postdeploy' once the host is up."
  exit 1
}

$base = "https://$func.azurewebsites.net/runtime/webhooks/blobs"

Write-Host "==> Creating/updating the 'landfall-questions' event subscription"
az eventgrid system-topic event-subscription create `
  --name landfall-questions `
  --system-topic-name $topic `
  --resource-group $rg `
  --endpoint-type webhook `
  --endpoint "$base`?functionName=Host.Functions.start&code=$key" `
  --included-event-types Microsoft.Storage.BlobCreated `
  --subject-begins-with "/blobServices/default/containers/questions/blobs/" `
  --max-delivery-attempts 30 `
  --event-ttl 1440 `
  --only-show-errors `
  --output none

Write-Host "==> Creating/updating the 'landfall-inventory' event subscription"
az eventgrid system-topic event-subscription create `
  --name landfall-inventory `
  --system-topic-name $topic `
  --resource-group $rg `
  --endpoint-type webhook `
  --endpoint "$base`?functionName=Host.Functions.ingest_blob&code=$key" `
  --included-event-types Microsoft.Storage.BlobCreated `
  --subject-begins-with "/blobServices/default/containers/raw/blobs/inventory/" `
  --max-delivery-attempts 30 `
  --event-ttl 1440 `
  --only-show-errors `
  --output none

Write-Host "==> postdeploy complete - questions/*.xlsx triggers the batch runner;"
Write-Host "    raw/inventory/* triggers the ingestion pipeline"
