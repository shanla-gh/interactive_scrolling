# Builds the one-folder Windows release (dist\InteractiveScrolling) and a zip of it.
#     powershell -ExecutionPolicy Bypass -File scripts\build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = ".venv\Scripts\python.exe"
& $python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Installing the build tools failed" }
& $python scripts\download_model.py
if ($LASTEXITCODE -ne 0) { throw "Models missing or invalid" }
& $python -m PyInstaller packaging\interactive_scrolling.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$version = & $python -c "import interactive_scrolling as m; print(m.__version__)"
$zip = "dist\InteractiveScrolling-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\InteractiveScrolling" -DestinationPath $zip
Write-Host "Built $zip"
