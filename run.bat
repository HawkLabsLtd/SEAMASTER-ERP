@echo off
setlocal

REM SeaMaster one-click bootstrap & run (Windows)
REM Usage: double-click or run: run.bat [PORT]

set SCRIPT_DIR=%~dp0
set PORT=%1
if "%PORT%"=="" set PORT=5000

echo Starting SeaMaster setup and server on port %PORT% ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup_and_run.ps1" -Port %PORT%

endlocal