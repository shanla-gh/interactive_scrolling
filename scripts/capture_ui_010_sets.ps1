# Renders the Brief 010 compatibility screenshots (CP 54.4). The development display is
# 1920 x 1080 at 125 % Windows scaling, so QT_SCALE_FACTOR 0.8 / 1.0 / 1.2 / 1.4 emulates
# 100 / 125 / 150 / 175 %; sizes are logical window sizes (taskbar subtracted).
param([Parameter(Mandatory = $true)][string]$Out)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = ".venv\Scripts\python.exe"
$sets = @(
    @{ name = "1366x768_100"; scale = "0.8"; size = "1366x728" },
    @{ name = "1366x768_125"; scale = "1.0"; size = "1093x582" },
    @{ name = "1366x768_150"; scale = "1.2"; size = "910x480" },
    @{ name = "1920x1080_100"; scale = "0.8"; size = "1920x1040" },
    @{ name = "1920x1080_125"; scale = "1.0"; size = "1536x824" },
    @{ name = "1920x1080_150"; scale = "1.2"; size = "1280x688" },
    @{ name = "1920x1080_175"; scale = "1.4"; size = "1097x590" }
)
foreach ($set in $sets) {
    & $python scripts\capture_ui_010.py --out "$Out\$($set.name)" --scale $set.scale --size $set.size --set compat
    if ($LASTEXITCODE -ne 0) { throw "capture failed for $($set.name)" }
}
