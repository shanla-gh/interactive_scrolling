# Starts the application. Extra arguments are passed through, e.g.:
#     scripts\run.ps1 --camera 1 --resolution 640x480
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& .venv\Scripts\python.exe -m interactive_scrolling @args
exit $LASTEXITCODE
