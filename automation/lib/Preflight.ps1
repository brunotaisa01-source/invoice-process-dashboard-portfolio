Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\PackEnv.ps1"

$envInfo = Initialize-PackEnvironment -RequireDashboardDb
$forbiddenNames = @(".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "htmlcov", "playwright-report", "test-results")
$found = @()

foreach ($name in $forbiddenNames) {
    $found += Get-ChildItem -LiteralPath $envInfo.PackRoot -Force -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $name } |
        Select-Object -ExpandProperty FullName
}

if ($found.Count -gt 0) {
    Write-Host "[FAIL] Forbidden directories found in pack:"
    $found | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" }
    exit 2
}

foreach ($path in @($env:INVOICE_DASHBOARD_DEPLOY_DIR, $env:INVOICE_DASHBOARD_CALENDAR_DIR, $env:INVOICE_DASHBOARD_PRODUCTION_OVERRIDES_DIR)) {
    $privateDrivePrefix = ([char]83) + ":" + [char]92
    if ($path.StartsWith($privateDrivePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "[FAIL] Automation target uses a prohibited mapped drive: $path"
        exit 2
    }
}

$automationFiles = Get-ChildItem -LiteralPath (Join-Path $envInfo.PackRoot "automation") -Recurse -File -ErrorAction SilentlyContinue
$drivePattern = ([char]83) + ":" + [char]92
$automationHits = $automationFiles | Select-String -Pattern $drivePattern -SimpleMatch -ErrorAction SilentlyContinue
if ($automationHits) {
    Write-Host "[FAIL] Automation files contain prohibited mapped-drive references:"
    $automationHits | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber)" }
    exit 2
}

$python = Get-PackPython
if ($python -eq "py") {
    & py -3 -B -c "import sqlite3, pandas, openpyxl" 2>&1 | Out-Null
} else {
    & $python -B -c "import sqlite3, pandas, openpyxl" 2>&1 | Out-Null
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Python runtime cannot import the local ETL dependencies:"
    Write-Host "       `"$python`" -m pip install -r `"$($envInfo.PackRoot)\requirements.txt`""
    exit 2
}

$requiredPaths = @(
    "scripts",
    "sql",
    "libs",
    "dashboard\index.html",
    "dashboard\data.js",
    "dashboard\css",
    "dashboard\dist",
    "dashboard\data_chunks",
    "dashboard\Calendar\pending",
    "dashboard\Calendar\processed",
    "dashboard\Calendar\rejected",
    "dashboard\ProductionOverrides\pending",
    "dashboard\ProductionOverrides\processed",
    "dashboard\ProductionOverrides\rejected",
    "dashboard\data\invoices.db",
    "runtime\logs",
    "runtime\locks",
    "runtime\manifests"
)

$missing = @()
foreach ($rel in $requiredPaths) {
    $target = Join-Path $envInfo.PackRoot $rel
    if (-not (Test-Path -LiteralPath $target)) {
        $missing += $rel
    }
}

if ($missing.Count -gt 0) {
    Write-Host "[FAIL] Required pack paths missing:"
    $missing | ForEach-Object { Write-Host "  $_" }
    exit 2
}

Write-Host "[OK] Pack root: $($envInfo.PackRoot)"
Write-Host "[OK] Deploy dir: $env:INVOICE_DASHBOARD_DEPLOY_DIR"
Write-Host "[OK] Calendar dir: $env:INVOICE_DASHBOARD_CALENDAR_DIR"
Write-Host "[OK] ProductionOverrides dir: $env:INVOICE_DASHBOARD_PRODUCTION_OVERRIDES_DIR"
Write-Host "[OK] SLA input: pack-local fixture snapshots (remote sync requires explicit override)."
Write-Host "[OK] Local ETL dependency imports passed."
Write-Host "[OK] Dashboard DB copy: $($envInfo.PackDashboardDb)"
Write-Host "[OK] Runtime DB env path: $env:INVOICE_DASHBOARD_DB_PATH"
Write-Host "[OK] Preflight passed."
