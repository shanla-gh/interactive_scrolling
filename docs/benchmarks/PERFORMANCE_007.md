# Performance and stability - Engineering Brief 007

Date: 2026-11-27. Development machine (Windows 11, 1920x1080 at 125 %, webcam at 1280x720,
30 fps delivered). All runs are **automated** GUI sessions (`scripts/stability_session.py`),
not human use. "Hand in view" = share of 1-second samples in which the tracker reported a
hand; whether a person was present is not known (no images are stored). Comparisons are only
made between runs with the same hand condition.

## Long-duration runs (CP 33.3)

| Run | Mode | Optional models | Hand in view | Capture / processing fps | Latency mean (p95) | Inference | CPU | Memory first -> last min | Camera restarts | Dropped | UI stalls |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 min | Developer | off | 56 % | 30.1 / 30.1 | 15.3 ms (23.5) | 14.4 ms | 4.6 % | 389 -> 367 MB | 5/5 ok | 15 | 1 (344 ms) |
| 10 min | Broadcast, transparent | segmentation + face + eye analytics | 0 % | 30.9 / 29.7 | 12.0 ms (12.8) | 9.0 ms | 4.6 % | 440 -> 430 MB | 1/1 ok | 512 | 0 |
| 5 min | Background (tray) | off | 0 % | 30.8 / 29.6 | 11.9 ms (12.3) | 8.8 ms | 2.7 % | 387 -> 342 MB | - | 268 | 0 |
| 10 min | cycling Developer -> Broadcast -> Background every 20 s | on, transparent | 0 % | 30.9 / 29.7 | 12.2 ms (12.9) | 9.0 ms | 3.8 % | 426 -> 420 MB | 2/2 ok | 554 | 1 (194 ms, at shutdown) |

* No memory growth in any run; no worker thread left after closing; shutdown 0.28-0.47 s.
* Mode cycling: 29 transitions, 7.2 ms mean (13.5 p95); invariant checks every second found
  **no violation**: the gesture-control mode never changed, one capture and one processing
  worker, segmentation running exactly while the transparent overlay was visible.
* **Open finding**: while the main window is hidden (Broadcast, Background, cycling) about
  0.9 frames/s are dropped (3 %) against 0.01/s with the window visible, and latency is ~2 ms
  higher than the visible no-hand run of Brief 006. The cause is not identified (a likely
  candidate is coarser thread wake-up while no window of the process is visible); recognition
  still runs at ~29.7 fps.
* UI stalls: 344 ms inside Qt's event loop outside any application handler (no worker gap,
  no garbage collection) - the same category as the historical rare stalls; not resolved.

## Optional model cost (headless pipeline benchmark, no hand in view)

| Configuration | Capture / processing fps | Inference mean (p95) | Latency mean (p95) | CPU | Memory |
|---|---|---|---|---|---|
| hand tracking only | 30.3 / 30.5 | 9.3 ms (11.7) | 9.7 ms (12.3) | 2.8 % | 247 MB |
| + segmentation + face landmarks | 30.1 / 30.5 | 10.5 ms (16.5) | 11.0 ms (17.8) | 3.3 % | 293 MB |

Segmentation and face inference run only when needed (transparent overlay visible; clown or
eye analytics on) - verified by the cycling invariants and the existing tests.

## Before / after (equivalent conditions only)

| Measure | Brief 006 (0.6.0b1) | Brief 007 (0.7.0b1) |
|---|---|---|
| Developer Mode, no hand, 6 min | 30.4 fps, 9.6 ms, CPU 3.9 % | not repeated (the 30-min run had a hand in view) |
| Developer Mode, hand in view | Brief 005: 14.0 ms (6 min) | 15.3 ms (30 min, 56 % of the time) |
| Recognition per frame (replay) | 0.208 ms | unchanged engine |
| Broadcast overlay compositing | ramp + EMA | + enclosed-hole fill: ~2 ms more per overlay frame at 480x270 (synthetic measurement) |
| Display smoothing | none | One Euro on the drawn landmarks only (negligible cost) |

Not measured: a session with a visible moving hand performed by a person (no participant);
performance on a second computer.
