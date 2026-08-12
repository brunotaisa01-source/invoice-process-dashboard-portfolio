Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\PackEnv.ps1"

Initialize-PackEnvironment -RequireDashboardDb | Out-Null

if ($env:ALLOW_FULL -ne "YES") {
    Write-Host "[FAIL] RUN_FULL is gated. Set ALLOW_FULL=YES only after operator approval for a pack-local run."
    exit 2
}

Write-Host "[WARN] RUN_FULL is intentionally not wired in the initial scaffold."
Write-Host "[WARN] It must stay pack-local and must not publish to shared destinations."
Write-Host "[WARN] Any future RUN_FULL implementation must apply Production Overrides and SLA tracker snapshots before dashboard export, then export with --no-deploy."
exit 3
