# Gesture recognition

Rule-based recognition on top of hand tracking (`vision/`) and motion analysis (`motion/`).
Code: `src/interactive_scrolling/gestures/`. No confidence percentages are produced: every
decision follows the documented criteria below, and the UI shows candidate *progress* and,
for every rejection, the measured and the required value.

Version 0.3 (Brief 003) introduced one four-direction index-finger gesture family and the
single-hand half-heart. Version 0.4 (Brief 004) reworked the recognizer after the Director's
real-world test; version 0.5 (Brief 005) made it a motion engine with finger and fist detectors
([benchmark 005](../benchmarks/GESTURE_BENCHMARK_005.md)); the measurements behind every decision are in
[GESTURE_BENCHMARK_004.md](../benchmarks/GESTURE_BENCHMARK_004.md). User-facing guides:
[gestures](../guides/GESTURE_GUIDE.md), [calibration](../guides/CALIBRATION_GUIDE.md).

## Pipeline

```text
TrackingResult + MotionFrame (processing thread)
  -> GestureEngine.update()
       control-hand selection (AUTO / LEFT / RIGHT, ambiguity suspension)
       pose analysis (pose.py), hand scale, positioning hints, frame rate
       DirectionalSwipeRecognizer (4 directions), half-heart and stop recognizers
       conflict rules (global cooldown, static vs dynamic)
  -> GestureFrame (UI, diagnostics tap)   -> GestureEvent (confirmed)
                                               -> ActionDispatcher (actions/) -> controller
```

The engine never performs actions. Events go to the dispatcher, which checks the control mode,
the mapping, the event age and the controller context before anything is executed. Every
processed frame also goes to the in-memory diagnostics collector (`gestures/diagnostics.py`)
through a pipeline gesture tap.

## Coordinates and directions

* Positions: source pixels of the unmirrored camera frame. Distances and speeds are in **hand
  lengths** ("palm lengths"): the larger of the wrist-to-middle-knuckle distance and the
  knuckle width / 0.8 (`pose.hand_scale_px`), which stays stable when the wrist turns (the
  palm length alone varied 27-184 px within one recorded sweep). The swipe recognizer smooths
  this scale while the hand rests and freezes it during a stroke.
* *Down* / *up* follow the image. *Right* and *left* are the **user's own** right and left: the
  camera image is not mirrored, so a movement to the user's right moves towards the image's
  left. Preview mirroring is display-only.
* Physical direction and content are kept apart: by default moving the finger **up** shows the
  **next** Short (touchscreen direction, the Director's natural mapping); settings of version
  0.3 that still had "down = next" are migrated once with a notice (`settings_store`).
* Either hand works: nothing in the rules depends on handedness.

## Gestures

| Gesture | How to perform it | Default action |
|---|---|---|
| `INDEX_SWIPE_UP` | Pointing finger moves up (finger flick, wrist or hand) | Next Short |
| `INDEX_SWIPE_DOWN` | The same, downwards | Previous Short |
| `INDEX_SWIPE_RIGHT` | The same, to your right | Next browser tab |
| `INDEX_SWIPE_LEFT` | The same, to your left | Previous browser tab |
| `HALF_HEART` | One half of a two-handed heart, held still 0.5 s | Like Short |
| `STOP_GESTURE` | Open hand, fingers up, palm to the camera, held still 0.8 s | Pause / resume |

### Index swipes

Criteria at the Balanced preset (all directions; left/right may have their own distance):

* the **index fingertip** travels >= 0.8 hand lengths along the direction, measured from where
  it last rested, with a peak speed >= 2.0 hand lengths/s, within 0.7 s;
* the movement along the direction is >= 1.8 times the movement across it (within ~29 degrees);
  diagonals are rejected, never assigned to the nearer direction;
* confirmation is **early**: as soon as the distance is reached (the user does not have to
  finish an exaggerated movement). Waiting for the end of the stroke was measured
  (+0.30 s median) and rejected.

**Hand pose (`pose_rule="endpoints"`).**

* A stroke made with a pointing hand is confirmed at once: the hand must be pointing when the
  distance is reached, and either during at least half of the stroke or just before it
  started.
* "Just before" means pointing that was sustained, not a single stray frame: at least 60 % of
  the frames of the preceding 0.25 s, spanning at least 0.06 s, measured in time so it does
  not depend on the frame rate.
* A **downward finger flick** curls the index finger, so the hand reads as a fist during the
  stroke; requiring pointing throughout rejected almost all downward flicks (1/4).
* A stroke that started from held pointing but has the finger curled at the threshold is
  therefore a **pending flick**. It is confirmed when the finger recovers within 0.8 s
  (pointing again, or the fingertip moving back 0.25 hand lengths). It is rejected if the
  finger stays curled, because relaxing a pointing finger into a fist moves the fingertip
  the same way.
* An open hand or a fist moving is never a swipe.

**Arming (`arming="observe"`).** A newly tracked hand (after 0.3 s of stable tracking) can
swipe once the recognizer has seen it at rest for one frame. Strokes before that, or during the
0.5 s cooldown after a gesture, are followed; if they meet the motion criteria (and their start
was observed) they are remembered like a swipe so their return is suppressed too. Version 0.3
required 0.2 s of stillness instead: during continuous movement it armed only at the end of a
stroke and then confirmed the return - every recorded horizontal sweep came out in the opposite
direction (0/12; now 9/12).

**Return movements.** After a swipe every opposite stroke is its return until the fingertip
is back within 35 % of the swipe length of where the swipe started *and has paused there*
(below 0.5 hand lengths/s for 0.1 s), or 1.2 s after the swipe's movement ended. A stroke at
right angles is never a return. Ending the return phase after a pause *anywhere* was measured
and rejected (natural pauses between stroke and return are 0.2-0.37 s).

**Tracking dropouts.** Gaps of up to 0.2 s (fast movements blur) keep the current candidate.

### Any hand shape (Brief 006, default)

"Swipe with: any hand shape" runs two motion references through the same lifecycle; which one
measures a stroke is decided by the hand's geometry **at the onset**, so the user never chooses
a pose:

| Onset shape | Reference | Intent gating | Distance |
|---|---|---|---|
| pointing | index fingertip (finger detector, unchanged from 0.5; finger flicks wait for the finger to recover unless the palm moved with it) | pointing at the threshold or held before | `swipe_*_distance_palms` (0.8) |
| any other shape except the half-heart and the stop pose (`hand_shape`) | palm centre (`HAND` detector) | the palm was settled (drift <= 0.25 hand lengths) for 0.4 s before the movement | `fist_swipe_distance_palms` (0.5, "whole-hand swipe distance") |

During a whole-hand stroke the shape may change freely (a fist may open). Strokes may not start
while the hand is partly out of view at the bottom (lowest landmark > 0.92); a downward
whole-hand stroke is confirmed when the hand stops (or 0.6 s after the distance was reached)
while still tracked, so a hand lowered out of the picture is lost first and never confirmed.
Moving the hand away after a half-heart or a stop pose is a release, not a swipe.
"Pointing finger only" keeps the 0.5 behaviour (fewer accidental swipes, see the benchmark).

**Tracking quality rules (all detectors).** A second hand that overlaps the established control
hand and has been tracked for less than 0.3 s is a duplicate detection of the same blurred hand
and is ignored (it used to cancel fast swipes). A stroke never starts across a tracking gap
(> 0.1 s between samples: the displacement was not observed); a jump across a gap implying more
than 25 hand lengths/s, or more than 1 hand length between two frames on the whole-hand path,
ends the stroke; no confirmation or reversal is decided on the single frame after a gap.

**What motion cannot tell.** Raising the hand to get ready for a downward swipe is the same
movement as an upward swipe (trajectory, speed and position measured alike); the settled-hand
cue is the only separation. Hold the hand still for a moment before swiping.

### Motion-first engine (Brief 005)

All swipes run through one motion engine (`DirectionalSwipeRecognizer`) with three detector
configurations; they share stroke segmentation, direction scoring and the return memory:

| Detector | Motion reference | Activation (intent gating) | Default |
|---|---|---|---|
| finger | index fingertip | pointing at the threshold (and during half the stroke or held before it); a curl flick from a held pointing pose waits for the finger to recover; confirmed at once when the palm moves with the fingertip (>= 40 % of its travel) | on |
| fist | palm centre = mean of wrist and the four knuckles | a fist (pose FIST) held in >= 70 % of the frames of the 0.45 s before the stroke, spanning >= 0.25 s, and the palm still (drift <= 0.25 hand lengths) for 0.25 s right before it; fist-shaped strokes without that cue are followed silently and remembered so their returns cannot fire | experimental (style "fist" or "finger or fist") |
| palm | palm centre | an open hand held still before the stroke | experimental, off (rejected on real sweeps) |

**Why the palm centre for fists.** Opening or closing the hand moves the fingertips but hardly
the knuckles and wrist, so the palm centre does not report pose changes as motion; up and down
are symmetric whole-hand or wrist movements without finger flexion. The fingertip is kept for
the finger detector because small finger and wrist movements move it most.

**Directional score** (all detectors; heuristic, not a probability). From the stroke's start
(the last rest of the reference) the displacement `d` is measured in hand lengths in user space
(x = the user's right, y = down; the camera image is not mirrored). The direction is the
dominant axis of the velocity when the stroke starts. Along that axis: `d_axis` = displacement,
`peak` = highest axis speed, `d_cross` = displacement across it. The stroke is confirmed when
`d_axis >= distance(direction, detector)`, `peak >= 2.0` hand lengths/s, `d_axis >= 1.8 x d_cross`
(within ~29 degrees; diagonals are rejected) and the time since the start is <= 0.7 s. A reversal
(speed >= 0.8 the other way) starts the opposite stroke from the turning point. The progress
shown is `d_axis / distance`.

**One physical gesture, one event.** When any detector confirms, the other detectors are
blocked for the global cooldown and adopt the swipe (its start is looked up in their own
reference's position history), so its return is suppressed in all of them.

**Leaving the picture.** A downward stroke whose lowest hand landmark is below 85 % of the image
height is confirmed only once the hand stops inside the view (a hand lowered out of view was
read as a swipe down; real downward swipes ended at 62-74 %).

**Measured asymmetry.** A downward finger flick and the curl back after an upward flick are the
same movement (finger flexion +113 vs +137 degrees, palm ~0); smaller downward distances turned
those returns into false downward swipes. See the Brief 005 benchmark.

### Half-heart

One half of the two-handed heart with one upright hand: index finger curved over with its tip
hooking down, thumb pointing down below it, tips apart. Image-space rules (hand lengths):

| Criterion | Value | Separates it from |
|---|---|---|
| Index flexion (sum of 3 joints) | 80-230 degrees | pointing (straight), fist (folded) |
| Index tip to its knuckle | >= 0.5 | fist |
| Index tip below its highest joint | >= 0.12 | relaxed and C-shaped hands |
| Thumb not curled, pointing down | within 70 degrees of down | thumbs up |
| Thumb tip below index tip | >= 0.25 | relaxed hand hanging down |
| Tip gap | 0.3-2.2 | pinch |
| Tips on the same side of the hand axis | yes | |
| Middle, ring, little finger | not straight (< 35 degrees flexion) | open hand |
| Hand axis upright | within 65 degrees of up | sideways C, thumbs down |

The other fingers may curve with the index (version 0.4, `HEART_RULE="tolerant"`; version 0.3
required them folded): no additional half-heart frames in 5,579 recorded hand frames. Held
still for **0.5 s** (0.6 s before; no false half-heart at 0.3-0.6 s in the recordings), one
event per hold, release 0.25 s before the next. A **personal template** from Quick Calibration
(`pose.matches_personal_heart`) additionally accepts poses close to the user's own shape;
gap, thumb-below-tip, curved index and thumb not curled stay mandatory. No real half-heart
recording exists yet.

### Stop pose

All four fingers extended (3D joint angles), hand axis within 40 degrees of vertical
(calibration may widen it up to 70), still, held 0.8 s. Stillness is the net palm drift over
0.3 s (<= 0.25 hand lengths), not the instantaneous speed: at arm's length a hand is ~42 px
and landmark jitter alone read as ~1 hand length per second. In the recordings the open palm
at arm's length stayed visible for only ~0.5 s before MediaPipe lost it (and in one prompt it
was never detected); this is a camera/detector limit, answered with a "move closer" hint.
Image-space finger extension and shorter holds were measured and rejected (more false poses,
no recall gain).

## Conflict rules

* After any confirmed gesture, every other recognizer is blocked for 0.4 s.
* Static candidates (half-heart, stop) are cancelled while a swipe candidate is active.
* At most one event per frame.
* A disabled swipe direction is still followed (and its return suppressed) but never confirms.

## Control hand

* AUTO (default): the first hand alone in view becomes the control hand and keeps the role
  while tracked; with several possible control hands recognition is suspended.
* LEFT / RIGHT: only a hand whose smoothed handedness matches.
* Two hands closer than 1.2 hand lengths suspend recognition.

## Diagnostics and feedback

* Every rejection has a code (`RejectCode`) and, where it applies, measured/required values and
  the unmet pose conditions; `gestures/explain.py` turns them into one plain sentence.
* Frames carry positioning hints (hand smaller than 4.5 % of the image width, hand at the image
  edge, camera below 20 fps) and the hand scale.
* `GestureDiagnostics` counts per gesture: candidates formed, confirmed, rejected by code, and
  the browser outcome of each action; "Copy diagnostics" exports it without personal data.

## Settings

Presets (shown as Relaxed / Balanced / Precise) scale distance, speed and hold times (0.8x /
1.0x / 1.25x); under a named preset thresholds always follow the current preset values, so
improved defaults reach existing users. *Personal* holds the Quick Calibration result, *Custom*
hand-edited values. Editable in Developer Mode: swipe distance (up/down and left/right), speed,
holds, cooldown, return window, control hand, per-gesture enable and the mapping.
The recognition strategies themselves are `RecognizerOptions` (`V03_OPTIONS` reproduces
version 0.3 for the benchmark).

## Known limitations

* Brief 006: whole-hand swipes depend on holding the hand still for a moment first; rhythmic
  repeated whole-hand swipes without a pause are partly ignored (left-hand fist swipes 5/16 in
  the held-out look). The preparation raise before a downward whole-hand swipe can be taken as
  an upward swipe.
* Below ~20 fps or with frame loss, a missed upward finger flick can let its return be read as
  a downward swipe (synthetic degradations, benchmark 006).

* Fist control has no real recording; its numbers are semi-synthetic (Brief 005 benchmark).
* Finger curl flicks downwards remain ambiguous with the return of an upward flick; they wait
  for the finger to recover (moving the hand or wrist down is confirmed at once).

* Left/right swipes, the half-heart and the stop pose at a normal distance have no real
  recordings yet; their evidence is synthetic or a proxy (benchmark report).
* All recordings come from one person, one camera and one room; there is no independent
  held-out set, so all numbers are development results.
* A pointing hand dropped out of view can be read as a downward swipe (one recorded case).
* Finger flicks need about 30 fps; at 15 fps they are undersampled (hand movements still work).
* An opposite swipe right after a swipe needs the hand back near the start with a brief pause.
* The stop pose is unreliable with the open hand far from the camera (detection).
