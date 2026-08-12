param(
    [Parameter(Mandatory = $true)]
    [string] $ExpectedPython
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\PackEnv.ps1"

$envInfo = Initialize-PackEnvironment
$pythonPath = [System.IO.Path]::GetFullPath($ExpectedPython)

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host "[FAIL] Pinned WinPython runtime not found:"
    Write-Host "       $pythonPath"
    Write-Host "[INFO] This operator pack does not download installers automatically."
    Write-Host "[INFO] Pass an explicit local Python executable path."
    exit 2
}

$versionOutput = & $pythonPath --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Could not execute pinned Python: $pythonPath"
    Write-Host $versionOutput
    exit 2
}

& $pythonPath -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 11, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Python runtime is not exactly 3.11.9: $versionOutput"
    exit 2
}

& $pythonPath -c "import win32com.client" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] pywin32/win32com is not installed in the pinned WinPython runtime."
    Write-Host "[INFO] Install it with:"
    Write-Host "       `"$pythonPath`" -m pip install -r `"$($envInfo.PackRoot)\requirements.txt`""
    exit 2
}

$manifestDir = Join-Path $envInfo.PackRoot "runtime\manifests"
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
$manifest = Join-Path $manifestDir "winpython_runtime.txt"
@(
    "pack=Invoice_Process_Dashboard_Operator_Pack"
    "python=$pythonPath"
    "version=$versionOutput"
    "win32com=ok"
) | Set-Content -LiteralPath $manifest -Encoding ASCII

Write-Host "[OK] WinPython runtime found: $pythonPath"
Write-Host "[OK] Version: $versionOutput"
Write-Host "[OK] win32com.client import passed."
Write-Host "[OK] Runtime manifest: $manifest"
