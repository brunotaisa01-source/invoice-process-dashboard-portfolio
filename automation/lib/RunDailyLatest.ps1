Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\PackEnv.ps1"
. "$PSScriptRoot\ApplyPackDashboardPatch.ps1"

function ConvertTo-FullPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-PackLocalPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string[]] $AllowedRoots
    )

    $fullPath = ConvertTo-FullPath -Path $Path
    $privateDrivePrefix = ([char]83) + ":" + [char]92
    if ($fullPath.StartsWith($privateDrivePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Name points to a prohibited mapped drive: $fullPath"
    }

    foreach ($root in $AllowedRoots) {
        $fullRoot = (ConvertTo-FullPath -Path $root).TrimEnd("\")
        if ($fullPath.StartsWith($fullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $fullPath
        }
    }

    throw "$Name is outside allowed pack/local roots: $fullPath"
}

function Invoke-PackPythonCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $python = Get-PackPython
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($python -eq "py") {
            $output = & py -3 @Arguments 2>&1
        } else {
            $output = & $python @Arguments 2>&1
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }

    return $output
}

function Test-SqliteIntegrity {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $code = "import sqlite3, sys; conn = sqlite3.connect(sys.argv[1]); print(conn.execute('pragma integrity_check').fetchone()[0]); conn.close()"
    $result = (Invoke-PackPythonCapture -Arguments @("-c", $code, $Path) | Select-Object -Last 1).ToString().Trim()
    if ($result -ne "ok") {
        throw "SQLite integrity_check failed for ${Path}: ${result}"
    }
    return $result
}

function Get-ImportSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string] $DbPath,
        [Parameter(Mandatory = $true)]
        [string] $ExtractionDate
    )

    $code = @'
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
extraction_date = sys.argv[2]
columns = {row[1] for row in conn.execute('pragma table_info(weekly_imports)').fetchall()}
has_entry_range = {'entry_date_min', 'entry_date_max'}.issubset(columns)

def with_entry_range(row):
    if row is None:
        return None
    values = list(row)
    if has_entry_range:
        return values
    date_key = values[0]
    entry_min, entry_max = conn.execute(
        'select min(entry_date), max(entry_date) from invoices where extraction_date = ?',
        (date_key,),
    ).fetchone()
    return values[:3] + [entry_min, entry_max] + values[3:]

select_cols = 'extraction_date, week_start, week_end, entry_date_min, entry_date_max, total_rows' if has_entry_range else 'extraction_date, week_start, week_end, total_rows'
requested = conn.execute(
    f'select {select_cols} from weekly_imports where extraction_date = ?',
    (extraction_date,),
).fetchone()
requested_count = conn.execute(
    'select count(*) from invoices where extraction_date = ?',
    (extraction_date,),
).fetchone()[0] if requested is not None else 0
latest = conn.execute(
    f'select {select_cols} from weekly_imports order by extraction_date desc limit 1'
).fetchone()
print(json.dumps({
    'requested': with_entry_range(requested),
    'requested_invoice_rows': requested_count,
    'latest': with_entry_range(latest),
}, ensure_ascii=True))
conn.close()
'@
    $json = (Invoke-PackPythonCapture -Arguments @("-c", $code, $DbPath, $ExtractionDate) | Select-Object -Last 1).ToString()
    return $json | ConvertFrom-Json
}

function Copy-SqliteAtomic {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Source,
        [Parameter(Mandatory = $true)]
        [string] $Destination,
        [Parameter(Mandatory = $true)]
        [string] $Label,
        [Parameter(Mandatory = $true)]
        [string] $Stamp
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        throw "${Label}: source DB missing: $Source"
    }

    $destinationDir = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null

    $destinationName = Split-Path -Leaf $Destination
    $tmp = Join-Path $destinationDir (".${destinationName}.${Stamp}.tmp")
    $backup = Join-Path $destinationDir ("${destinationName}.${Stamp}.bak")

    try {
        Copy-Item -LiteralPath $Source -Destination $tmp -Force
        Test-SqliteIntegrity -Path $tmp | Out-Null

        if (Test-Path -LiteralPath $Destination) {
            try {
                [System.IO.File]::Replace($tmp, $Destination, $backup, $true)
            } catch {
                Move-Item -LiteralPath $Destination -Destination $backup -Force
                Move-Item -LiteralPath $tmp -Destination $Destination -Force
            }
            Write-Host "[OK] ${Label}: replaced $Destination (backup: $backup)"
        } else {
            Move-Item -LiteralPath $tmp -Destination $Destination -Force
            Write-Host "[OK] ${Label}: created $Destination"
        }

        Test-SqliteIntegrity -Path $Destination | Out-Null
        if (Test-Path -LiteralPath $backup) {
            Remove-Item -LiteralPath $backup -Force
            Write-Host "[OK] ${Label}: removed transient backup $backup"
        }
        return $null
    } finally {
        if (Test-Path -LiteralPath $tmp) {
            Remove-Item -LiteralPath $tmp -Force
        }
    }
}

function Clear-SlaTrackerData {
    param(
        [Parameter(Mandatory = $true)]
        [object] $EnvInfo
    )

    $clearScript = Join-Path $PSScriptRoot "ClearSlaTrackerData.py"
    if (-not (Test-Path -LiteralPath $clearScript)) {
        throw "SLA clear helper missing: $clearScript"
    }

    Invoke-PackPython -Arguments @(
        $clearScript,
        "--db", $EnvInfo.RuntimeDbPath
    )
}

function Get-LatestExtraction {
    param(
        [Parameter(Mandatory = $true)]
        [string] $PackRoot
    )

    $datePattern = "^(.+)_(\d{2})_(\d{2})_(\d{4})\.xlsx$"
    $candidateFiles = @()

    foreach ($folder in @("data\incoming", "data\archive")) {
        $path = Join-Path $PackRoot $folder
        if (Test-Path -LiteralPath $path) {
            $candidateFiles += Get-ChildItem -LiteralPath $path -Recurse -File -Filter "*.xlsx" |
                Where-Object { $_.Name -match $datePattern }
        }
    }

    if ($candidateFiles.Count -eq 0) {
        throw "No ERP files found in pack data/incoming or data/archive."
    }

    $latest = $candidateFiles |
        ForEach-Object {
            if ($_.Name -match $datePattern) {
                $dateText = "{0}_{1}_{2}" -f $Matches[2], $Matches[3], $Matches[4]
                [pscustomobject]@{
                    File = $_
                    Date = [datetime]::ParseExact($dateText, "dd_MM_yyyy", [System.Globalization.CultureInfo]::InvariantCulture)
                    Arg = $dateText
                    Iso = "{0}-{1}-{2}" -f $Matches[4], $Matches[3], $Matches[2]
                }
            }
        } |
        Sort-Object Date -Descending |
        Select-Object -First 1

    $filesForDate = $candidateFiles | Where-Object { $_.Name -like "*_$($latest.Arg).xlsx" }
    $filenamePrefixes = $filesForDate | ForEach-Object {
        if ($_.Name -match $datePattern) { $Matches[1] }
    } | Sort-Object -Unique

    return [pscustomobject]@{
        Arg = $latest.Arg
        Iso = $latest.Iso
        Files = $filesForDate
        FilenamePrefixes = $filenamePrefixes
    }
}

function Acquire-DailyLock {
    param(
        [Parameter(Mandatory = $true)]
        [string] $LockPath,
        [Parameter(Mandatory = $true)]
        [string] $Stamp
    )

    $lockDir = Split-Path -Parent $LockPath
    New-Item -ItemType Directory -Force -Path $lockDir | Out-Null
    try {
        $stream = [System.IO.FileStream]::new(
            $LockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    } catch {
        throw "RUN_DAILY lock is already held or cannot be acquired: $LockPath"
    }

    $payload = "pid=$PID`nstamp=$Stamp`nstarted=$(Get-Date -Format o)`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $stream.SetLength(0)
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
    return $stream
}

function ConvertTo-PublicLogMessage {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Message,
        [Parameter(Mandatory = $true)]
        [string] $PackRoot
    )

    $sanitized = $Message
    $replacementValues = @(
        [pscustomobject]@{ Value = $PackRoot; Replacement = "<PACK_ROOT>" },
        [pscustomobject]@{ Value = [Environment]::GetFolderPath("UserProfile"); Replacement = "<USER_PROFILE>" },
        [pscustomobject]@{ Value = "$env:USERDOMAIN\$env:USERNAME"; Replacement = "<HOST_IDENTITY>" },
        [pscustomobject]@{ Value = $env:USERNAME; Replacement = "<HOST_IDENTITY>" },
        [pscustomobject]@{ Value = $env:USERDOMAIN; Replacement = "<HOST_IDENTITY>" }
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_.Value) } |
        Sort-Object { $_.Value.Length } -Descending

    foreach ($item in $replacementValues) {
        $sanitized = [regex]::Replace(
            $sanitized,
            [regex]::Escape($item.Value),
            $item.Replacement,
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }

    return [regex]::Replace(
        $sanitized,
        "(?im)(?<![a-z0-9])[a-z]:[\\/][^\r\n]*",
        "<ABSOLUTE_PATH>"
    )
}

function Write-DailyEvent {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("INFO", "OK", "WARN", "FAIL")]
        [string] $Level,
        [Parameter(Mandatory = $true)]
        [string] $Message,
        [Parameter(Mandatory = $true)]
        [string] $PackRoot,
        [Parameter(Mandatory = $true)]
        [string] $LogPath
    )

    $safeMessage = ConvertTo-PublicLogMessage -Message $Message -PackRoot $PackRoot
    foreach ($line in ($safeMessage -split "\r?\n")) {
        $entry = "$(Get-Date -Format o) [$Level] $line"
        [System.IO.File]::AppendAllText(
            $LogPath,
            $entry + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
        Write-Host "[$Level] $line"
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$envInfo = Initialize-PackEnvironment -RequireDashboardDb
$runtimeDir = Join-Path $envInfo.PackRoot "runtime"
$logDir = Join-Path $runtimeDir "logs"
$lockDir = Join-Path $runtimeDir "locks"
New-Item -ItemType Directory -Force -Path $logDir, $lockDir | Out-Null

$logPath = Join-Path $logDir "run_daily_${stamp}.log"
$lockPath = Join-Path $lockDir "run_daily.lock"
$lockStream = $null
$exitCode = 0
[System.IO.File]::WriteAllText($logPath, "", [System.Text.UTF8Encoding]::new($false))

try {
    Write-DailyEvent -Level "INFO" -Message "RUN_DAILY started: stamp=$stamp" -PackRoot $envInfo.PackRoot -LogPath $logPath

    $lockStream = Acquire-DailyLock -LockPath $lockPath -Stamp $stamp
    Write-DailyEvent -Level "OK" -Message "RUN_DAILY lock acquired: runtime\locks\run_daily.lock" -PackRoot $envInfo.PackRoot -LogPath $logPath

    $localRoot = $envInfo.PackRoot
    Assert-PackLocalPath -Name "Runtime DB" -Path $envInfo.RuntimeDbPath -AllowedRoots @($localRoot) | Out-Null
    Assert-PackLocalPath -Name "Deploy dir" -Path $envInfo.DashboardDir -AllowedRoots @($envInfo.PackRoot) | Out-Null
    Assert-PackLocalPath -Name "Calendar dir" -Path $envInfo.CalendarDir -AllowedRoots @($envInfo.PackRoot) | Out-Null
    Assert-PackLocalPath -Name "ProductionOverrides dir" -Path $envInfo.ProductionOverridesDir -AllowedRoots @($envInfo.PackRoot) | Out-Null
    Assert-PackLocalPath -Name "SLA snapshot dir" -Path $envInfo.SlaSnapshotDir -AllowedRoots @($localRoot) | Out-Null
    Write-DailyEvent -Level "OK" -Message "Kill-switch env vars are pack/local only." -PackRoot $envInfo.PackRoot -LogPath $logPath

    Write-DailyEvent -Level "OK" -Message "Daily input mode: LOCAL_SYNTHETIC (committed two-row fixture)." -PackRoot $envInfo.PackRoot -LogPath $logPath
    Write-DailyEvent -Level "WARN" -Message "External integration boundary: RED_EXTERNAL_GATE." -PackRoot $envInfo.PackRoot -LogPath $logPath
    Invoke-PackPython -Arguments @("-B", "-m", "scripts.bootstrap_local")
    Write-DailyEvent -Level "OK" -Message "Local fixture bootstrap completed." -PackRoot $envInfo.PackRoot -LogPath $logPath
    Invoke-PackPython -Arguments @(
        "-B", "-m", "scripts.etl.apply_calendar_absences",
        "--db", $envInfo.RuntimeDbPath,
        "--pending-dir", (Join-Path $envInfo.CalendarDir "pending"),
        "--processed-dir", (Join-Path $envInfo.CalendarDir "processed"),
        "--rejected-dir", (Join-Path $envInfo.CalendarDir "rejected")
    )
    Write-DailyEvent -Level "OK" -Message "Calendar pending inputs applied." -PackRoot $envInfo.PackRoot -LogPath $logPath
    Invoke-PackPython -Arguments @(
        "-B", "-m", "scripts.etl.apply_production_overrides",
        "--db", $envInfo.RuntimeDbPath,
        "--pending-dir", (Join-Path $envInfo.ProductionOverridesDir "pending"),
        "--processed-dir", (Join-Path $envInfo.ProductionOverridesDir "processed"),
        "--rejected-dir", (Join-Path $envInfo.ProductionOverridesDir "rejected")
    )
    Write-DailyEvent -Level "OK" -Message "Production override pending inputs applied." -PackRoot $envInfo.PackRoot -LogPath $logPath
    Clear-SlaTrackerData -EnvInfo $envInfo
    Write-DailyEvent -Level "OK" -Message "Pack-local SLA tracker data cleared." -PackRoot $envInfo.PackRoot -LogPath $logPath
    Test-SqliteIntegrity -Path $envInfo.RuntimeDbPath | Out-Null
    Copy-SqliteAtomic -Source $envInfo.RuntimeDbPath -Destination $envInfo.PackDashboardDb -Label "dashboard mirror" -Stamp $stamp | Out-Null
    Write-DailyEvent -Level "OK" -Message "Dashboard database mirror refreshed: dashboard\data\invoices.db" -PackRoot $envInfo.PackRoot -LogPath $logPath
    Invoke-PackPython -Arguments @("-B", "-m", "scripts.dashboard.export_dashboard", "--force-html", "--no-deploy")
    Write-DailyEvent -Level "OK" -Message "Dashboard exporter completed in local-only mode." -PackRoot $envInfo.PackRoot -LogPath $logPath
    Invoke-PackDashboardPatch -DashboardDir $envInfo.DashboardDir
    Write-DailyEvent -Level "OK" -Message "Pack dashboard patch applied." -PackRoot $envInfo.PackRoot -LogPath $logPath

    Test-SqliteIntegrity -Path $envInfo.RuntimeDbPath | Out-Null
    $after = Get-ImportSummary -DbPath $envInfo.RuntimeDbPath -ExtractionDate "2026-08-14"
    Test-SqliteIntegrity -Path $envInfo.PackDashboardDb | Out-Null

    Write-DailyEvent -Level "OK" -Message "DB integrity: ok" -PackRoot $envInfo.PackRoot -LogPath $logPath
    Write-DailyEvent -Level "OK" -Message "Daily result: requested=$($after.requested -join ', ') invoice_rows=$($after.requested_invoice_rows)" -PackRoot $envInfo.PackRoot -LogPath $logPath
    Write-DailyEvent -Level "OK" -Message "Latest DB row: $($after.latest -join ', ')" -PackRoot $envInfo.PackRoot -LogPath $logPath
    Write-DailyEvent -Level "OK" -Message "Dashboard exported in pack: dashboard" -PackRoot $envInfo.PackRoot -LogPath $logPath
    Write-DailyEvent -Level "INFO" -Message "Log: runtime\logs\run_daily_${stamp}.log" -PackRoot $envInfo.PackRoot -LogPath $logPath
} catch {
    $exitCode = 1
    Write-DailyEvent -Level "FAIL" -Message "RUN_DAILY failed: $($_.Exception.Message)" -PackRoot $envInfo.PackRoot -LogPath $logPath
} finally {
    if ($null -ne $lockStream) {
        $lockStream.Close()
        $lockStream.Dispose()
        if (Test-Path -LiteralPath $lockPath) {
            Remove-Item -LiteralPath $lockPath -Force
        }
        Write-DailyEvent -Level "OK" -Message "RUN_DAILY lock released: runtime\locks\run_daily.lock" -PackRoot $envInfo.PackRoot -LogPath $logPath
    }
    Write-DailyEvent -Level "OK" -Message "RUN_DAILY completed: exit_code=$exitCode" -PackRoot $envInfo.PackRoot -LogPath $logPath
}

exit $exitCode
