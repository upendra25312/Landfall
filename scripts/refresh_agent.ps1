$ErrorActionPreference = 'Stop'

# Refresh only the Foundry prompt-agent definition after an OpenAPI or prompt
# change. This intentionally does not provision resources or apply SQL schema.
foreach ($line in (azd env get-values)) {
  if ($line -match '^\s*([A-Z0-9_]+)="?(.*?)"?\s*$') {
    [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
  }
}
$env:AZURE_SUBSCRIPTION_ID = (azd env get-value AZURE_SUBSCRIPTION_ID)

$agentOutput = @(.venv2\Scripts\python.exe scripts/create_agent.py)
if ($LASTEXITCODE -ne 0) { throw "create_agent.py failed ($LASTEXITCODE)" }
$agentLine = $agentOutput | Where-Object { $_ -match '^AGENT_ID=' } | Select-Object -Last 1
if (-not $agentLine) { throw 'create_agent.py did not return AGENT_ID' }
$agentId = ($agentLine -replace '^AGENT_ID=', '').Trim()
if (-not $agentId) { throw 'create_agent.py returned an empty AGENT_ID' }

azd env set AGENT_ID $agentId | Out-Null
az functionapp config appsettings set `
  --subscription $env:AZURE_SUBSCRIPTION_ID `
  --resource-group $env:AZURE_RESOURCE_GROUP `
  --name $env:SERVICE_API_NAME `
  --settings "AGENT_ID=$agentId" --output none
if ($LASTEXITCODE -ne 0) { throw 'Function AGENT_ID update failed' }
az containerapp update `
  --subscription $env:AZURE_SUBSCRIPTION_ID `
  --resource-group $env:AZURE_RESOURCE_GROUP `
  --name $env:SERVICE_WEB_NAME `
  --set-env-vars "AGENT_ID=$agentId" --output none
if ($LASTEXITCODE -ne 0) { throw 'Web AGENT_ID update failed' }

Write-Host "Agent refreshed: $agentId"
