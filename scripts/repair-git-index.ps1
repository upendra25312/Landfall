# Landfall: Automated Git Index Repair Utility
# Solves: fatal: .git/index: index file smaller than expected

$indexPath = Join-Path $PSScriptRoot "..\.git\index"

if (Test-Path $indexPath) {
    $len = (Get-Item $indexPath).Length
    if ($len -eq 0 -or $len -lt 12) {
        Write-Host "Detected corrupted/truncated .git/index ($len bytes). Rebuilding..." -ForegroundColor Yellow
        Remove-Item $indexPath -Force
        git reset
        git checkout .
        Write-Host "Git index successfully restored from HEAD." -ForegroundColor Green
    } else {
        Write-Host "Git index is healthy ($len bytes)." -ForegroundColor Green
    }
} else {
    Write-Host ".git/index not found. Running git reset to restore..." -ForegroundColor Yellow
    git reset
    git checkout .
    Write-Host "Git index created." -ForegroundColor Green
}
