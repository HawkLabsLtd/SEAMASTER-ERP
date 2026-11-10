Param(
  [string]$Port = "5000"
)

$ErrorActionPreference = "Stop"

function Ensure-Python {
  $py = Get-Command python -ErrorAction SilentlyContinue
  if (-not $py) {
    Write-Host "Python not found. Attempting installation via winget/choco..." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
      winget install -e --id Python.Python.3.12 --source winget
    } else {
      $choco = Get-Command choco -ErrorAction SilentlyContinue
      if ($choco) {
        choco install -y python
      } else {
        throw "Python is required but not found, and no installer (winget/choco) is available. Please install Python 3.10+ and re-run."
      }
    }
  }
}

function Invoke-InVenv {
  param([string[]]$ArgsArray)
  $pythonPath = Join-Path $PWD ".venv\\Scripts\\python.exe"
  & $pythonPath @ArgsArray
}

# Move to repo root if script is executed from elsewhere
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

Write-Host "== SeaMaster bootstrap ==" -ForegroundColor Cyan
Ensure-Python

# Create virtual environment if missing
if (-not (Test-Path ".venv")) {
  Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
  python -m venv .venv
}

Write-Host "Upgrading pip/setuptools/wheel..." -ForegroundColor Cyan
Invoke-InVenv -ArgsArray @("-m","pip","install","--upgrade","pip","setuptools","wheel")

# Root app dependencies
if (Test-Path "requirements.txt") {
  Write-Host "Installing root requirements.txt ..." -ForegroundColor Cyan
  Invoke-InVenv -ArgsArray @("-m","pip","install","-r","requirements.txt")
} else {
  Write-Host "Installing core dependencies (Flask + SQLAlchemy)..." -ForegroundColor Cyan
  Invoke-InVenv -ArgsArray @("-m","pip","install","Flask","Flask-SQLAlchemy")
}

Write-Host "Starting Flask dev server on port $Port ..." -ForegroundColor Green
Invoke-InVenv -ArgsArray @("-m","flask","--app","app.py","init-db")
Invoke-InVenv -ArgsArray @("-m","flask","--app","app.py","run","--debug","-p",$Port)
