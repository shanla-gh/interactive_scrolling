# Integration Audit 005 (complete system, release candidate 0.3.0rc1)

Date: 2026-11-26. Scope: the whole project (M0-M11), not only the newest features.

| Verdict | |
|---|---|
| Implementation | complete for every Brief 003 checkpoint except the optional grayscale / scrolling-delay extras (not implemented, optional in the brief) |
| Technical verification | **passed** (automated, hardware, fixture browser, live website, loopback and separate-process co-op, packaged build) |
| Director acceptance | **pending** - the audit is therefore *not* a full pass |
| Blocked requirements | real-person verification of left/right swipes and the half-heart, visual quality, OBS Windows Graphics Capture, two-computer co-op, signed-in liking |

## Architecture

* One camera (`camera-capture-N`), one processing thread, one gesture engine, one dispatcher, one
  extension bridge for all presentation modes and features (verified by
  `test_mode_switches_share_one_runtime`). Optional models are separate workers fed by frame
  taps; they never feed back into the hand tracker. Co-op Guest requests enter the Host's
  existing dispatcher; the Guest swaps its controller (one dispatcher either way).
* No duplicate processing: the face worker is shared by the clown and eye analytics;
  segmentation runs only while the transparent overlay is visible.
* Dependency rules extended for `wellbeing` and `integrations/coop`; MediaPipe confined to
  three adapters (`test_architecture.py`).

## Functional combinations

| Combination | Evidence |
|---|---|
| Developer Mode + gesture control | UI and control tests; stability sessions (Gesture test) |
| Creator + transparent background | `test_transparent_overlay_removes_background_and_hides_camera_without_mask`; capture script |
| Creator + clown; transparency + clown | clown painter registered on both views; rendered together on the reference photo (UI_AND_EFFECTS.md) |
| Eye tracking during scrolling | services feed eye samples on the face worker; aggregates via activity thread (unit tests) |
| Background Mode + browser control | tray actions use the same handlers; runtime unchanged by mode (tests); tray not available on the offscreen test platform, so its menu is in the checklist |
| Tab switching away from and back to Shorts | real extension in headless Edge |
| Reporting after restart, day rollover | crash/heartbeat and midnight tests |
| Wrapped export | layout, numbers, PNG size tests |
| Co-op + local creator overlay | independent: co-op changes only the dispatcher's controller on the Guest; the overlay reads frames only |
| Emergency disable in each execution mode | dispatcher tests, creator-mode test, co-op host test |

## Performance (development machine: i7-13700H, Windows 11, built-in camera, 1280x720)

Headless benchmark, 60 s each, power-throttling opt-out, same session of measurements:

| Configuration | Capture / processing FPS | Latency mean / p95 | Hand inference | Optional inference | CPU (machine) | RSS | Dropped |
|---|---|---|---|---|---|---|---|
| Hand tracking only | 30.2 / 30.0 | 12.7 / 22.4 ms | 11.4 ms | - | 2.9 % | 251 MB | 21 |
| + transparent background | 30.8 / 29.5 | 15.5 / 29.8 ms | 11.1 ms | segmentation 3.4 ms at 13/s | 3.2 % | 273 MB | 65 |
| + face (clown / eyes) | 30.8 / 29.5 | 15.3 / 29.5 ms | 11.0 ms | face 7.3 ms at 13/s | 3.4 % | 280 MB | 69 |
| All optional models | 30.9 / 29.5 | 15.3 / 29.6 ms | 11.1 ms | 3.3 ms + 7.1 ms | 3.6 % | 303 MB | 64 |

GUI stability sessions (10 min each, Gesture test, production services, camera restarts every
2 min, window resizes): processing 29.6 / 30.0 FPS, latency 19.2 / 15.5 ms mean, CPU 4.3 / 4.1 %,
RSS 384 -> 363 MB (no growth), 4/4 camera restarts in ~1 s, shutdown 0.28 s, no worker threads
left, dropped 404 / 228 frames (baseline M2: 483 under concurrent load).

Comparison with the 0.2 baseline (M2 session: 29.8 FPS, 13.2 ms mean latency, 3.5 % CPU):
primary performance is preserved with optional features off; with all optional models on, the
gesture pipeline keeps ~29.5 FPS and the mean latency grows by ~2.6 ms. Gesture recognition
itself: 0.13 ms per frame. Browser action latency (live site, this run's live test passed):
next / previous 200-450 ms, pause 4-5 ms (0.2 measurements, same code path). Gesture
confirmation is dominated by the gesture (0.2-0.5 s strokes; 0.6 / 0.8 s holds by design).
No adaptive scheduling was needed: the 15 FPS cap per optional worker kept the primary
pipeline within 0.5 FPS of its baseline.

Measurement conditions: the same person was partly in view (hands in 5-25 % of frames), so
results are representative of light real use, not of continuous gesturing.

## Overlay capture (CP 5.2)

`scripts/verify_overlay_capture.py` with the real overlay in transparent mode over a magenta
window: **desktop composition** (screen BitBlt, what OBS *Display Capture* sees) shows the person
opaque and the magenta window through the removed background - per-pixel transparency works.
**PrintWindow** of the overlay alone (comparable to OBS *Window Capture*, BitBlt method) returns
the transparent pixels as **opaque black**. OBS's *Windows 10 (1903 and up)* method could not be
tested without modifying the Director's OBS configuration and is in the checklist.

## Security and privacy

| Check | Result |
|---|---|
| Camera visible and user-controlled | camera opens only on Start (or the tray action); tray icon always shows its state; quit releases it (stability: camera stopped after close) |
| No cloud inference, no telemetry | all models local; the only network use: one-time model download, the loopback extension bridge, user-initiated co-op on the local network |
| No hidden recording, no identity recognition | no frames written; face landmarks used only for clown and eye estimates; no embeddings |
| Biometric storage | eye analytics: daily totals only; no landmarks or images stored anywhere |
| Credentials | none collected; pairing code and co-op code are local secrets |
| Browsing history | analytics store no URLs, titles or video ids; tab commands use positions only |
| Remote commands | extension: six fixed commands; co-op: three shared actions, authenticated, approved, signed, sequenced, size-limited; likes/tabs never accepted from a Guest |
| Endpoints | extension bridge on 127.0.0.1 with origin pinning; co-op endpoint only during a session, one Guest, five-attempt lockout |
| Extension permissions | unchanged: `storage` + `https://www.youtube.com/*` |
| Analytics deletion | *Delete all statistics* removes events and eye totals; opt-out records nothing |
| Licensing | MediaPipe models Apache-2.0 (notices, license text bundled in builds); PyInstaller used as a build tool (GPL with bundling exception) |
| Repository | scanned: no secrets, personal data, recordings, reports, models or assistant attribution committed; all commits with the existing identity |

## Regression

| Suite | Result |
|---|---|
| `ruff format --check` / `ruff check` (src, tests, scripts) | clean |
| `pytest --hardware` | **567 passed, 1 skipped** (opt-in live test) - baseline 392 (+1 flaky) |
| `pytest tests/live --live-youtube` | 1 passed (real website, signed out) |
| CI (GitHub Actions, Windows) | success on de6ddb1; see PROJECT_STATUS for the latest run |

Categories: unit (gestures, settings, protocols, wellbeing, eyes, clown, stall monitor),
integration (UI modes, overlay, reports, wrapped, co-op incl. a separate process, real models
via self-test), regression (one per fixed defect), hardware (webcam), browser fixture (real
extension in headless Edge, incl. tabs), live website (opt-in). Network tests: co-op over
loopback TCP. Human acceptance: the Director checklist.

Superseded behaviour updated (not weakened): thumbs-up and open-hand-sweep tests replaced by
half-heart and horizontal index-swipe tests; the old sweep and thumbs recordings are now
scored as negatives.

## Open risks for acceptance

| Severity | Risk |
|---|---|
| High (verification) | Left/right swipes and half-heart unverified on real hands; possible opposite-tab switch from preparation movements made while pointing |
| Medium | Stop pose unreliable with the open hand far from the camera |
| Medium | YouTube markup changes would make Shorts actions fail (reported honestly) |
| Medium | Transparent background quality depends on lighting/clothing (lightweight model) |
| Low | Rare UI stalls inside Qt's event loop (instrumented); gesture control unaffected |
| Low | Packaged build validated only on the development machine; unsigned |
