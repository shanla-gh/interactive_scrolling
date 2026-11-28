# Performance and real-time pipeline - Brief 009 (0.9.0b1)

## Method

`scripts/benchmark_modes.py` replays a recording (development data, s5 right, 45 s, 1,351
frames, 12 gestures) through the **real application window** in each presentation mode: a
replay camera delivers the synthetic scene at the recording's own frame times, the real
MediaPipe hand model runs on every frame (for its real cost) and its output is replaced by the
recorded landmarks, the real dispatcher executes actions against a scripted browser that
confirms after 150 ms, optional models are the real ones (segmentation, face). Every scenario
receives identical input, so differences come from the mode. Times are `perf_counter`.
Distributions are median / p95 / p99 / max. This is replay, not human interaction.

## The Broadcast Mode investigation (CP 45.3)

| Hypothesis | Test | Verdict |
|---|---|---|
| Camera acquisition differs by mode | replay camera identical; real camera: CAMERA.md | rejected (acquisition is mode-independent) |
| Hand inference / recognition slower in Broadcast | per-frame capture -> recognition latency in 9 scenarios | **rejected**: ~10 ms median, <= 22 ms p99 in every mode, identical gesture sequence in all |
| Face inference / segmentation / clown delay the hand pipeline (GIL, threads) | Broadcast with each optional model and all together | **rejected**: inference 8.9-9.5 ms median in all; wait before processing 0.4 ms |
| Windows power throttling depends on which window is visible | same benchmark without the app's throttling opt-out | **confirmed mechanism, not active in the app**: without the opt-out Normal Mode ran at 26 ms median vs 10.8 ms in Broadcast; the application always opts out at start (`app.py`), and with the opt-out all modes are equal |
| Overlay rendering wastes the UI thread | overlay paint count | **confirmed**: 2,198 overlay paints in 30 s (73/s) - a repaint loop while feedback faded; fixed (1,092 = the camera rate) |
| Display smoothing makes the skeleton lag | drawn vs real fingertip during fast moves | minor: 3.5 ms median lag (2 px); reduced to 1.6 ms |
| Recognized gestures act late (decision delay) | `analyze_decision_delay.py` | **confirmed for downward swipes** (previous Short): 255 ms (finger) / 432 ms (whole hand) median wait after the stroke; reduced to 192 / 367 ms at >= 22 fps (GESTURE_BENCHMARK_009.md). Applies in every mode. |
| Browser focus / dispatch delays | record timing: event -> dispatch 10 ms median; dispatch -> verified = browser time; verified -> UI thread 1-3 ms | rejected as mode-specific (same path; Broadcast keeps the browser in front) |
| Frames lost at the capture handoff (real camera) | 30-min sessions: 27-85 dropped frames/min, highest in Broadcast with every optional model (85/min, processing 27.5 fps) | **confirmed, mode-amplified**: camera bursts + a single-slot handoff; fixed with a two-frame buffer (39.5 -> 0.0/min). Lost frames make fast swipes less reliable; this is the strongest technical candidate found for the Broadcast complaint |
| Presentation-mode transitions reset gesture state | `tests/integration/test_mode_consistency.py`; mode cycling endurance | rejected (identical sequences, control mode unchanged) |

**Conclusion.** In replay (periodic camera) no mode-specific recognition or latency defect
exists. On the real camera, frames were lost at the handoff - most in Broadcast Mode with every
optional model (85 per minute, about 5 %) - which makes fast swipes less reliable; this is now
fixed (two-frame buffer). Two inefficiencies were fixed (overlay repaint loop; display
smoothing lag), and the largest delay in how responsive control *feels* - the wait before a
downward swipe fires - was reduced. The Director's practical observation is therefore **not explained by a
reproduced defect**; plausible remaining factors that replay cannot capture: the real hand
position while watching the browser (lower in the picture, where downward swipes wait), the
small overlay making feedback less visible than Normal Mode's banner, and the real browser's
navigation time (200-700 ms measured on the live site). This needs the Director's check.

## Before / after under equivalent conditions (app process, throttling opt-out in both)

| Scenario | 0.8.0b1: latency median / p99 / max, CPU, UI lateness p99 | 0.9.0b1 |
|---|---|---|
| Normal | 10.3 / 18.5 / 20.5 ms, 3.6 %, 4.9 ms | 10.6 / 21.6 / 41.7 ms, 3.2 %, 4.7 ms |
| Broadcast, basic overlay | 10.4 / 18.7 / 92.7 ms, 3.6 %, 4.3 ms | 10.4 / 19.8 / 44.6 ms, **2.6 %**, 3.2 ms |
| Broadcast, everything (transparency, clown, eye analytics, vectors, counters, preview) | 10.3 / 20.0 / 36.0 ms, 6.1 %, 6.6 ms | 10.0 / 18.2 / 25.7 ms, **4.4 %**, 5.7 ms |
| Background | 10.5 / 20.3 / 32.8 ms, 2.2 %, 2.8 ms | 10.5 / 18.0 / 23.0 ms, 2.3 %, 2.7 ms |

All 9 scenarios after the changes (`reports/b9_modes_after.json`):

| Scenario | Latency median / p95 / p99 / max (ms) | Inference median | Frames processed | CPU | UI lateness p99 |
|---|---|---|---|---|---|
| Normal | 10.6 / 16.4 / 21.6 / 41.7 | 9.5 | 1349/1351 | 3.2 % | 4.7 ms |
| Normal + preview | 10.7 / 16.0 / 19.8 / 29.1 | 9.5 | 1351 | 3.9 % | 6.2 ms |
| Broadcast basic | 10.4 / 15.3 / 19.8 / 44.6 | 9.3 | 1351 | 2.6 % | 3.2 ms |
| Broadcast skeleton + trails + vectors | 10.2 / 14.5 / 17.6 / 21.5 | 9.0 | 1351 | 2.7 % | 3.6 ms |
| Broadcast transparent | 10.0 / 14.0 / 18.6 / 28.4 | 8.9 | 1351 | 3.8 % | 5.2 ms |
| Broadcast clown | 10.2 / 14.5 / 18.7 / 28.2 | 9.1 | 1351 | 3.1 % | 3.8 ms |
| Broadcast eye analytics | 10.2 / 14.4 / 18.6 / 28.0 | 9.2 | 1351 | 2.7 % | 3.6 ms |
| Broadcast everything | 10.0 / 14.1 / 18.2 / 25.7 | 9.0 | 1351 | 4.4 % | 5.7 ms |
| Background | 10.5 / 14.5 / 18.0 / 23.0 | 9.5 | 1351 | 2.3 % | 2.7 ms |

## Gesture-to-action breakdown (CP 48.5)

| Stage | Measured | Source |
|---|---|---|
| Stroke (onset -> distance reached) | 184-672 ms median by detector/direction | recordings |
| Decision after the stroke | 0 ms (up, sideways); down 192 ms finger / 367 ms hand | recordings, after D |
| Frame capture -> recognition | 10 ms median, <= 22 ms p99 | replay |
| Recognition -> dispatch (record created) | 10-11 ms median | replay |
| Dispatch -> verified result | browser time: scripted 150 ms; real YouTube next/previous 205-711 ms, pause 3-12 ms | replay; live tests (Brief 008) |
| Verified result -> UI thread (feedback can paint) | 1-3 ms | replay |

The immediate recognition banner appears when the record is created (before the browser
answers); "Success" appears only after the browser confirmed. The browser's own navigation and
the downward decision delay dominate perceived latency.

## Scheduling (CP 48.1-48.3)

Unchanged by evidence: hand tracking and recognition run on their own thread with
latest-frame handoff; segmentation and face models run in separate workers capped at 15 fps
and only while a feature needs them, fed after recognition with a read-only view; preview
decoding runs on the UI thread only for visible new frames (2 ms). With every optional feature
on, hand latency did not change (table above), so an adaptive processing budget was **not**
added - the simpler fixed scheduling already keeps control-critical work unaffected on this
machine. The privacy fallback (no stale mask shows the room) is unchanged.

## UI stalls (CP 48.6)

Programmatic resizes of the real window with the camera running took 17-48 ms each (16
resizes, cProfile: `QWidget.resize` ~4 ms, first paint ~4.5 ms, video paint 6.3 ms mean /
14.7 ms max) - the 110-180 ms pauses of Brief 008's stability sessions did **not** reproduce,
and the 393 ms stall remains unexplained. Not resolved; no optimization without a reproduced
bottleneck.

## Endurance (real webcam, automated, no person; CP 52.4)

| Run | Minutes | Capture / processing fps | Latency mean (p95) | Dropped / min | CPU | Memory first -> last minute | UI stalls (max) |
|---|---|---|---|---|---|---|---|
| Normal + live preview (real YouTube via a test browser) | 30.0 | 30.4 / 29.8 | 15.8 (24.3) ms | 27.0 | 4.4 % | 390 -> 382 MB | 20 (1,127 ms) |
| Broadcast + transparency + face/eye models | 30.0 | 29.8 / 27.5 | 12.5 (12.9) ms | **85.3** | 3.7 % | 449 -> 419 MB | 4 (351 ms; 3 at start) |
| Mode cycling every 20 s (29 transitions, 0 invariant violations) | 10.0 | 29.9 / 28.1 | 12.3 (12.9) ms | 72.0 | 2.7 % | 405 -> 388 MB | 5 (550 ms) |

No memory growth, no worker threads after close, all camera restarts succeeded; 24,254
preview frames received and 24,220 painted in 30 minutes.

Two findings:

* **Frames dropped at the handoff (up to 5 %).** This morning's camera delivered frames in
  bursts (arrival-time standard deviation up to 25 ms, CAMERA.md); with a single-slot handoff
  the first frame of a burst was overwritten before processing (about 10 ms) could take it,
  although average capacity was ample. Replay could not show it (its camera is periodic).
  Fix: a two-frame bounded buffer (`FRAME_BUFFER`, core/mailbox.py) - see the A/B below.
* **Stalls during the preview session.** In the 30-minute preview run, 16 stalls of 215-1,127
  ms started after minute 15 and continued to the end; during each, the camera and processing
  threads also made no progress (a process-wide pause). The Broadcast run without a browser
  had none after startup, and the replay benchmark with a simulated preview feed had none.
  Isolation: see the detached-preview run below.

### Frame buffer A/B (real webcam, Broadcast + transparency + face/eye models, 5 min each, alternating)

| Run | Buffer | Dropped / min | Processing fps | Latency mean (p95) |
|---|---|---|---|---|
| pair 1 | 1 | invalid: the computer went to sleep during the run (59 min, one 55-minute "stall") | | |
| pair 1 | 2 | 4.0 | 30.4 (capture 30.9) | 18.2 (36.2) ms |
| pair 2 | 1 | 39.5 | 29.8 (capture 30.7) | 12.9 (18.1) ms |
| pair 2 | 2 | **0.0** | 30.2 (capture 30.2) | 14.4 (26.9) ms |

Adopted (`FRAME_BUFFER = 2`): frames lost at the handoff fall from 39.5-85 per minute to 0-4,
so fast gestures keep all their frames; the cost is +1.5 to +6 ms mean latency (p95 up to one
frame interval), small next to the browser's 200-700 ms navigation. Frames are still processed
in order with their own timestamps; a third frame evicts the oldest, so latency stays bounded.

### Preview-session stalls: harness or product?

Same Normal Mode + live preview session, but the test harness closes its DevTools connections
(reader threads inside the application process) once the preview runs (`--preview-detach`),
12 minutes: stalls only at start (277 ms), at the scheduled camera restart (164 ms, 120 s) and
at the very end (1,873 ms - the script closes the browser on the UI thread); none in between,
28 fps of preview frames (20,189 received, 20,157 painted), 0.3 dropped frames per minute.
This points to the in-process browser automation, not the preview feature, as the cause of the
mid-run stalls of the 30-minute run - but that run's stalls began after minute 15 and this run
was shorter, so a long-run effect is not excluded. Open.

