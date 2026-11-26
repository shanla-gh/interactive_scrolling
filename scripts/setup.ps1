# Creates the project-local virtual environment, installs the pinned dependencies and
# downloads the MediaPipe models (hands; optional segmentation and face). Run from the root:
#     powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment (.venv) with Python 3.12..."
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required (install it from python.org)." }
}
$python = ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
& $python -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw "Project installation failed" }
& $python scripts\download_model.py
if ($LASTEXITCODE -ne 0) { throw "Model download failed" }
Write-Host ""
Write-Host "Setup complete. Start the application with: scripts\run.ps1"
