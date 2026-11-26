# Runs formatting, lint and the automated test suite.
# Pass -Hardware to include the tests that use the physical webcam.
param([switch]$Hardware)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = ".venv\Scripts\python.exe"
& $python -m ruff format --check src tests scripts
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m ruff check src tests scripts
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$pytestArgs = @()
if ($Hardware) { $pytestArgs += "--hardware" }
& $python -m pytest @pytestArgs
exit $LASTEXITCODE
