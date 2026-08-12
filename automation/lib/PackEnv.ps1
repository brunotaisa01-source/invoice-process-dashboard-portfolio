Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PackRoot {
    $scriptPath = $PSScriptRoot
    return (Resolve-Path (Join-Path $scriptPath "..\..")).Path
}

function Initialize-PackEnvironment {
    param(
        [switch] $RequireDashboardDb
    )

    $packRoot = Get-PackRoot
    $dashboardDir = Join-Path $packRoot "dashboard"
    $calendarDir = Join-Path $dashboardDir "Calendar"
    $productionOverridesDir = Join-Path $dashboardDir "ProductionOverrides"
    $runtimeDbPath = Join-Path $packRoot "db\invoices.db"
    $slaSnapshotDir = Join-Path $packRoot "data\sla_tracker_snapshots"
    $packDashboardDb = Join-Path $dashboardDir "data\invoices.db"

    $env:INVOICE_DASHBOARD_DB_PATH = $runtimeDbPath
    $env:INVOICE_DASHBOARD_DEPLOY_DIR = $dashboardDir
    $env:INVOICE_DASHBOARD_CALENDAR_DIR = $calendarDir
    $env:INVOICE_DASHBOARD_PRODUCTION_OVERRIDES_DIR = $productionOverridesDir
    $env:INVOICE_DASHBOARD_SLA_TRACKER_SNAPSHOT_DIR = $slaSnapshotDir
    $env:PYTHONPATH = $packRoot
    $env:PYTHONDONTWRITEBYTECODE = "1"

    if ($RequireDashboardDb -and -not (Test-Path -LiteralPath $packDashboardDb)) {
        throw "Pack dashboard DB missing: $packDashboardDb"
    }

    return [pscustomobject]@{
        PackRoot = $packRoot
        DashboardDir = $dashboardDir
        CalendarDir = $calendarDir
        ProductionOverridesDir = $productionOverridesDir
        RuntimeDbPath = $runtimeDbPath
        SlaSnapshotDir = $slaSnapshotDir
        SlaSiteUrl = $env:INVOICE_DASHBOARD_SLA_SITE_URL
        PackDashboardDb = $packDashboardDb
    }
}

function Get-PackPython {
    $candidates = @()
    if ($env:INVOICE_DASHBOARD_PYTHON) {
        $candidates += $env:INVOICE_DASHBOARD_PYTHON
    }
    $candidates += @("py", "python")

    foreach ($candidate in $candidates) {
        if ($candidate -in @("py", "python")) {
            $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
            if ($null -ne $cmd) {
                return $candidate
            }
        } elseif (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "No Python runtime found. Set INVOICE_DASHBOARD_PYTHON or place Python on PATH."
}

function Invoke-PackPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $python = Get-PackPython
    if ($python -eq "py") {
        & py -3 @Arguments
    } else {
        & $python @Arguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}
