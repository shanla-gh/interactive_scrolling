# Integration Audit 002 (after M2 and M3)

Date: 2026-11-26. Scope: the whole codebase, including M0/M1 code, the browser extension,
CI and documentation.

**Technical verification: PASSED** (automated, hardware, fixture-browser and CI).
**Director verification: PENDING** (live gestures controlling the Director's own browser and
account; [checklist](../milestones/M2_M3_DIRECTOR_CHECKLIST.md)). The audit is therefore not a
full pass: the mandatory end-to-end check with physical gestures in the real browser remains
open.

## A. Architecture

| Area | Finding |
|---|---|
| Dependency direction | `config` <- `vision`/`motion` <- `gestures` <- `actions` <- `integrations` / `storage` <- `services` <- `ui` <- `app`. New layer rules (gestures, actions, storage, integrations: no Qt, no upward imports) enforced by `test_architecture.py`; MediaPipe still only in `vision/hand_tracker.py`. |
| Threads | UI; camera capture; processing (inference, motion, gestures); tracker loader; action dispatcher worker; bridge server + one thread per browser connection; analytics writer; camera scan. Each owns its resources; cross-thread data is immutable records, lock-protected state or Qt queued signals. |
| Coupling | Gesture recognition never executes actions; the dispatcher is the only path to the controller; the UI only observes. `services.py` is the single composition root. The bridge's private callback attribute was replaced by a public setter. |
| Error propagation | Camera / tracker errors as before; controller errors -> UNKNOWN outcomes; bridge start failure shown in the UI; analytics errors logged and shown, never raised; listener failures logged. |
| Resource ownership | Window close: emergency disable -> hotkey unregistered -> pipeline shutdown -> dispatcher, bridge and analytics shutdown; stability run: 0.29 s, no worker threads left. |
| Speculative code | None added for M4+: sweep actions are typed but marked unavailable and never executed. |

## B. Functional verification

| Item | Evidence |
|---|---|
| Webcam start/stop, restarts | hardware tests; 10-minute session with 4 restarts |
| Skeleton alignment, motion vectors/trails | unchanged code; pixel tests pass |
| Gesture recognition and conflicts | 65 gesture tests; two labeled recordings |
| Action routing, browser context, disconnection | dispatcher, bridge and fixture-browser tests (CI) |
| Daily counters, history, configuration persistence | analytics, settings-store and control-UI tests |
| Emergency disable | dispatcher and UI tests (button, Esc); Ctrl+Alt+D registration logged at runtime |

## C. Regression

393 tests pass with `--hardware` (baseline 207; all 207 original tests are retained). Tests
changed during this brief, with reasons:

* corrections were confined to tests written in this brief and each fixed the test's model of
  the behaviour, not the assertion's strictness: a return movement scripted inside the cooldown,
  an over-specific rejection reason after a synthetic pose jump, and two browser waits that sent
  a command before the new Short had been reported;
* M1 tests were not modified, except `test_architecture.py`, which gained rules for the new
  layers.

## D. Performance

Development machine as in M1 (i7-13700H, Windows 11, built-in camera, 1280x720).

| Metric | M1 baseline (session 2) | Now, Gesture test mode, 10 min |
|---|---|---|
| Capture / processing / display FPS (mean) | 30.2 / 30.3 / 30.3 | 30.9 / 29.8 / 29.8 |
| Capture-to-result latency mean / p99 | 16.2 / 23.3 ms | 13.2 / 16.4 ms |
| Inference mean | 15.4 ms | 9.7 ms |
| Gesture recognition per frame | n/a | 0.01 ms without hands (session); 0.13 ms mean, 0.15 ms p95 with hands (recorded frames) |
| CPU (share of machine) | 4.9 % | 3.5 % |
| RSS first / last minute | 368 / 342 MB | 357 / 362 MB |
| Dropped frames | 9 | 483 |
| UI heartbeat p99 / max | 12.5 / 39 ms | 13.7 / 357 ms |
| Errors / clean shutdown | none / yes | none / yes |

Caveats: no hand was in view during this session (lower inference cost), and other workloads
(browser tests, evaluations) ran concurrently, which explains the higher frame drops, the 21 FPS
capture minimum and probably the single 357 ms UI stall; the cause of that stall is still not
identified (it also occurred once in M1). Browser action latency (not inference): next 223-441 ms,
previous 202-211 ms, pause/resume 4-5 ms on the live site. Gesture confirmation time is dominated
by the gesture itself (0.21-0.43 s for swipes, 0.6 / 0.8 s holds by design). The Windows
power-throttling opt-out (ADR-008) and `--allow-power-throttling` are unchanged.

## E. Security and privacy

| Check | Result |
|---|---|
| Unauthorized browser control | only the paired extension origin, only four commands, only a visible Shorts tab with the expected video |
| Arbitrary command execution | none: fixed command set, schema-validated input, no eval |
| Exposed endpoints | loopback only; 403 for other origins; 4001 without pairing code; connection cap 8 |
| Browser permissions | `storage`, `https://www.youtube.com/*` |
| Credentials | none collected or stored; pairing code stored locally (accepted risk) |
| Camera / facial / gaze data | none stored; gesture recordings are developer data in ignored `recordings/` (landmarks only) |
| Browsing data | analytics store no URLs, titles or video ids |
| Repository | scanned before commits: no secrets, personal paths or assistant attribution; no recordings, models or reports committed |
| Licensing | websockets (BSD-3-Clause) added to notices; extension is part of the MIT project |

## F. Findings and resolution

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| A2-1 | High | Stale Shorts state kept after a tab navigated away; the app still targeted the tab | cleared on navigation; regression test |
| A2-2 | High | YouTube ignores navigation before the video has loaded; actions failed | readiness requires a loaded video; regression test |
| A2-3 | Medium | Bridge server thread died with WinError 10038 on shutdown | expected error handled during stop; regression test |
| A2-4 | Medium | Finger flicks are ambiguous with their own return movement (from data) | gesture redefined; return window from movement end; tests |
| A2-5 | Medium | Handedness label flips cancelled sweeps; rejections required stillness before the next stroke; reversals lost half of the real stroke | label smoothing; immediate re-arm after rejection; turning-point start; tests |
| A2-6 | Medium | Side panel clipped long values at 1280x720 | values wrap |
| A2-7 | Low | Failed settings writes left temporary files | cleaned up; regression test |
| A2-8 | Low | Unbounded bridge connections | capped at 8; regression test |
| A2-9 | Low | CI failures were invisible without authenticated log access | failed tests reported as annotations |

## Remaining risks

| Severity | Risk |
|---|---|
| High (verification) | Physical gestures controlling the Director's real browser and account not yet verified |
| Medium | YouTube page structure may change; actions then report failed/unknown |
| Medium | Hand sweeps: ~1/3 recall at balanced, overlap with face-touching movements (no action yet) |
| Low | Calibration data from one person and one camera |
| Low | Unexplained rare UI stalls (222 ms in M1, 357 ms now, under concurrent load) |
| Low | GitHub Actions warns that the pinned action versions use the deprecated Node.js 20 runtime |
