# Landfall postprovision - runs after `azd provision`, before `azd deploy`. Idempotent.
$ErrorActionPreference = 'Stop'

Write-Host "==> Loading azd environment"
foreach ($line in (azd env get-values)) {
  if ($line -match '^\s*([A-Z0-9_]+)="?(.*?)"?\s*$') {
    [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
  }
}
$env:AZURE_SUBSCRIPTION_ID = (azd env get-value AZURE_SUBSCRIPTION_ID)

Write-Host "==> Installing helper dependencies"
python -m pip install --quiet --disable-pip-version-check -r scripts/requirements.txt

Write-Host "==> Loading SQL schema (Entra auth via sqlcmd)"
if (Get-Command sqlcmd -ErrorAction SilentlyContinue) {
  sqlcmd -S $env:AZURE_SQL_SERVER_FQDN -d $env:AZURE_SQL_DATABASE `
    --authentication-method ActiveDirectoryDefault -i scripts/schema.sql
} else {
  Write-Warning "sqlcmd (go-sqlcmd) not found - skipping. Run scripts/schema.sql manually."
}

Write-Host "==> Building the AI Search index pipeline"
python scripts/setup_search.py

Write-Host "==> Creating the Foundry agent"
$agentLine = (python scripts/create_agent.py)
$agentId = ($agentLine -replace '^AGENT_ID=', '').Trim()
Write-Host "   agent: $agentId"
azd env set AGENT_ID $agentId

Write-Host "==> Pushing AGENT_ID to the running services"
az functionapp config appsettings set -g $env:AZURE_RESOURCE_GROUP -n $env:SERVICE_API_NAME `
  --settings "AGENT_ID=$agentId" --output none
az containerapp update -g $env:AZURE_RESOURCE_GROUP -n $env:SERVICE_WEB_NAME `
  --set-env-vars "AGENT_ID=$agentId" --output none

Write-Host "==> postprovision complete"
