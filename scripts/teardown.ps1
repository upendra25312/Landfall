# Landfall - safe close-out (PRD E13.11 / section 4.15).
#
#   ./scripts/teardown.ps1 [-Backup <dir>]
#
# Exports EVERY engagement (blobs + SQL) to a retained directory, checksums it,
# and ONLY THEN runs `azd down --purge`. Stops before touching the deployment if
# the export fails, is empty, or any engagement fails - no silent data loss.
# The backup is the input to rehydrate.ps1. Keep it.
[CmdletBinding()]
param(
  [string]$Backup = "_closeout/$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
)
$ErrorActionPreference = 'Stop'

foreach ($t in 'azd','az') {
  if (-not (Get-Command $t -ErrorAction SilentlyContinue)) { Write-Error "$t not on PATH"; exit 1 }
}

Write-Host "==> Loading azd environment"
$RG = (azd env get-value AZURE_RESOURCE_GROUP).Trim()
if (-not $RG) { Write-Error "no AZURE_RESOURCE_GROUP in the azd env"; exit 1 }

az group show -n $RG 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "==> $RG does not exist - already torn down."; exit 0 }

Write-Host "==> Exporting every engagement to $Backup  (blobs + SQL)"
python scripts/export_all.py --out $Backup --sql
if ($LASTEXITCODE -ne 0) { Write-Error "export_all.py failed - ABORT, not tearing down"; exit 1 }

$manifest = Join-Path $Backup 'manifest.json'
if (-not (Test-Path $manifest)) { Write-Error "$manifest not written - ABORT"; exit 1 }
$m = Get-Content $manifest -Raw | ConvertFrom-Json
$exported = @($m.engagements).Count
$failed   = @($m.failed).Count
Write-Host "==> Exported $exported engagement(s); $failed failed"
if ($failed -ne 0) { Write-Error "$failed engagement(s) failed to export - ABORT"; exit 1 }

Write-Host "==> Checksumming the archive"
Get-ChildItem (Join-Path $Backup '*.landfall.zip') -ErrorAction SilentlyContinue |
  Get-FileHash -Algorithm SHA256 |
  ForEach-Object { "{0}  {1}" -f $_.Hash, (Split-Path $_.Path -Leaf) } |
  Set-Content (Join-Path $Backup 'SHA256SUMS')

Write-Host ""
Write-Host "==> Export OK. Tearing down $RG with --purge in 10s. Ctrl-C to abort."
Start-Sleep -Seconds 10
azd down --force --purge

az group show -n $RG 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Error "$RG still exists after 'azd down --purge' - INCOMPLETE"; exit 1 }

Write-Host ""
Write-Host "==> $RG destroyed. Meter stopped."
Write-Host "    Backup: $Backup  ($exported engagement(s))"
Write-Host "    Bring it back with:  ./scripts/rehydrate.ps1 -Backup $Backup"
