# Gesture benchmark - Engineering Brief 006 (pose-independent motion)

Date: 2026-11-27. Version 0.6.0b1. Continues [GESTURE_BENCHMARK_005.md](GESTURE_BENCHMARK_005.md).
Tool: `scripts/benchmark_motion.py` (development / held-out rows; wrong-direction, duplicate
and ordinary-activity events counted separately; `--degrade` for synthetic degradations).

**Read this first.** Real recordings: sessions 1-2 (Brief 004) and the Director's session 5
(right and left hand, about 3 minutes each, recorded 2026-11-27). Everything is one person.
The left-hand session was declared *held out* before tuning and scored once (section 4); its
fist segments were then analysed, so **from that point no independent data remains** and every
later number is development data. Evidence classes: **real** (recorded), **real use** (the
Director's statistics database, unlabelled), **synthetic** (degraded or scripted).

## 1. What the session-5 recordings and real use showed

| Finding | Evidence |
|---|---|
| Downward finger swipes failed in the Director's style: 5/10 with 7 events in the wrong direction (0.5 engine) | real, session 5 baseline |
| The Director's "down" is a fast curl of a pointing finger, followed by a slower extension back | real (stroke analysis) |
| **Root cause A - duplicate hand detections.** During fast movements MediaPipe reports the blurred hand twice for 1-4 frames, ~10 times per session, mostly mid-swipe. The engine read "two hands too close", cancelled the swipe and required a fresh settled hand; afterwards the finger extensions fired as swipes UP (phase lock) | real: 59 duplicate frames in the four recordings |
| **Root cause B - pose dependence.** In real use of 0.5 (13:35-13:43, finger style) a downward attempt failed ~20 times in 25 s, 12 of them "pose 0.0 of 0.5": the hand was not pointing at all | real use, unlabelled |
| Root cause C - preparation movement. To swipe down the hand is first raised; with a whole hand that raise is a valid UP and the intended DOWN becomes its return. Not separable from an intended up-swipe by motion alone (same trajectory, speed and position) | real, fist-down segments |
| Real use: 16 UP vs 5 DOWN confirmed; many near-diagonal (30-37 deg) and "hand already moving" rejections | real use, unlabelled - cannot give recall |

## 2. Fast movements: pipeline measurements

| Measure | Value |
|---|---|
| Webcam (MSMF and DirectShow) | **30 fps only**: a 60 fps request is accepted (DirectShow even reports 60) but 30.0 fps is delivered |
| Frame intervals in the recordings | median 32 ms; 12 % around 48 ms (delivery jitter of the capture backend, sd 5 ms, up to +-19 ms); real drops (~66 ms) < 1 % |
| Backend sample time (CAP_PROP_POS_MSEC) | exactly 33.33 ms; replaying with sample-grid timestamps gave **no improvement** (wrong-direction +2, false +2) -> not adopted |
| Duplicate detections | the dominant cause of missed fast swipes (root cause A) |
| Smoothing, minimum duration | not implicated (fast flicks peak 10-24 hand lengths/s against a 2.0 threshold) |
| Optical flow (CP 20.5) | **not implemented**: landmark tracking was not the limiting factor once duplicates were handled; no evidence of a gap it would bridge |
| Short-window / 2-3-observation detector (CP 20.3) | not needed: confirmed fast flicks were already decided within 3-6 frames; the missing ones were cancelled by duplicates, not undersampled |

## 3. Iterations (all development data unless marked)

Real = all four recordings; "hand shapes" = 44 prompted non-pointing swipes (fist and open
hand), "finger" = prompted pointing swipes; "ordinary" = false events in 249 s of negative
segments (rest, typing, face, natural movement, fist repositioning, opening/closing, lowering
the hand out of view, thumbs-up, stop pose).

| # | Candidate | Result | Decision |
|---|---|---|---|
| R0 | 0.5 engine, finger style (s5 right + s1/s2) | finger down 9/13, 3 wrong | baseline |
| R1 | ignore duplicate hands (< 0.3 s old, overlapping the control hand) | finger down **13/13, 0 wrong**; held-out left 5/5 (was 4/5 with 3 wrong) | **kept** |
| R2 | "faster stroke is the intended one" | session 2 returns are 1.07-2.4x faster than slow deliberate swipes | rejected (analysis) |
| R3 | pose-free whole-hand path (palm centre), settled 0.25 s, 0.5 | hand shapes 12/12 sweeps, fists 16/16 (right hand); ordinary 4 -> 15 | refined |
| R4 | + distance 0.6/0.7/0.8/1.0 | ordinary stays 12-15; sweeps fall to 0/6 at 0.8 | not the separator |
| R5 | + implausible jump (> 1 hand length/frame) and hand at the bottom edge | 15 -> 14 | kept (safety) |
| R6 | + strokes never start across a tracking gap; no decision on the frame after a gap | one recorded rest "swipe" (hand lost, re-found 2 hand lengths away) removed | **kept** |
| R7 | settle 0.4 s instead of 0.25 | wrong-direction 3 -> 1 at equal recall | **kept** |
| H1 | **held-out look** (left hand, R1-R7) | finger 5/5; **hand shapes 5/16** | generalizes for finger, not for whole hand |
| R8 | dynamic rearming: repeats need no new settle | no change (0) | rejected, removed |
| R9 | "ballistic" activation (1.3x faster than the previous opposite stroke) | +4 ordinary, no recall | rejected, removed |
| R10 | pointing hands stay on the fingertip path; half-heart / stop excluded; shape may change mid-stroke; downward hand strokes confirm when the hand stops in view | pointing behaviour identical to 0.5; lowering out of view not a swipe | **kept** |
| R11 | wider angle tolerance (34 deg) | no labelled recall gain, +1 ordinary | rejected |
| R12 | remember near-miss strokes for return suppression | baseline finger up 8/8 -> 4/8 (wind-ups suppressed the real swipe) | rejected, removed |
| R13 | personal whole-hand distance from calibration (cross-hand) | identical to default in both directions | no effect (distance is not the limit) |
| -- | learned classifier, template matching | data limitation unchanged (one person, ~100 intended strokes) | not repeated |

## 4. Selected engine (0.6.0b1 default "any hand shape") per category

| Category | Source | Correct | Wrong direction | Extra | Notes |
|---|---|---|---|---|---|
| Finger down | real, 4 sessions | 18/18 | 0 | 3 | extras: the left-hand performer made 8 swipes for 5 prompts |
| Finger up | real | 8/8 | 0 | 0 | |
| Reversal up then down | real | 4/4 up, 3/4 down | 0 | | |
| Fist up / down | real | 5/8 / 3/8 | 0 / 1 | | down: preparation raise (root cause C); swipes ending out of view |
| Fist left / right | real | 5/8 / 7/8 | 0 | | left-hand rhythmic swipes without a pause are not activated |
| Open hand left / right | real (sessions 1-2 sweeps) | 6/6 / 6/6 | 0 | 1 | were negatives in 0.5 (0/12 with the 0.5 palm experiment) |
| Ordinary activity | real, 249 s | 11 false events (2.6/min) | | | finger only: 6 (1.4/min) |
| Held-out (H1, before R8-R13) | real, left hand | finger 5/5; hand shapes 5/16 | 0 / 1 | | the only independent look |

**Targets (95 % recall and precision per direction, no recurring wrong-direction events, no
unintended action in 30 minutes) are not met for hand shapes and not demonstrable for any
category**: one person, development data, 4 minutes of ordinary activity.

## 5. Speed, frame rate and dropouts (synthetic degradations of the real recordings)

| Condition | Finger down | Finger up | Fist (all) | Open hand | Ordinary |
|---|---|---|---|---|---|
| as recorded (30 fps) | 18/18, 0 wrong | 8/8 | 20/32, 1 wrong | 12/12 | 11 |
| 20 fps | 18/18 | 7/8, 1 wrong | 18/32, 1 wrong | 9/12, 2 wrong | 13 |
| 15 fps | 15/18, 3 wrong | 4/8, 3 wrong | 21/32, 3 wrong | 12/12 | 10 |
| 10 % random frame loss | 18/18 | 6/8, 2 wrong | 20/32, 2 wrong | 10/12, 1 wrong | 11 |
| +-8 ms timestamp jitter | 18/18 | 8/8 | 20/32, 2 wrong | 12/12 | 10 |
| 15 % dropouts in fast frames | 18/18 | 8/8 | 17/32, 3 wrong | 11/12 | 11 |

Fast vs slow (real): the Director's downward curl flicks peak 9.8-17 hand lengths/s in 0.19-0.49 s
and are all recognized; the slowest recognized swipes last ~1.2 s (session 2). Below ~20 fps
missed upward flicks turn into wrong-direction events (their return is recognized); the app
already shows a low-frame-rate hint below 20 fps.

## 6. Cost

Recognition per frame over 56,682 replayed frames: finger 0.201 ms, any hand shape 0.208 ms
(p95 0.67 ms). End-to-end figures: see PROJECT_STATUS (stability session).

## 7. What would settle the remaining questions

A held-out recording (any session, both hands) made after this version, and the Director's
judgement of accidental swipes in real use with "any hand shape" vs "pointing finger only".
