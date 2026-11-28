# Engineering Brief 009 - checkpoint report (motion engine, real-time, passive eyes)

Statuses per `docs/ENGINEERING_CONVENTIONS.md`. Evidence kinds: **replay** (development
recordings through the real code), **synthetic** (generated input), **hardware** (the real
webcam, no person), **human** (none in this brief). Screenshots and reports are local
(`screenshots/brief009/`, `reports/b9_*`), never committed.

| CP | Status | Evidence / remaining |
|---|---|---|
| Baseline | COMPLETED | 0c5883b / 0.8.0b1: 755 passed, 6 skipped (one unidentified failure in the first of 5 runs); gate no regression x5 |
| 45.1 Pipeline instrumentation | COMPLETED | `benchmark_modes.py`: per-frame capture->recognition, inference, wait, processing interval, UI lateness, event->dispatch->verified->UI, overlay paints, worker rates, CPU |
| 45.2 Mode benchmarks | COMPLETED (replay) | 9 scenarios, identical gestures; Co-op overhead from Brief 008 (loopback) - no new two-person scenario |
| 45.3 Broadcast complaint | COMPLETED (investigated) / NOT REPRODUCED | causes confirmed/rejected in PERFORMANCE_009.md; practical check needs the Director |
| 46.1 Recognizer limitations | COMPLETED | decision-delay analysis: only downward swipes waited (guards against a hand lowered out of view) |
| 46.2-46.3 Motion representation / reference | COMPLETED (no change adopted) | existing finger/hand detectors kept; candidates F, G rejected by the gate |
| 46.4 Fast gestures | COMPLETED (no change) | duplicate-hand filter preserved; no fabricated frames |
| 46.5 Repeated gestures | BLOCKED - data | no rapid-repeat recordings; cooldown candidates had no effect; new `--session repeats` recorder |
| 46.6 False positives | COMPLETED (no change adopted) | 11 / 249 s unchanged; candidates lose real swipes; no classifier without independent data |
| 46.7 Adaptive sensitivity | COMPLETED | frame-rate-aware downward confirmation (adopted, candidate D) |
| 46.8 Half-heart / stop | NOT_STARTED - no new data | unchanged; emergency disable independent of face/eye tracking (unchanged) |
| 46.9 Degraded conditions | COMPLETED (replay) | 15/20 fps, 10 % loss unchanged by design (gate) |
| 46.10 Candidate comparison | COMPLETED | 9 candidates logged in GESTURE_BENCHMARK_009.md |
| 47.1-47.2 Camera FPS / modes | COMPLETED (hardware) | camera max 1280x720@30 in every backend/format; DirectShow claims 60/120 falsely |
| 47.3 Variable frame intervals | COMPLETED | no fixed intervals in motion code; frame-rate-aware rule measures intervals |
| 47.4 Capture latency / buffering | COMPLETED | bursty delivery (arrival sd 25 ms vs driver 0.9 ms) lost up to 5 % of frames at the handoff; two-frame bounded buffer: 39.5 -> 0.0 dropped/min (real-camera A/B), +1.5-6 ms latency; driver times recorded, recognition on arrival times |
| 47.5 Camera settings | COMPLETED (unchanged UI) | requested fps already selectable; measured rate shown |
| 48.1-48.3 Priority / decoupling / budget | COMPLETED (evidence: no change needed) | optional workloads do not change hand latency; adaptive budget rejected as unneeded complexity |
| 48.4 Broadcast smoothness | COMPLETED | repaint loop fixed; smoothing lag halved |
| 48.5 Gesture-to-action | COMPLETED (replay + Brief 008 live times) | breakdown in PERFORMANCE_009.md |
| 48.6 UI stalls | IN_PROGRESS - not resolved | resize 17-48 ms (no 110-180 ms reproduced); rare long stalls remain unexplained |
| 48.7 Mode consistency | COMPLETED | `test_mode_consistency.py` (4 configurations, identical sequences); replay: identical 12 gestures in 9 scenarios |
| 49.1 Eye audit | COMPLETED | one face model reused |
| 49.2-49.4 Eye landmarks, head pose, gaze vectors | COMPLETED (synthetic) | overlay + estimate; real-person check pending |
| 49.5-49.6 Calibration, gaze point | BLOCKED - person needed | evaluation tool ready; crosshair not implemented without accuracy evidence |
| 49.7 Robustness | BLOCKED - person needed | quality gating tested synthetically |
| 50.1 Eye analytics | COMPLETED (reviewed) | already normalized (rate per screen-facing minute, known share) |
| 50.2 Heatmap | NOT IMPLEMENTED (by evidence) | no accuracy data |
| 50.3 Privacy | COMPLETED | no storage of gaze coordinates; calibration tool saves aggregates only |
| 50.4 Wrapped | COMPLETED | optional eye line with unknown time |
| 51.1 Clown | COMPLETED (unchanged) | brief 008 design kept; landmark smoothing unchanged |
| 51.2 Transparent background | COMPLETED (unchanged) | fallback unchanged; replay cost measured |
| 51.3 Live preview | COMPLETED (unchanged) | first-navigation failure: no new evidence |
| 51.4 Doomscroll Together | COMPLETED (regression tests) | Co-op suites pass; no two-computer test |
| 52.1-52.2 Benchmarks / targets | COMPLETED (measured) | PERFORMANCE_009.md |
| 52.3 Recognition targets | NOT MET / NOT MEASURABLE | no independent labelled data; targets not claimed |
| 52.4 Endurance | COMPLETED (automated, real webcam, no person) | 30 min Normal + live preview, 30 min Broadcast with all models, 10 min mode cycling (29 transitions, 0 violations); no leaks or leftover threads; preview-session stalls investigated |
| 53 Audit 011 | see INTEGRATION_AUDIT_011.md | |
