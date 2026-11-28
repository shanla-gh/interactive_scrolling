# Renders the screenshot set at the three reference laptop configurations (Brief 007/008).
# The development display runs at 125 % Windows scaling, so QT_SCALE_FACTOR 0.8 / 1.0 / 1.2
# emulates 100 % / 125 % / 150 %; sizes are the logical work areas (taskbar subtracted).
param([Parameter(Mandatory = $true)][string]$Out, [string]$Only = "")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = ".venv\Scripts\python.exe"
$sets = @(
    @{ name = "1366x768_100"; scale = "0.8"; size = "1366x728" },
    @{ name = "1920x1080_125"; scale = "1.0"; size = "1536x824" },
    @{ name = "1920x1080_150"; scale = "1.2"; size = "1280x688" }
)
foreach ($set in $sets) {
    $extra = @()
    if ($Only) { $extra = @("--only", $Only) }
    & $python scripts\capture_screenshots.py --out "$Out\$($set.name)" --scale $set.scale --size $set.size @extra
}
