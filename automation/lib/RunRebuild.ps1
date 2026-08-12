Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\PackEnv.ps1"

Initialize-PackEnvironment -RequireDashboardDb | Out-Null

if ($env:ALLOW_REBUILD -ne "YES") {
    Write-Host "[FAIL] RUN_REBUILD is gated. Set ALLOW_REBUILD=YES only after operator approval for a pack-local rebuild."
    exit 2
}

Write-Host "[WARN] RUN_REBUILD is intentionally not wired in the initial scaffold."
Write-Host "[WARN] Rebuild would delete and recreate pack-local DB state; no rebuild is executed."
Write-Host "[WARN] Any future RUN_REBUILD implementation must apply Production Overrides and SLA tracker snapshots before dashboard export, then export with --no-deploy."
exit 3
