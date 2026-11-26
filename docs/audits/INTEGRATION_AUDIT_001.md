# Integration Audit 001 (after M0 and M1)

Date: 2026-11-26. Scope: the entire codebase (`src/`, `tests/`, `scripts/`, CI and
documentation), not only recent changes.

**Result: PASSED for all automatically and hardware-verifiable requirements.** The owner's
visual sign-off on their own hands (M1 manual checklist) is still open and is the only
unverified integration requirement; see "Remaining risks".

## 1. Architecture audit

| Area | Finding |
|---|---|
| Module boundaries / dependency direction | `config` -> `core`/`vision`/`motion` -> `visualization` -> `ui` -> `app`. Enforced by `tests/unit/test_architecture.py` (no Qt in config/core/vision/motion, MediaPipe only in `vision/hand_tracker.py`). No violations. |
| Thread ownership | Camera opened, read and released on its capture thread; tracker created on the loader thread and then used and closed only by the processing thread; analyzer owned by the processing thread; all Qt objects on the UI thread. Data crossing threads is immutable (`Frame`, `TrackingResult`, `MotionFrame`, `ProcessedFrame`) or lock-protected. |
| Resource lifecycle | Camera released in `finally` on every exit path; tracker closed on shutdown or after repeated failures; threads joined on window close with timeouts. Verified by tests and by the stability session (no worker threads alive after close). |
| Error propagation | Camera errors -> `ERROR` state with user-readable message; model errors -> tracking `UNAVAILABLE`, preview continues; listener exceptions logged with traceback without killing worker threads. No silent `except: pass` in `src/` (the only suppression is Qt log emission during interpreter teardown, documented). |
| Configuration | Frozen, validated dataclasses; the only mutable settings (`OverlaySettings`, mirror flag) are touched only by the UI thread. |
| Separation inference / motion / visualization | Inference returns `HandObservation`s; motion consumes `TrackingResult`; rendering consumes both through `ViewTransform`. No module reaches into another's internals. |
| Extensibility | A gesture engine can consume `MotionFrame` / `TrackingResult` from the pipeline listener without Qt. |

## 2. Functional integration audit

Pipeline `webcam -> acquisition -> processing -> inference -> tracking results -> motion ->
visualization -> desktop app` verified with real data at every stage:

* Physical webcam -> `OpenCVCamera`: hardware tests (30.4-30.8 FPS).
* Acquisition -> processing -> inference -> results -> motion: hardware test
  `test_full_pipeline_with_real_camera_and_model` and the 10-minute session (hands detected
  in 373 of 600 samples, 30.3 FPS processing).
* Motion correctness on real tracking: real MediaPipe landmarks on a photo moving at
  86.7 px/s produced a measured 87-88 px/s.
* Visualization -> desktop app: the GUI stability session drives the real window; pixel tests
  verify overlay placement; screenshots with real landmarks reviewed in both mirror modes.

## 3. Defects found and fixed

All have regression tests in `tests/regression/` or the integration suites. For D-1 and D-6
the regression test was additionally confirmed to fail with the fix removed.

| ID | Severity | Defect | Fix |
|---|---|---|---|
| D-1 | High | Camera state notifications could arrive out of order (STOPPED before STOPPING), leaving the UI stuck in "Stopping" with Start disabled. | Notify under the state lock (re-entrant); queued Qt connections. |
| D-2 | Medium | Preview stayed empty until the model loaded (~9 s on a cold first launch). | Model loads on a helper thread; frames pass through meanwhile. |
| D-3 | Medium | Configured default resolution 1280x720 ignored (640x480 requested). | Select combo entry by list position (`findData` cannot match tuples). |
| D-4 | Medium | Stopping while the camera was still opening could report RUNNING. | Stop check and RUNNING transition under one lock. |
| D-5 | Medium | Activity log empty when the console log level was above INFO. | Package logger passes INFO to the UI handler; console handlers filter themselves. |
| D-6 | Low | Displayed latency mixed preview-only frames with inference frames right after model load. | Reset statistics when the tracker becomes ready. |
| D-7 | Low | Diagnostics bar blank until the first timer tick. | Render diagnostics at construction. |
| D-8 | Low | Velocity labels overlapped the skeleton and were hard to read; title accent had a visible background box. | Label background placed beyond the arrow head; transparent title background. |
| D-9 | Low | Test-only helpers in production code (`ensure_model`, `mirror_normalized`, `ViewTransform.contains`, `RollingStats.maximum`). | Removed. |

Performance finding (not a defect): Windows power throttling doubled latency; mitigated by
ADR-008.

## 4. Regression audit

Full suite after the fixes: `python -m pytest --hardware` -> **207 collected, all passed**
(see `PROJECT_STATUS.md` for the final run). `ruff format --check` and `ruff check` clean.

## 5. Stability audit

| Concern | Result |
|---|---|
| Race conditions | D-1 and D-4 fixed. Frame handoff through a lock/condition mailbox; bridge coalescing under a lock. |
| Memory leaks | 10-minute session: RSS last-minute mean 336 MB vs first-minute 365 MB; thread count stable. |
| Unbounded queues | None: single-slot mailbox, coalescing bridge, bounded deques for stats/history, log widget capped at 500 lines. |
| Stale tracking data | Frames from stopped sessions are discarded; lost hands leave no overlay (tests); analyzer resets per session. |
| Timestamps | `perf_counter_ns` at capture; strictly increasing timestamps to MediaPipe; non-increasing timestamps rejected by the analyzer. |
| Coordinate transforms | One `ViewTransform` for image and overlay; pixel-tested at several sizes and both mirror modes. |
| UI thread blocking | Heartbeat p99 lateness 14 ms; one 222 ms stall at t = 100 s and nine 40-81 ms stalls in 10 minutes. The largest coincided with a scripted overlay toggle; root cause not identified (processing FPS was unaffected). |
| Camera resource leaks | Release verified after every session in tests, hardware tests and stability runs. |
| Shutdown | 0.30 s; no worker threads alive afterwards. |
| Exception handling | Worker threads log tracebacks and surface states; no swallowed errors. |

## 6. Repository and privacy audit

* No credentials, tokens, `.env` files, personal paths or user names in tracked files
  (scanned before each commit).
* No webcam images or recordings; screenshots used for review were kept outside the
  repository and not committed. Models, reports and test caches are ignored by Git.
* No assistant branding, attribution or co-author trailers in files or commit messages.
* Licensing: MIT; dependency licences and the model's Apache 2.0 licence documented in
  `docs/THIRD_PARTY_NOTICES.md`; the sample photo with undocumented licence is never committed.
* Reproducible installation: exact pins, `scripts/setup.ps1`, CI installs from the pins.
* Documentation reviewed against the implementation; planned features are marked as planned.

## Remaining risks

| Severity | Risk | Impact |
|---|---|---|
| Medium | Owner's visual confirmation on real hands is pending (manual checklist). | Overlay alignment on live hands is verified by pixel tests and by real landmarks on a photo, but not yet by a person in front of the webcam. |
| Low | Only one machine and one built-in camera tested; busy-camera and USB-disconnect paths verified only with simulated devices. | Other drivers may behave differently. |
| Low | Performance depends on Windows power management; with `--allow-power-throttling` latency roughly doubles. | Documented. |
| Low | MediaPipe logs a native warning ("Using NORM_RECT without IMAGE_DIMENSIONS ...") from inside its own graph. | Cosmetic console output; landmark accuracy on non-square frames verified by tests and review. |
| Low | One 222 ms UI stall observed in 10 minutes, cause not identified. | Brief visual hitch; processing was unaffected. To be profiled in M5 (desktop UX). |
