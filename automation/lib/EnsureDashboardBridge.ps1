param(
    [switch] $OpenBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\PackEnv.ps1"

$envInfo = Initialize-PackEnvironment -RequireDashboardDb
$index = Join-Path $envInfo.DashboardDir "index.html"
$serverScript = Join-Path $PSScriptRoot "dashboard_server.py"
$calendarPendingDir = Join-Path $envInfo.CalendarDir "pending"
$productionPendingDir = Join-Path $envInfo.ProductionOverridesDir "pending"

function Get-PackId {
    param([string] $Path)

    $normalized = [System.IO.Path]::GetFullPath($Path).ToLowerInvariant()
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
        return ([System.BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant().Substring(0, 16)
    } finally {
        $sha256.Dispose()
    }
}

$expectedPackId = Get-PackId -Path $envInfo.DashboardDir

if (-not (Test-Path -LiteralPath $index)) {
    throw "Dashboard index missing: $index"
}
if (-not (Test-Path -LiteralPath $serverScript)) {
    throw "Dashboard bridge missing: $serverScript"
}
New-Item -ItemType Directory -Force -Path $calendarPendingDir | Out-Null
New-Item -ItemType Directory -Force -Path $productionPendingDir | Out-Null

$serverLogDir = if ($env:INVOICE_DASHBOARD_LOG_DIR) {
    $env:INVOICE_DASHBOARD_LOG_DIR
} else {
    Join-Path ([System.IO.Path]::GetTempPath()) "invoice-process-dashboard-server"
}
New-Item -ItemType Directory -Force -Path $serverLogDir | Out-Null

function Test-DashboardServer {
    param([int] $Port)

    try {
        $baseUrl = "http://127.0.0.1:$Port"
        $health = Invoke-RestMethod -Uri "$baseUrl/__health" -Method Get -TimeoutSec 2
        $response = Invoke-WebRequest -Uri "$baseUrl/" -UseBasicParsing -TimeoutSec 2
        return $health.ok -eq $true -and $health.bridge_version -ge 3 -and $health.pack_id -eq $expectedPackId -and $response.StatusCode -eq 200 -and $response.Content.Contains("Invoice Process Dashboard")
    } catch {
        return $false
    }
}

function Stop-StaleDashboardBridge {
    $dashboardPattern = [regex]::Escape($envInfo.DashboardDir)
    $staleProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match "dashboard_server\.py" -and
            $_.CommandLine -match $dashboardPattern -and
            $_.CommandLine -notmatch ("--pack-id\s+" + [regex]::Escape($expectedPackId))
        }
    foreach ($process in $staleProcesses) {
        Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Removed stale dashboard bridge process: $($process.ProcessId)"
    }
}

$pythonCommand = Get-PackPython
$pythonPath = (Get-Command $pythonCommand -ErrorAction Stop).Source
$port = $null
Stop-StaleDashboardBridge
foreach ($candidatePort in 8765..8785) {
    $candidateListener = Get-NetTCPConnection -LocalPort $candidatePort -State Listen -ErrorAction SilentlyContinue
    if ($candidateListener -and (Test-DashboardServer -Port $candidatePort)) {
        $port = $candidatePort
        break
    }
}

if ($null -eq $port) {
    $port = 8765
    while ((Test-DashboardServer -Port $port) -eq $false) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $listener) {
            $arguments = @()
            if ($pythonCommand -eq "py") {
                $arguments += "-3.11"
            }
            $arguments += @(
                ('"' + $serverScript + '"'),
                "--dashboard-dir",
                ('"' + $envInfo.DashboardDir + '"'),
                "--calendar-pending-dir",
                ('"' + $calendarPendingDir + '"'),
                "--production-pending-dir",
                ('"' + $productionPendingDir + '"'),
                "--pack-id",
                $expectedPackId,
                "--bind",
                "127.0.0.1",
                "--port",
                "$port"
            )
            $stdout = Join-Path $serverLogDir "dashboard_server.out.log"
            $stderr = Join-Path $serverLogDir "dashboard_server.err.log"
            Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $envInfo.DashboardDir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
            Start-Sleep -Milliseconds 400
            break
        }
        $port += 1
        if ($port -gt 8785) {
            throw "No free local dashboard port found between 8765 and 8785."
        }
    }
}

if (-not (Test-DashboardServer -Port $port)) {
    throw "Local dashboard bridge did not start. Check $serverLogDir."
}

$url = "http://127.0.0.1:$port/"
if ($OpenBrowser) {
    Start-Process -FilePath $url
    Write-Host "[OK] Opened dashboard over local HTTP: $url"
} else {
    Write-Host "[OK] Dashboard bridge ready: $url"
}
