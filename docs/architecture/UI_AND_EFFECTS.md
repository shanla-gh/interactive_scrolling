# UI modes, transparent background, clown and eye analytics

## Normal Mode layout (Brief 008)

Brief 008 replaced the developer dashboard (header with camera selectors, a row of gesture
buttons, five side tabs and a status bar) with one product layout. Product name and code
names: Normal Mode = `ui_mode "developer"`, Broadcast Mode = `"creator"`, Background Mode =
`"background"` (the internal names are unchanged so settings and tests keep working).

```
top bar     Interactive Scrolling  beta 0.8.0b1   ● Camera on    Camera settings  [Normal|Broadcast]  More  [Stop camera]
centre      Your camera (16:9)                     Now playing (9:16)        Browser
            gesture strip: Gestures [Off|Test|Live] state  last result      Doomscroll Together
                           Practice  Gesture settings  [Stop Ctrl+Alt+D]    Today
bottom      ▸ Activity & diagnostics   CAM / PROC fps, latency, CPU, RAM ...   Copy diagnostics
```

| Area | Contents | Code |
|---|---|---|
| Top bar | name, version, camera state, *Camera settings*, Normal/Broadcast, *More* (Background Mode, Broadcast settings, practice, gesture settings, face effects, daily report, browser setup, copy diagnostics, getting started, show Now playing), Start/Stop camera | `ui/main_window.py` |
| Camera settings | device, scan, resolution, frame rate, mirror, camera-view layers, colours and sizes; locked while the camera runs | `ui/camera_settings.py` |
| Your camera | 16:9 image at the top of its column; skeleton, motion arrow, hints and gesture banners; brackets, grid, status chips, recognizer internals, hand box and label are off in this style (`VideoView.minimal`) | `ui/video_view.py` |
| Gesture strip | Off / Test / Live (Live in red), one-line state, last result, Practice, Gesture settings, Stop (with the global shortcut) - always visible, never inside a menu | `ui/control_bar.py` |
| Now playing | the live Shorts preview (`docs/architecture/LIVE_PREVIEW.md`), 9:16, or one sentence on how to start it / why it is hidden; can be hidden (More), which also ends the capture | `ui/preview_view.py` |
| Browser | connected browser, Shorts readiness and reason, "controlled from the app" while the preview path is active, *Setup and pairing* (dialog with the former Browser tab), *Stop preview* | `ui/session_panel.py` |
| Doomscroll Together | Host / Join dialogs, invitation (code, address, copy, new code), approve/decline/remove, shared control switch, last shared action with who did it, per-player counts, Duo Wrapped | `ui/together.py` |
| Today | session time, scrolling today, Shorts navigated; *Report* opens the former Today tab (daily report, limits, Wrapped, eye analytics) | `ui/session_panel.py` |
| Activity & diagnostics | collapsible (state remembered): Activity (gesture history and log), Recognition (former Gestures tab), Performance (performance, tracking and motion panels), Browser and Together (bridge, preview fps/transport/skips, Together round trip and confirmation time); the header line keeps the live figures | `ui/console.py` |

Layout rules: the right column is 292 logical pixels; Now playing is as wide as a 9:16 picture
of the stage height, at most 36 % of the stage; the camera keeps 16:9 and shrinks on short
windows so the strip always fits; nothing scrolls except the right column on very small
windows and the console lists. Minimum window 960x560 logical pixels. Verified on rendered
screenshots at 1366x768 100 %, 1920x1080 125 % and 150 % (`scripts/capture_screenshot_sets.ps1`).

Visual language (`ui/theme.py`): neutral dark surfaces, thin separator lines instead of boxes,
one restrained green (on, primary action), red only for stop, Live control and errors, the
system UI font everywhere except the diagnostics console, sentence-case labels.

## Presentation modes (M5)

| Mode | What is shown | Code |
|---|---|---|
| Normal (formerly Developer) | the layout above | `ui/main_window.py` |
| Broadcast | Frameless always-on-top overlay: camera, skeleton, optional trails/vectors, last gesture, action outcome, gesture-control chip, optional session timer/counters, optional transparent background; move, resize (16:9), opacity, layers; **Broadcast settings** dialog (Brief 008) opened from More, the overlay's *Settings* button (shown while the mouse is over the overlay), its right-click menu and the tray; double-click returns to Normal Mode | `ui/creator_overlay.py`, `ui/broadcast_settings.py` |
| Background | Windows hidden; the tray icon stays visible in every mode | `ui/tray.py` |

* All modes are views of one runtime: switching never starts a second camera, dispatcher or
  bridge, never resets statistics or pairing and leaves no threads behind
  (`tests/integration/test_ui_modes.py`). Execution safety (Off / Test / Live control) is
  independent of the presentation mode; Ctrl+Alt+D works in every mode.
* Focus: the overlay is a `Tool` window with `WindowDoesNotAcceptFocus`,
  `WA_ShowWithoutActivating` and, on Windows, `WS_EX_NOACTIVATE`; clicking or dragging it keeps
  the browser as the active window.
* Tray colours: grey camera off, green tracking only, amber gesture test, red live control.
  Menu: status, start/stop camera, disable control, Normal / Broadcast / Background Mode,
  Broadcast settings, quit.

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
* Stages from the **active time of the current scrolling session** (REPORTING.md), thresholds
  configurable (default 10 / 20 / 30 min); *Preview stage* shows a stage at any time. The stage
  grows as the session continues and returns to 0 when the session ends.
* **Brief 008 redesign - makeup, not a mask.** Stage 1: red nose on the nose tip. Stage 2: red
  lip colour multiplied onto the lips (their light and texture stay visible; an open mouth
  stays open). Stage 3: light white base, translucent (strength 10-70 %, default 35 %,
  *Broadcast settings -> White makeup*), feathered in 10 layers towards the face outline and
  towards the eyes, eyebrows and lips, which stay uncovered. Removed: curly orange wig, white
  eye diamonds, blue outlines, painted smile, black brows, rosy cheeks, opaque base. The
  person's own hair is never covered.
* Rendering: procedural QPainter artwork anchored to landmarks of the current frame, landmark
  smoothing (60 ms, display only), fade in/out, hidden 0.25 s after the face is lost. Drawn in
  Normal and Broadcast Mode, on top of the transparent background. Nothing is captured or
  saved. Previews on a synthetic face built from MediaPipe's canonical face mesh:
  `scripts/render_clown_stages.py` (no real person; real-person appearance needs the Director).

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
