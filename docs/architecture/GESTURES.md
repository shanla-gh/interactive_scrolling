# Gesture recognition

Rule-based recognition on top of hand tracking (`vision/`) and motion analysis (`motion/`).
Code: `src/interactive_scrolling/gestures/`. No confidence percentages are produced: every
decision follows the documented criteria below, and the UI shows candidate *progress*
(fraction of the required distance or hold time) instead.

## Pipeline

```text
TrackingResult + MotionFrame (processing thread)
  -> GestureEngine.update()
       control-hand selection (AUTO / LEFT / RIGHT, ambiguity suspension)
       pose analysis (pose.py)
       recognizers with explicit lifecycles (recognizers.py)
       conflict rules (global cooldown, static vs dynamic)
  -> GestureFrame (UI)            -> GestureEvent (confirmed)
                                       -> ActionDispatcher (actions/) -> controller
```

The engine never performs actions. Events go to the dispatcher, which checks the control mode,
the mapping, the event age and the controller context before anything is executed.

## Coordinates and directions

* Positions: source pixels of the unmirrored camera frame; distances and speeds in **palm
  lengths** (wrist to middle-finger knuckle), so thresholds do not depend on the distance to
  the camera. During a stroke the largest palm length seen is used (the palm looks shorter
  while the hand is turned edge-on).
* Vertical: *down* means the hand moves towards the bottom of the image (and of the user's
  view); mirroring does not change it.
* Horizontal: *right* and *left* are the **user's own** right and left. The camera image is
  not mirrored, so a movement to the user's right moves towards the image's left. The preview
  mirror setting has no influence on recognition (inference always runs on the unmirrored
  frame).

## Gestures

| Gesture | How to perform it | Criteria (balanced preset) | Default action |
|---|---|---|---|
| `FINGER_SWIPE_DOWN` | Point with the index finger (other fingers folded) and move the whole hand down quickly | pointing pose at the start and in >= 60 % of the stroke; >= 0.8 palm lengths from the last resting position; peak >= 2.0 palm lengths/s; <= 0.7 s; vertical/horizontal >= 1.8 | Next Short |
| `FINGER_SWIPE_UP` | Same, moving up | as above | Previous Short |
| `HAND_SWIPE_RIGHT` / `_LEFT` | Open hand, big fast sweep to your right / left | open hand in >= 70 % of the stroke (may start curled); >= 0.75 palm lengths; peak >= 2.8 palm lengths/s; <= 0.9 s; horizontal/vertical >= 1.8 | none yet (M4: switch to study app / return to social app) |
| `THUMBS_UP` | Fist with the thumb pointing up, held still | four fingers curled, thumb extended, thumb within 40 degrees of vertical and its tip the highest landmark; palm speed <= 0.6 palm lengths/s; held 0.6 s | Like Short |
| `STOP_GESTURE` | Open hand, fingers up, palm to the camera, held still | all four fingers extended, hand axis within 40 degrees of vertical; still; held 0.8 s | Pause / resume |

Pose classification uses the summed flexion of each finger's three joints from the normalized
3D landmarks: extended <= 70 degrees, curled >= 140 degrees (thumb: <= 45 / >= 80), anything in
between is *uncertain* and matches no pose.

## Lifecycles

Swipes: `REARMING -> IDLE -> CANDIDATE -> CONFIRMED -> COOLDOWN -> REARMING -> IDLE`.

* A candidate starts when the axis speed exceeds 0.8 palm lengths/s and is measured from where
  the point last rested. It confirms as soon as the distance is reached (low latency) or is
  rejected with a reason (too slow, diagonal, too short, pose not held, return movement,
  tracking lost). A reversal rejects it and starts the opposite candidate from the turning
  point, so a wind-up that flows into the real movement is measured correctly.
* After a confirmation: cooldown 0.6 s for the same gesture; an opposite-direction swipe
  starting within 1.0 s after the swipe's movement has *ended* is treated as the hand's return
  movement and ignored.
* A newly acquired hand must be tracked for 0.3 s and be nearly still for 0.2 s before its first
  swipe, so raising a hand into view cannot trigger a swipe.

Static poses: `IDLE -> CANDIDATE (holding) -> CONFIRMED -> COOLDOWN -> REARMING (until the pose
has been released for 0.25 s) -> IDLE`. Holding a pose produces exactly one event; pose dropouts
up to 0.15 s are tolerated; movement cancels the hold.

Engine-wide: after any confirmed gesture, every other recognizer is blocked for 0.4 s; static
candidates are cancelled while a swipe candidate is active; at most one event per frame.

## Control hand

* AUTO (default): the first hand alone in view becomes the control hand and keeps the role while
  tracked. If several hands could take the role, recognition is suspended.
* LEFT / RIGHT: only a hand whose handedness (majority over the last 15 frames, ignoring labels
  with score < 0.7) matches.
* Two hands closer than 1.2 palm lengths suspend recognition (identity may swap).
* Losing the control hand cancels all candidates; a new track starts fresh.

## Calibration evidence

Thresholds were set from two labeled recordings of the Director performing each pose and gesture
plus natural non-gesture movement (`scripts/record_gestures.py`, landmark numbers only, kept
locally) and replayed with `scripts/evaluate_gestures.py`. Results at the balanced preset:

| Item | Result |
|---|---|
| Pointing-hand swipes down / up (session 2) | 4/4 and 4/4, every return movement suppressed |
| Thumbs-up presentations | session 1: 2/2; session 2: 4 events for ~7 short presentations, never two per presentation |
| Stop pose | fired once whenever the open hand was tracked and held; two prompts lost hand tracking entirely |
| Hand sweeps | 4 of 12 detected (sweeps were small and fast; LOW 1/12; HIGH 5/12 plus one wrong-direction sweep) |
| False triggers in negative segments (rest, natural movement, two hands, typing, face touching) | 0 at every preset; at HIGH one false thumbs-up occurred between sweeps |

What the data changed: (1) finger "flicks" (curling and extending the index finger) are
symmetric with their own return movement and with preparation movements, so they cannot be
disambiguated; the finger swipe is therefore defined as a moving *pointing hand*, and flicks
are unsupported. (2) Return movements are as fast and as large as the swipe itself, starting
0.1-0.3 s after it ends, hence the return window measured from the end of the movement. (3)
Real sweeps start with a curled wind-up, hence motion-based start, open pose during the stroke
and reversal from the turning point. (4) MediaPipe's handedness label flips during fast
movement, hence label smoothing. (5) An edge-on wind-up looks like a thumbs-up for ~0.5 s,
hence the 0.6 s hold.

## Latency

* Computation: gesture recognition takes ~0.02 ms per frame (measured in the stability session).
* Confirmation latency is dominated by the gesture itself: swipes confirm when the distance is
  reached, 0.21-0.43 s after the stroke left its resting position in the recordings; static
  poses confirm after their hold time (0.6 s / 0.8 s) by design.

## Known limitations

* Hand sweeps miss about two thirds of small sweeps at the balanced preset and overlap with
  some natural movements (face touching); they trigger no action in this version.
* Holding an open hand still for 0.8 s (for example before a sweep) is a stop gesture.
* An intended opposite swipe must start more than 1 s after the previous swipe's movement ended.
* Finger flicks are not recognized as swipes, and a flick may occasionally register as the
  opposite swipe (observed once in the flick recording).
* All calibration data comes from one person, one camera and one room.
