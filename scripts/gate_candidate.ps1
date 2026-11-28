# Runs the five-configuration gesture gate with extra benchmark arguments (a candidate), e.g.
#   scripts\gate_candidate.ps1 --option down_stop_fraction=0.5 --option early_min_fps=22
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
    $out = & $python scripts\benchmark_motion.py @recordings @($run.extra) @args --baseline "$($base)_$($run.name).json"
    $result = (($out | Select-String "RESULT") -join "").Trim()
    $median = (($out | Select-String "confirmation median") -join "").Trim()
    $ordinary = (($out | Select-String "ordinary-activity events") -join "").Trim()
    Write-Output "$($run.name): $result | $ordinary | $median"
    if ($LASTEXITCODE -ne 0) { $failed += 1 }
}
if ($failed) { exit 1 }
