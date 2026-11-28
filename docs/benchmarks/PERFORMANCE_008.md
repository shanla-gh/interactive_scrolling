# Performance - Brief 008 (0.8.0b1)

Development machine (Windows 11, 125 % scaling), physical webcam 1280x720 delivering 30 fps,
`scripts/stability_session.py` (automated sessions: camera restart every 120 s, window resized
every 30 s, gesture test mode, no person deliberately in view). CPU is the app process as a
share of all logical cores; the browser's own CPU is reported separately. Summaries:
`python scripts/summarize_sessions.py reports/b8_*.json` (reports are local, not committed).

## Application under equivalent conditions

| Scenario | Minutes | Capture / processing fps | Latency mean (p95) | Dropped / min | App CPU | Memory first -> last minute |
|---|---|---|---|---|---|---|
| 0.7.0b1 Developer Mode (Brief 007, 30 min) | 30 | 30.1 / 30.1 | 15.3 (23.5) ms | 0.5 | 4.6 % | 388 -> 367 MB |
| Normal Mode, webcam only | 4 | 30.1 / 30.0 | 15.4 (23.9) ms | 2.0 | 4.5 % | 385 -> 405 MB |
| Normal Mode + live Shorts preview (real YouTube, 28 fps) | 3 | 30.2 / 30.2 | 18.5 (23.0) ms | 1.7 | 4.6 % | 395 -> 408 MB |
| Broadcast + transparent background + face/eye models | 3 | 30.1 / 30.1 | 13.8 (21.3) ms | 0.3 | 4.9 % | 431 -> 420 MB |
| Combined: Normal + preview + segmentation/face/eye models | 3 | 30.1 / 30.1 | 19.6 (26.3) ms | 4.7 | 6.4 % | 434 -> 440 MB |
| Background Mode (timer opt-out, 2 runs) | 4 + 4 | 30.1 / 30.0 | 15.5-16.7 (19.3-20.6) ms | 0.2 | 3.7-3.9 % | 386 -> 388-401 MB |

* The live preview adds about 3 ms to the mean camera-to-result latency (UI thread decoding
  and painting about 28 frames/s compete with frame hand-off) and no measurable app CPU in
  this run; recognition keeps 30 fps (the preview never runs on the camera or recognition
  threads). 4,297 preview frames received in 3 minutes, 4,294 painted; transport median
  4.7 ms; the browser skipped none.
* Combined operation is the heaviest case: 19.6 ms mean latency, 6.4 % CPU, 4.7 dropped
  frames per minute (0.26 %).
* No memory growth beyond the first-minute variation; no worker threads after close in any
  run; camera restarts all succeeded (about 1 s).

## Live preview cost in the browser and the app

| Measurement | Result |
|---|---|
| Received frame rate | 25-30 fps (real YouTube; a still Short sends fewer frames) |
| Browser-to-app transport (median) | 4.7-12 ms |
| Page-to-app with a drawn clock (fixture) | 23-27 ms median |
| Decode per frame on the UI thread | 2.0 ms median |
| JPEG size | 30-55 KB at <= 640 px height |
| Browser CPU, preview on vs off (4 interleaved rounds of 6 s, settled page) | off 1.6-1.7 % (first round 7.5 % while loading), on 2.6-3.9 %: **+1.7 % of the machine** (20 logical cores, about a third of one core) at 28.5-30 fps |

## Doomscroll Together (loopback, `scripts/benchmark_coop.py`)

| Measurement | Result |
|---|---|
| Idle session CPU (pings every 2 s) | 0.0 % of the machine |
| Ping round trip | 1.4 ms (loopback) |
| Shared action: request -> Host executes (scripted 250 ms browser) -> result | 251.6 ms median, i.e. 1.6 ms app overhead |

Two computers on Wi-Fi or a VPN were not measured (no second computer). Screen-sharing delay
cannot be measured by the app.

## Background Mode frame drops (CP 43.2)

Brief 007 reported 53.5 dropped frames per minute (about 3 %) in a 5-minute Background Mode
run, with a capture rate of 30.8 fps (above the camera's 30 fps, i.e. bursty delivery) and
processing at 29.6 fps. Hypothesis tested in Brief 008: Windows 11 ignores the timer
resolution of a process without a visible window; the app now opts out
(`PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION`, `core/platform.py`).

| Run (4 min each, alternating) | Dropped / min | UI stalls | CPU |
|---|---|---|---|
| timer throttling kept, run 1 | 1.0 | 3 (max 498 ms; another test process ran briefly) | 3.8 % |
| timer throttling kept, run 2 | 1.5 | 1 (197 ms) | 4.2 % |
| opt-out, run 1 | 0.2 | 0 | 3.7 % |
| opt-out, run 2 | 0.2 | 0 | 3.9 % |

* The Brief 007 condition (53.5 dropped per minute) **did not reproduce** today, with or
  without the opt-out; capture ran at 30.0-30.1 fps instead of the bursty 30.8 fps of that
  run, so camera delivery bursts are the more likely cause of the 2026-11-27 drops. This is
  an explanation, not a proof.
* The opt-out gives a small, repeatable improvement (1.0-1.5 -> 0.2 dropped per minute, no
  stalls in Background Mode) and is kept; the motion engine is unaffected (gate unchanged).

## UI responsiveness (CP 43.3)

Stalls (UI thread blocked > 150 ms, watchdog thread) in the Brief 008 runs:

* at the end of the preview sessions (806 ms and 732 ms at exactly 180 s): the measurement
  script closes the test browser on the UI thread - a script artifact;
* in the first second (startup, model loading, first layout);
* 110-180 ms when the script resizes the window (every 30 s) and at the camera restart
  (120 s): the redesigned layout re-fits the camera and Now playing columns on resize, and
  the first paint at the new size took up to 94-124 ms (`video paint` section). Brief 007's
  30-minute run with the same resizing had one stall, so resizing is more expensive in the
  new layout. Users resize rarely; not optimized in this brief.
* one 393 ms stall during combined operation with no attributed section (last event: a
  Now playing paint 155 ms earlier). Not reproduced; cause unknown.

Rare Qt stalls are therefore **not** resolved.
