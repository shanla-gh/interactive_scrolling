# UI modes, transparent background, clown and eye analytics

## Presentation modes (M5)

| Mode | What is shown | Code |
|---|---|---|
| Developer | Full dashboard: video with skeleton, landmarks, boxes, trails, vectors; Gestures, Today, Browser, Co-op, Performance and View tabs; gesture history; activity log; status bar (FPS, latency, dropped frames, CPU/RAM, UI stalls) | `ui/main_window.py` |
| Content Creator | Frameless always-on-top overlay: camera, skeleton, optional trails/vectors, last gesture, action outcome, optional counters, optional transparent background; move, resize (16:9), opacity, layers, mode switches via right-click; double-click returns to Developer Mode | `ui/creator_overlay.py` |
| Background | Windows hidden; the tray icon stays visible in every mode | `ui/tray.py` |

* All modes are views of one runtime: switching never starts a second camera, dispatcher or
  bridge, never resets statistics or pairing and leaves no threads behind
  (`tests/integration/test_ui_modes.py`). Execution safety (Tracking only / Gesture test /
  Live control) is independent of the presentation mode; Ctrl+Alt+D works in every mode.
* Focus: the overlay is a `Tool` window with `WindowDoesNotAcceptFocus`,
  `WA_ShowWithoutActivating` and, on Windows, `WS_EX_NOACTIVATE`; clicking or dragging it keeps
  the browser as the active window.
* Tray colours: grey camera off, green tracking only, amber gesture test, red live control.
  Menu: status, start/stop camera, disable control, the three modes, quit. Quitting from any
  mode stops the camera and ends the process.
* Visual customization (*View -> Appearance...*): skeleton colour (or by hand), landmark size,
  line thickness, trail length, gesture feedback and status chips on/off, overlay corner,
  size and opacity; layer toggles in the View tab and the overlay menu. Persisted.

## Transparent background (CP 5.3)

* Model: MediaPipe Selfie Segmenter (landscape, 144x256 input, 250 KB, Apache-2.0), run on a
  320-pixel-wide copy at up to 15 FPS in its own worker, only while the transparent overlay is
  visible. The hand tracker always receives the original frame; the worker gets a read-only
  view after tracking.
* Compositing: person confidence -> soft alpha ramp (0.35-0.75) -> temporal average (weight
  0.5) -> alpha channel of the overlay's own downscaled copy. Masks older than 0.5 s or from
  another camera session are refused; then the camera image is hidden and a notice shown, so
  the room is never revealed unexpectedly.
* Observed on the reference photo: face, hair, hands and arms kept; a light sweater against a
  dark wall was partly faded (model confidence), which is a known limitation of this
  lightweight model in some lighting.

## Progressive Clown Transformation (M7)

* Face landmarks: MediaPipe Face Landmarker (478 points incl. irises, blendshapes, head pose),
  640-pixel-wide copy, up to 15 FPS, worker enabled only while the clown or eye analytics are on.
* Stages from the **active time of the current scrolling session** (REPORTING.md): 1 red nose
  at 10 min, 2 makeup (white eye diamonds, rosy cheeks, red lips) at 20 min, 3 full clown
  (white base, wide smile, arched brows, blue outlines, curly orange wig) at 30 min;
  thresholds configurable; *Preview* shows a stage at any time. The stage follows the session:
  it grows as the session continues and returns to 0 (fading out over ~1.5 s per stage) when
  the session ends (more than 2 minutes without active scrolling).
* Rendering: original procedural QPainter artwork anchored to landmarks of the current frame
  (follows rotation, mouth opening, blinking), landmark smoothing (60 ms), fade in/out, hidden
  0.25 s after the face is lost. Drawn in Developer and Creator Mode, on top of the transparent
  background. Nothing is captured or saved.

## Passive eye analytics (M8)

* States: facing the screen (head within 25 deg yaw / 20 deg pitch and irises within 0.12 of
  the baseline), looking away (beyond 1.6 times those limits), unknown (no face, ambiguous,
  eyes closed longer than 0.5 s, gaps over 0.5 s). Unknown is never counted as away; the three
  durations always add up to the analysed time.
* Blinks: blink blendshapes (closed > 0.5) lasting <= 0.5 s; reported as unavailable when the
  sampling rate is below 10 Hz.
* Calibration (optional, *Calibrate...*): 3 s looking at the screen centre; baseline = mean head
  angles and iris offset; refused if head variation > 4 deg or iris variation > 0.04 or fewer
  than 20 samples. Without calibration the baseline is "straight ahead". Whether calibration
  improves the estimate could only be checked with synthetic faces here (it shifts the
  baseline as intended); a real comparison needs the Director (checklist section 5). A
  multi-point regression was deliberately not built: a webcam cannot support precise gaze
  coordinates and the brief asks for unknown rather than invented precision.
* Storage: daily totals only (`eye_stats` table: screen, away, unknown seconds, blinks, longest
  screen period), flushed every 60 s; no landmarks, images or per-frame data. Never used to
  execute actions or enforce limits.

## Measured cost (CP 5.3 / 7.3, headless benchmark, 60 s each, 1280x720, same machine)

See [INTEGRATION_AUDIT_005.md](../audits/INTEGRATION_AUDIT_005.md) for the table.
