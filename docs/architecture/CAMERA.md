# Camera capture: capabilities, frame rate and timestamps (Brief 009)

## What the development webcam really delivers

`scripts/probe_camera_modes.py` opens the camera with every combination of backend (Media
Foundation, DirectShow), pixel format (driver default, MJPG, YUY2) and request (1920x1080@30,
1280x720@30, 1280x720@60, 640x480@30, 640x480@60, 640x480@120), reads frames for 3 s and
counts delivered and *unique* frames with `perf_counter` (`reports/b9_camera_modes.json`).

| Request | Claimed by the driver | Delivered | Unique frames |
|---|---|---|---|
| 1920x1080@30 (any backend) | 1280x720 | 1280x720 | 30 fps |
| 1280x720@30 / @60 | Media Foundation: 30 fps; DirectShow: 30 / **60** | 1280x720 | **30 fps** |
| 640x480@30 / @60 / @120 | Media Foundation: 30; DirectShow: 30 / **60 / 120** | 640x480 | **30 fps** |

* The camera's maximum is **1280x720 at 30 frames per second** in every backend and format.
  DirectShow reports 60 and 120 fps that it does not deliver - an API return value is not
  proof (CP 47.2).
* The application requests 30 fps by default (`CameraSettings.fps`), can request 15/30/60 in
  Camera settings, and shows the measured rate. Nothing in the motion code assumes a fixed
  frame interval: speeds use actual frame timestamps; the frame-rate-aware rule of Brief 009
  measures the interval it sees.
* Higher frame rates could not be tested on real hardware here; the 60 fps path is exercised
  only with synthetic timing in unit tests.

## Delivery timing

Frames arrive in bursts. In one 6-second run through the application's camera class, the
intervals between `read()` returns had a median of 32.4 ms but a **standard deviation of 25 ms**
(1st-99th percentile spread 77 ms); the driver's own sample times (`CAP_PROP_POS_MSEC`, Media
Foundation) were 33.34 ms apart with a 0.9 ms standard deviation. Typical frames arrived about
27 ms after the earliest-delivered ones. The probe runs saw 4-8 ms standard deviation, so the
burstiness varies between runs.

`DriverClock` (`vision/camera.py`) maps the driver sample times onto the application clock:
offset = smallest observed (arrival - sample), creeping up by 0.01 ms per frame against clock
drift, so a mapped time is never later than the arrival; invalid values (missing, not
increasing, jumps over 1 s) fall back to the arrival time. The result is stored as
`Frame.sample_ns` / `ProcessedFrame.sample_ns` and saved by `scripts/record_gestures.py`.

**Recognition still uses the arrival time** (`timestamp_ns`). The engine's thresholds were
tuned on arrival-timed recordings, and replaying them with a periodic approximation of the
driver times regressed (+2 false events, duplicate swipes; GESTURE_BENCHMARK_009.md, H). The
approximation cannot reconstruct true sample times of late-delivered frames, so the honest
next step is new recordings that contain both times.

## Frame handoff

The capture thread publishes each frame to a bounded mailbox; the processing thread takes the
oldest pending frame. Until Brief 009 the mailbox held one frame, and a frame replaced before
processing was counted as dropped. With bursty delivery that lost up to 5 % of the frames in
real-camera sessions (39.5-85 per minute) although processing (about 10 ms) had ample average
capacity. Since Brief 009 it holds **two** frames: both frames of a burst are processed, a third
evicts the oldest, nothing accumulates. Real-camera A/B: 39.5 -> 0.0 dropped per minute, +1.5
to +6 ms mean latency (PERFORMANCE_009.md).
