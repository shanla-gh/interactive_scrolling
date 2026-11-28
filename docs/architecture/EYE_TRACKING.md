# Passive eye tracking (Brief 009)

Passive only: nothing in this document can trigger, move, click, pause, switch or influence
any action or gesture mapping. Active gaze control is postponed until after v1.0.

## Pipeline

One face model for everything (MediaPipe Face Landmarker: 478 landmarks including iris
centres, blink blendshapes, facial transformation matrix), on a 640-pixel copy at up to 15 fps
in its own worker, **only** while the clown effect, eye analytics or the eye overlay is on.
No additional model was added.

| Quantity | Kind | Source |
|---|---|---|
| eye contours, iris centres | measured (landmarks) | face model |
| eye openness | model output | blink blendshapes |
| head yaw / pitch | estimated | facial transformation matrix (`face_tracker.head_angles`) |
| head roll | estimated | angle of the eye-corner line (`wellbeing/gaze.py`) |
| iris offset per eye | measured relative position | iris vs eye corners / eyelid midpoint, in eye widths |
| gaze direction | **estimate** | head yaw/pitch + eyeball rotation asin(offset / 0.42 eye widths) |
| quality 0-1 | heuristic | eye openness x head turn (full below 30 deg, zero at 50 deg) x eye size |

The gaze direction is an approximation in degrees, not a measured 3-D ray: a webcam provides
no eye depth, no per-person eyeball model and no infrared corneal reflection.

## Eye and gaze overlay

`visualization/eye_overlay.py`, optional (More -> *Show eye and gaze overlay (estimate)*, or
Broadcast settings), in the camera view and the Broadcast overlay, independent of the clown:
thin eye outlines, iris dots, one thin vector per eye and a combined arrow from between the
eyes. Vector opacity follows the quality; below 0.35 the vectors are hidden and the outlines
turn grey with "gaze: low tracking quality"; after 0.3 s without a face everything disappears.
The direction is smoothed for display only (120 ms). Renders on a synthetic face:
`scripts/render_gaze_overlay.py`.

## Calibration and a passive gaze point

Not implemented in the application. Whether a webcam estimate is good enough for a
screen-region crosshair can only be measured with a person: `scripts/evaluate_gaze_calibration.py`
shows 9 calibration points, then 8 different evaluation points and a final centre point
(drift), fits an affine and a quadratic ridge regression on the calibration samples only,
and reports median / p90 pixel error, error as a share of the screen diagonal, 3x3 region
accuracy, tracking availability and drift. It stores only those numbers. **No measurement
exists yet** (no person was available); the crosshair and a gaze heatmap stay unimplemented
until it shows useful accuracy (CP 49.6, 50.2).

## Analytics (unchanged, reviewed)

Screen-facing / looking-away / unknown durations, blinks (only when sampling >= 10 Hz), blink
rate per screen-facing minute, share of known time, longest screen-facing period; daily totals
only, local, optional, clearable. Unknown (no face, ambiguous, eyes closed, gaps) is never
counted as away. Wrapped shows an optional "Eyes (estimated)" line with the unknown time.
These are estimates of head and eye orientation, not attention, engagement or wellbeing.
