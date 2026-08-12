@echo off
setlocal EnableExtensions

set "PACK_ROOT=%~dp0"
for %%I in ("%PACK_ROOT%") do set "PACK_ROOT=%%~fI"

set "RUNTIME_VERSION=3.11.9"
if not defined INVOICE_DASHBOARD_PYTHON (
  echo [FAIL] Set INVOICE_DASHBOARD_PYTHON to an existing Python 3.11.9 executable.
  exit /b 2
)
set "PYTHON_EXE=%INVOICE_DASHBOARD_PYTHON%"

set "INVOICE_DASHBOARD_DB_PATH=%PACK_ROOT%\db\invoices.db"
set "INVOICE_DASHBOARD_DEPLOY_DIR=%PACK_ROOT%\dashboard"
set "INVOICE_DASHBOARD_CALENDAR_DIR=%PACK_ROOT%\dashboard\Calendar"
set "INVOICE_DASHBOARD_PRODUCTION_OVERRIDES_DIR=%PACK_ROOT%\dashboard\ProductionOverrides"
set "INVOICE_DASHBOARD_SLA_TRACKER_SNAPSHOT_DIR=%PACK_ROOT%\data\sla_tracker_snapshots"

echo =====================================================
echo   Invoice Process Dashboard - WinPython Runtime
echo =====================================================
echo.
echo Runtime: %PYTHON_EXE%
echo Python: %RUNTIME_VERSION%
echo.

if not exist "%PYTHON_EXE%" (
  echo [FAIL] Pinned runtime not found:
  echo        %PYTHON_EXE%
  echo [INFO] This handoff BAT validates a local WinPython runtime only.
  echo [INFO] It does not download or install anything automatically.
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PACK_ROOT%\automation\lib\InstallWinPythonRuntime.ps1" -ExpectedPython "%PYTHON_EXE%"
  exit /b %ERRORLEVEL%
)

"%PYTHON_EXE%" --version
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 11, 9) else 1)"
if errorlevel 1 (
  echo [FAIL] Python runtime is not exactly 3.11.9.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PACK_ROOT%\automation\lib\InstallWinPythonRuntime.ps1" -ExpectedPython "%PYTHON_EXE%"
exit /b %ERRORLEVEL%
