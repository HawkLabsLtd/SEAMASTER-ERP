@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PY_EXE=%SCRIPT_DIR%\.venv\Scripts\python.exe"
if exist "%PY_EXE%" (
  set "PYTHON_EXE=%PY_EXE%"
) else (
  set "PYTHON_EXE=python"
)

set "ROOT=%SCRIPT_DIR%"
set "ROOT=%ROOT:~0,-1%"
set "ROOTF=%ROOT:\=/%"

REM SQLite connection
set "DATABASE_URL=sqlite:///%SCRIPT_DIR%instance\seamaster.db"
REM GEMINI_API_KEY is read from .env

"%PYTHON_EXE%" -m pip install -r requirements.txt
"%PYTHON_EXE%" -m flask --app app init-db
"%PYTHON_EXE%" -m flask --app app run --port 5000 %*