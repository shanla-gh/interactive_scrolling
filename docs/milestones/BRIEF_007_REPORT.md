# Engineering Brief 007 - checkpoint report (product experience)

Statuses follow `docs/ENGINEERING_CONVENTIONS.md`. Screenshots (technical demonstrations with a
synthetic camera scene, not committed): `E:\interactive_scrolling\screenshots\brief007\before\`
and `...\after\` (1366x768_100, 1920x1080_125, 1920x1080_150).

| CP | Status | Evidence / remaining |
|---|---|---|
| Baseline | COMPLETED | 195a214: 686 passed, 6 skipped; recognition benchmark reproduced |
| 26.1 Freeze baseline | COMPLETED | `docs/benchmarks/baselines/v0.6.0b1_*.json` (5 conditions) |
| 26.2 False positives | COMPLETED (no change adopted) | whole-hand minimum speed 3.0/3.5 rejected by the gate |
| 26.3 Low-fps robustness | COMPLETED (no change adopted) | low-fps return memory rejected (flicks undersampled at 15 fps) |
| 26.4 Calibration safety | COMPLETED | unchanged bounds; no style migration (settings stay v5) |
| 26.5 Regression gate | COMPLETED | `benchmark_motion.py --baseline`; final code: no regression on all baselines |
| 27.1 UI audit | COMPLETED (technical) | 15 screens x 3 scalings before and after; defects listed in Audit 009 |
| 27.2 Information hierarchy | COMPLETED (technical) | camera / gestures / browser wording; overlay control chip |
| 27.3 Simplified interaction | COMPLETED (partly) | guide with direct buttons; thresholds behind "advanced"; step counts unchanged otherwise |
| 27.4 Error messages | COMPLETED | camera error, browser connection, boundaries, sign-in, recognized-but-rejected; no success without verification (unchanged) |
| 28.1 Overlay audit | COMPLETED (technical) | always-on-top/no-activate unchanged; counters layer fixed; session timer added |
| 28.2 Creator presentation | IN_PROGRESS - Director pending | layers independent; smoothing; visual quality needs a human check |
| 28.3 Interaction and focus | COMPLETED (technical) | Position menu, off-screen recovery; second monitor and browser fullscreen untested |
| 28.4 Smooth motion | COMPLETED | display-only One Euro: jitter -30 %, lag 2.6 px (recordings) |
| 29.1-29.2 Segmentation quality | IN_PROGRESS - Director pending | enclosed-hole fill adopted on synthetic evidence; 4 other candidates rejected |
| 29.3 Privacy-safe behaviour | COMPLETED | fallback unchanged and tested |
| 29.4 Combined performance | COMPLETED (no hand) | pipeline benchmark hand-only vs + both models; Broadcast run with models |
| 30.1 OBS compatibility | PARTIAL | desktop composition ok, PrintWindow black, WGC not verified (OBS hung in the automated attempt) |
| 30.2 Recording workflow | COMPLETED | `docs/guides/BROADCAST_GUIDE.md` |
| 31.1 Background Mode | COMPLETED (technical) | 5-min run; tray states; camera release |
| 31.2 Mode transitions | COMPLETED | 29 transitions with per-second invariants, 0 violations |
| 31.3 Resource-aware operation | COMPLETED (verified) / finding open | model scheduling verified; hidden-window frame drops (3 %) unexplained |
| 32.1-32.3 Onboarding | COMPLETED (technical) | Getting started window; gesture texts; extension guide (Chrome manual only) |
| 33.1 Signature features | COMPLETED (automated) | clown, eye analytics, reports, Wrapped, wellbeing, co-op tests pass |
| 33.2 Co-op | COMPLETED (localhost only) | no two-computer test |
| 33.3 Long-duration | COMPLETED (automated) | 30 + 10 + 5 + 10 min; no human-use session |
| 34 Performance | COMPLETED (measured) | `docs/benchmarks/PERFORMANCE_007.md`; Qt stalls not resolved |
| Audit 009 | see [INTEGRATION_AUDIT_009.md](../audits/INTEGRATION_AUDIT_009.md) | |
