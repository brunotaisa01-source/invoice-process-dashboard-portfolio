@echo off
setlocal
set "PACK_ROOT=%~dp0.."
for %%I in ("%PACK_ROOT%") do set "PACK_ROOT=%%~fI"
set "INVOICE_DASHBOARD_DB_PATH=%PACK_ROOT%\db\invoices.db"
set "INVOICE_DASHBOARD_DEPLOY_DIR=%PACK_ROOT%\dashboard"
set "INVOICE_DASHBOARD_CALENDAR_DIR=%PACK_ROOT%\dashboard\Calendar"
set "INVOICE_DASHBOARD_PRODUCTION_OVERRIDES_DIR=%PACK_ROOT%\dashboard\ProductionOverrides"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lib\RunDailyLatest.ps1"
exit /b %ERRORLEVEL%
