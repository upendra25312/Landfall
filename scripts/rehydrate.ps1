# Landfall - rehydrate a torn-down deployment (PRD E13.11 / section 4.15).
#
#   ./scripts/rehydrate.ps1 -Backup <dir> [-Engagements a/b,c/d]
#
# 1. asserts the resource group is GONE (not an update path - use `azd deploy`;
#    `azd up` on a live env re-runs postprovision, which DROPs the SQL schema).
# 2. `azd up` - full stack. Set these once (they persist in .azure/<env>/):
#       azd env set DEPLOY_DRAWIO true
#       azd env set WEB_AUTH_CLIENT_ID <app-id>
#       azd env set --secret WEB_AUTH_CLIENT_SECRET
# 3. re-versions the Foundry agent.
# 4. prints how to re-import engagements (import API is behind Easy Auth).
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Backup,
  [string[]]$Engagements = @()
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $Backup 'manifest.json'))) { Write-Error "$Backup/manifest.json not found"; exit 1 }
if (-not (Get-Command azd -ErrorAction SilentlyContinue)) { Write-Error "azd not on PATH"; exit 1 }

$RG = ''
try { $RG = (azd env get-value AZURE_RESOURCE_GROUP 2>$null).Trim() } catch {}
if ($RG) {
  az group show -n $RG 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Error "$RG already exists. rehydrate is for a torn-down env. For a code update use 'azd deploy api|web|calc|drawio'."
    exit 1
  }
}

$dd = 'false'; $wa = ''
try { $dd = (azd env get-value DEPLOY_DRAWIO 2>$null).Trim() } catch {}
try { $wa = (azd env get-value WEB_AUTH_CLIENT_ID 2>$null).Trim() } catch {}
$waState = if ($wa) { 'set' } else { 'EMPTY (no web auth)' }
Write-Host "==> Stack switches:  DEPLOY_DRAWIO=$dd  WEB_AUTH_CLIENT_ID=$waState"
if ($dd -ne 'true') { Write-Host "   (ca-drawio will NOT deploy - 'azd env set DEPLOY_DRAWIO true' then re-run to include it)" }

Write-Host "==> azd up  (full stack; ~8-12 min cold)"
azd up

Write-Host "==> Re-versioning the Foundry agent"
try { python scripts/create_agent.py } catch { Write-Host "   (create_agent.py failed - run it by hand once the env is loaded)" }

Write-Host "==> Post-deploy smoke (+ cold-start timing)"
try { python scripts/smoke.py --cold } catch { Write-Host "   (smoke reported issues - inspect above)" }

$web = ''
try { $web = (azd env get-value SERVICE_WEB_URI 2>$null).Trim() } catch {}
Write-Host ""
Write-Host "==> Stack is back: $web"
Write-Host "    Re-import engagements from $Backup via the dashboard's  ^ import  button:"
Get-ChildItem (Join-Path $Backup '*.landfall.zip') -ErrorAction SilentlyContinue |
  ForEach-Object { "        $($_.Name)" } | Write-Host
if ($Engagements.Count) { Write-Host "    (you asked for: $($Engagements -join ', '))" }
