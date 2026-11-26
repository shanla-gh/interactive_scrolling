# Gesture recognition

Rule-based recognition on top of hand tracking (`vision/`) and motion analysis (`motion/`).
Code: `src/interactive_scrolling/gestures/`. No confidence percentages are produced: every
decision follows the documented criteria below, and the UI shows candidate *progress*
(fraction of the required distance or hold time) instead.

Version 0.3 (Engineering Brief 003) replaced the vertical-only finger swipe and the open-hand
sweep with one four-direction index-finger gesture family, and the thumbs-up with the
single-hand half-heart.

## Pipeline

```text
TrackingResult + MotionFrame (processing thread)
  -> GestureEngine.update()
       control-hand selection (AUTO / LEFT / RIGHT, ambiguity suspension)
       pose analysis (pose.py)
       DirectionalSwipeRecognizer (4 directions), half-heart and stop recognizers
       conflict rules (global cooldown, static vs dynamic)
  -> GestureFrame (UI)            -> GestureEvent (confirmed)
                                       -> ActionDispatcher (actions/) -> controller
```

The engine never performs actions. Events go to the dispatcher, which checks the control mode,
the mapping, the event age and the controller context before anything is executed.

## Coordinates and directions

* Positions: source pixels of the unmirrored camera frame; distances and speeds in **palm
  lengths** (wrist to middle-finger knuckle), so thresholds do not depend on the distance to
  the camera. During a stroke the largest palm length seen is used.
* *Down* / *up* follow the image. *Right* and *left* are the **user's own** right and left: the
  camera image is not mirrored, so a movement to the user's right moves towards the image's
  left. The preview mirror setting never influences recognition (inference always runs on the
  unmirrored frame); it only changes how the image is drawn.
* Either hand works: nothing in the rules depends on handedness. The control-hand preference
  (AUTO, LEFT, RIGHT) only decides *which* hand may issue gestures.

## Gestures

| Gesture | How to perform it | Default action |
|---|---|---|
| `INDEX_SWIPE_DOWN` | Point with the index finger (other fingers folded), move down quickly | Next Short |
| `INDEX_SWIPE_UP` | The same, upwards | Previous Short |
| `INDEX_SWIPE_RIGHT` | The same, to your right | Next browser tab |
| `INDEX_SWIPE_LEFT` | The same, to your left | Previous browser tab |
| `HALF_HEART` | One half of a two-handed heart with one hand, held still ~0.6 s | Like Short |
| `STOP_GESTURE` | Open hand, fingers up, palm to the camera, held still 0.8 s | Pause / resume |

### Index swipes (one recognizer, four directions)

Criteria at the balanced preset (all four directions share them):

* pointing pose (index extended, middle/ring/little finger curled) at the start of the stroke
  and in >= 60 % of its frames;
* the **index fingertip** travels >= 0.8 palm lengths along the direction, measured from where
  it last rested, with a peak speed >= 2.0 palm lengths/s, within 0.7 s;
* the movement along the direction is >= 1.8 times the movement across it (within ~29 degrees
  of the axis). Movements between the axes are **rejected**, never assigned to the nearer
  direction; the direction is committed when the stroke starts (dominant axis of the
  fingertip velocity) and a reversal restarts the opposite stroke from the turning point.

**Why the fingertip of a pointing hand.** The brief asked to compare (1) small index-finger-led
movements with little palm displacement and (2) moving the pointing hand. The fingertip
measurement supports both, as long as the index stays extended: a wrist-pivot moves the
fingertip with little palm movement, a whole-hand stroke moves both. What it does not support
is the *flick* (curling and extending the finger), because the pose requirement rejects it.
Evidence (replayed recordings, balanced preset):

| Style | Recording | Recall | False triggers |
|---|---|---|---|
| Finger-led swipes, finger partly curling (session 1) | down 4, up 4 | 1/4 down, 4/4 up | 1 wrong-direction swipe |
| Pointing hand moving (session 2) | down 4, up 4 | 4/4, 4/4 | 0 |

In the confirmed swipes the palm moved a median 0.74 of the fingertip distance (range
0.04-1.04, n = 14): the Director's natural swipes were mostly whole-hand movements, with some
wrist-led ones. Flicks remain ambiguous with their own return (ADR-013), so the selected
interaction is **a pointing hand moving in the direction**, which may be a small wrist movement
as long as the fingertip travels about one palm length. Without the pose requirement the same
data produced 17 events in the open-hand sweep segments (all in the wrong direction, see below) and false triggers in natural
movement, typing and two-hand segments (`--any-pose` diagnostic), so the pose requirement is
what keeps the gesture safe.

**One shared threshold set.** Horizontal and vertical thresholds are shared. Palm-length units
are isotropic and the existing data contains no horizontal index swipes that would justify
separate values; the presets and the distance/speed settings apply to all four directions. The
third recording session (`scripts/record_gestures.py --session 3`) collects the data needed to
revisit this.

### Return movements

After a swipe the hand moves back, about as fast and as far as the swipe, and in the recordings
often in several parts that overshoot the starting point. Lifecycle:
`REARMING -> IDLE -> CANDIDATE -> CONFIRMED -> COOLDOWN (0.5 s) -> REARMING -> IDLE`, plus a
*return phase* after each confirmed swipe:

* every stroke opposite to the last swipe is treated as its return while the return phase lasts;
* the phase ends when the fingertip is back within 35 % of the swipe length of where the swipe
  started **and has paused there** (below 0.5 palm lengths/s for 0.1 s), or when 1.2 s have
  passed since the swipe's movement ended;
* a stroke at right angles (for example a tab swipe after a Shorts swipe) is never a return.

So "next, then previous" needs only the return and a brief pause, not a long fixed delay, while
a return that flows on past the start cannot trigger the opposite action. A position-only rule
(without the pause) failed on the recordings at the HIGH preset: the third part of a return
started near the start and became a false SWIPE UP (regression test
`tests/regression/test_gesture_return_overshoot_triggers_opposite.py`).

A newly acquired hand must be tracked for 0.3 s and be nearly still for 0.2 s before its first
swipe, so raising a hand into view cannot trigger a swipe. Losing the hand cancels the stroke.

### Half-heart

One half of the familiar two-handed heart, made with one upright hand: the index finger curves
up and over towards the heart's centre line with its tip hooking down, the thumb points down
towards the heart's bottom point, the tips stay apart. Image-space rules (palm lengths):

| Criterion | Value | Separates it from |
|---|---|---|
| Index flexion (sum of 3 joints) | 80-230 degrees | pointing (straight), fist (folded) |
| Index tip to its knuckle | >= 0.5 | fist (tip tucked into the palm) |
| Index tip below its highest joint | >= 0.12 | relaxed and C-shaped hands (tips point sideways) |
| Thumb not curled, pointing down | within 70 degrees of down | thumbs up |
| Thumb tip below index tip | >= 0.25 | relaxed hand hanging down |
| Tip gap | 0.3-2.2 | pinch (tips touching) |
| Tips on the same side of the hand axis | yes | |
| Middle, ring, little finger | not extended | open hand |
| Hand axis upright | within 65 degrees of up | sideways C, thumbs down |

Then held still (palm <= 0.6 palm lengths/s) for 0.6 s; one event per hold; the pose must be
released for 0.25 s before it can trigger again. This is *not* the crossed-finger mini-heart and
not a pinch. **Verification status**: the thresholds are an engineering starting point checked
on synthetic hands (both hands, three sizes) and on all existing negative recordings (no false
half-hearts in 190 s of rest, natural movement, typing, face touching, two hands, thumbs up,
fist, pointing, open hand). No recording of a real half-heart exists yet; the Director's
session-3 recording is required before its recall can be stated.

### Stop pose

Unchanged from 0.2: all four fingers extended, hand axis within 40 degrees of vertical, still,
held 0.8 s. Pose classification uses the summed flexion of each finger's joints: extended <= 70
degrees, curled >= 140 (thumb <= 45 / >= 80), uncertain in between.

## Conflict rules

* After any confirmed gesture, every other recognizer is blocked for 0.4 s.
* Static candidates (half-heart, stop) are cancelled while a swipe candidate is active.
* At most one event per frame.
* A disabled swipe direction is still followed (and its return suppressed) but never confirms,
  so a movement in a disabled direction cannot be misread as another direction.

## Control hand

* AUTO (default): the first hand alone in view becomes the control hand and keeps the role while
  tracked. If several hands could take the role, recognition is suspended.
* LEFT / RIGHT: only a hand whose handedness (majority over the last 15 frames, ignoring labels
  with score < 0.7) matches.
* Two hands closer than 1.2 palm lengths suspend recognition (identity may swap).

## Settings

Presets scale distance, speed and hold times: LOW 1.25x, BALANCED 1.0x, HIGH 0.8x. Editable:
swipe distance and speed, half-heart and stop hold, swipe cooldown, return window, control hand,
per-gesture enable, gesture-to-action mapping (any gesture to any available action or none).
Settings files of version 0.2 are migrated on first load and backed up
(`settings.json.v1-backup`).

## Benchmark (CP 4.5)

`scripts/evaluate_gestures.py recordings/*.json [--preset ...] [--mirror]` on the two Director
recordings (one person, one camera, Nov 2026). Sample sizes are small: these are engineering
checks, not accuracy claims.

| Category | n | Balanced | Low | High | Mirrored (balanced) |
|---|---|---|---|---|---|
| Index swipe down (pointing hand) | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| Index swipe up (pointing hand) | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| Finger-led swipes (session 1) | 8 | 5/8, 1 false | 1/8 | 5/8, 2 false | 5/8, 1 false |
| Index swipe left / right | 0 | no recordings | | | |
| Half-heart | 0 | no recordings | | | |
| Stop pose | 3 | 0/3 in the prompt window | 0/3 | 0/3 | 0/3 |
| Return movements suppressed | | 13 | 12 | 21 | 13 |
| False triggers, 190 s of negatives (24 segments) | | 0 | 0 | 0 | 0 |

Negative segments: rest, natural movement, typing, face touching, two hands, open hand held,
fist, pointing held, thumbs up (the old like) and open-hand sweeps (the old horizontal gesture).

* **Mirrored replay** flips the recordings and swaps the handedness labels; a mirrored right hand
  is geometrically a left hand, so this is a simulation of left-hand use on real motion, not a
  left-hand recording. Results are identical.
* **Stop pose**: in two of the three prompts MediaPipe lost the open hand at arm's length for
  most of the prompt or measured the fingers as half-bent; when the open palm was tracked and
  held, the stop confirmed, but only after the prompt window ended. The 0.2 recognizer scored
  the same 0/3; this is a tracking limitation for open palms far from the camera, recorded for
  the Director checklist.
* **The 4/12 open-hand sweeps of version 0.2**: their rejection reasons were mostly direction
  reversals, strokes too short and the open pose not being held during fast movement. The
  replacement cannot be scored on those recordings: they are open-hand movements and are now
  correctly ignored (0 events). The pose-independent diagnostic (`--any-pose`) on the same 12
  sweeps produced **0 correct and 17 opposite-direction events**. The traces show why: before
  each sweep the Director moved the hand to a starting position with a stroke of about 6 palm
  lengths/s in the opposite direction, the real sweep followed at 16-19 palm lengths/s, and the
  first stroke from rest was taken as the gesture, with the real sweep then suppressed as its
  return. This is the same back-and-forth ambiguity that rules out flicks (ADR-013).
  Consequences: (1) the pointing-pose requirement is what prevents it (a preparation movement
  made while the hand is still opening or turning is not a pointing stroke); (2) a user who
  pre-positions the hand **while already pointing** would trigger the opposite tab switch,
  which no recording can rule out yet. A minimum resting time before a stroke ("arming dwell",
  tried at 0.1-0.3 s) did not resolve the inversion (at best 3 correct / 10 wrong) and lost real
  upward swipes (4/4 -> 3/4 at 0.1 s, 1/4 at 0.2 s), so it was not adopted. Speed does not
  separate gesture from return either: after the vertical swipes, returns were as fast as or
  faster than the swipes. Left/right swipes therefore remain **verification pending** until
  the session-3 recording and the Director checklist (four repeated right swipes must give four
  next-tab actions and no previous-tab action).

## Known limitations

* Left/right swipes and the half-heart have no real recordings yet (synthetic tests only).
* Back-and-forth ambiguity: a fast preparation movement made while already pointing, in the
  direction opposite to the intended swipe, is recognized as a swipe (see the benchmark).
* All calibration data comes from one person, one camera and one room.
* Holding an open hand still for 0.8 s is a stop gesture.
* An opposite swipe directly after a return needs a brief pause (about 0.1-0.2 s) at the start.
* The stop pose is unreliable when the open hand is far from the camera (tracking).
