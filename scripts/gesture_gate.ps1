# Gesture regression gate: compares the motion engine against the five frozen 0.6.0b1
# baselines (recorded frame rate, 20 fps, 15 fps, 10 % frame loss, pointing finger only).
# Needs the local development recordings in recordings/ (never committed). Exits 1 on any
# regression.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = ".venv\Scripts\python.exe"
$recordings = Get-ChildItem recordings\gestures_*.json | ForEach-Object { $_.FullName }
$base = "docs\benchmarks\baselines\v0.6.0b1"
$runs = @(
    @{ name = "recorded"; extra = @() },
    @{ name = "fps20"; extra = @("--degrade", "fps20") },
    @{ name = "fps15"; extra = @("--degrade", "fps15") },
    @{ name = "drop10"; extra = @("--degrade", "drop10") },
    @{ name = "recorded_finger_only"; extra = @("--set", "control_style=finger") }
)
$failed = 0
foreach ($run in $runs) {
    Write-Output "=== $($run.name)"
    & $python scripts\benchmark_motion.py @recordings @($run.extra) --baseline "$($base)_$($run.name).json" | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) { $failed += 1 }
}
if ($failed) { Write-Output "REGRESSION in $failed configuration(s)"; exit 1 }
Write-Output "no regression in all five configurations"
