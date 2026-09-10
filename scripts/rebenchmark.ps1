<#
.SYNOPSIS
    Runs the Landfall Quarterly Price, SKU & Cloud Adoption Framework (CAF) Re-benchmark (S2).

.DESCRIPTION
    Executes the FinOps audit comparing Landfall's pinned VM SKU catalog and pricing book
    against live Azure Retail Prices API rates and Microsoft CAF baselines. Generates a dated
    markdown audit report in evidence/benchmarks/.

.PARAMETER Region
    Target Azure deployment region (default: "swedencentral").

.PARAMETER Offline
    Run against offline deterministic fixtures ($0 spend, zero network calls).

.PARAMETER Strict
    Exit with non-zero code if any price drift exceeds tolerance.

.EXAMPLE
    .\scripts\rebenchmark.ps1 -Offline
    .\scripts\rebenchmark.ps1 -Region swedencentral
#>
[CmdletBinding()]
param(
    [string]$Region = "swedencentral",
    [switch]$Offline,
    [switch]$Strict,
    [string]$Out = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

$Python = Join-Path $RepoRoot ".venv2\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$Script = Join-Path $RepoRoot "scripts\rebenchmark_prices.py"

$ArgsList = @($Script, "--region", $Region)
if ($Offline) {
    $ArgsList += "--offline"
}
if ($Strict) {
    $ArgsList += "--strict"
}
if ($Out) {
    $ArgsList += @("--out", $Out)
}

Write-Host "==> Running Landfall Quarterly Re-benchmark (S2)..." -ForegroundColor Cyan
Write-Host "    Region:  $Region" -ForegroundColor DarkGray
Write-Host "    Offline: $Offline" -ForegroundColor DarkGray

& $Python @ArgsList
$ExitCode = $LASTEXITCODE

if ($ExitCode -eq 0) {
    Write-Host "==> Re-benchmark completed successfully (status: APPROVED)." -ForegroundColor Green
} else {
    Write-Warning "==> Re-benchmark completed with warnings or drift detected (exit code: $ExitCode)."
}

exit $ExitCode

