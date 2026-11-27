# Gesture and browser benchmark - Engineering Brief 004

Date: 2026-11-27. Code: version 0.4.0b1 (see the commit list in `PROJECT_STATUS.md`).

**Read this first.** All gesture numbers below come from the two existing landmark recordings
(`recordings/gestures_20261126_053533.json` = session 1, `..._054657.json` = session 2), made by
one person with one camera in one room, about 9 minutes in total. They were used to *find and
fix* problems, so they are **development results, not independent validation**. There is no
recording of left/right index swipes, of a real half-heart, or of a stop pose at a normal
distance. The Director's guided recording (`scripts/record_gestures.py --session 4`) is
the held-out test this report cannot replace.

Tools (all in `scripts/`, re-runnable):

| Script | Measures |
|---|---|
| `evaluate_gestures.py` | recall and false triggers per labeled segment; `--option`/`--v03` switch strategies, `--mirror` (simulated other hand), `--synthetic-horizontal` (rotated real swipes, labeled synthetic), `--any-pose` (horizontal proxy) |
| `evaluate_poses.py` | frame-level pose classification per segment |
| `simulate_calibration.py` | Quick Calibration on one session, scored on another |
| `experiment_classifier.py` | learned stroke classifier vs rules (Strategy D) |
| `experiment_filtering.py` | smoothing filters and frame-rate robustness |

## 1. The Director's real test (analytics database, 2026-11-27 06:50-07:00)

The dashboard values were reproduced from the local statistics database (read-only copy):

| Stage | Count |
|---|---|
| Gestures confirmed (Live control) | 15: swipe up 12, swipe down 2, half-heart 1 |
| Gestures confirmed (Gesture test mode) | 5: up 3, down 1, stop 1 |
| Actions dispatched | 14: previous Short 12, next Short 2 |
| Succeeded | 9 |
| Failed | 5 - all "previous Short: the active Short did not change", each after ~3.04 s |
| Rejected | 5 - 4 "previous action still running" (made during those 3 s waits), 1 half-heart: "no YouTube Shorts tab is active" |
| Left / right | 0 confirmed |

Findings, each confirmed by measurement:

1. **Direction mapping.** Up was mapped to *previous*. The Director swiped up 12 times; the
   Director's description is "finger up = next". Changed (ADR-029).
2. **First Short.** All 5 failures came before the first forward move. Live probe: at the first
   Short YouTube hides the previous button's host but does not disable it; the click does
   nothing. Previous now refused in 11 ms (ADR-028).
3. **Rejections during waits.** The 4 "still running" rejections were repeated swipes during the
   3 s failure waits; they disappear with (2).
4. **Like.** The single half-heart arrived while no Shorts tab was active (the Shorts session had
   ended 80 s before): a correct context rejection. Liking itself was never attempted in a valid
   context; the half-heart was confirmed only once in the whole session - recognition, not the
   browser, was the bottleneck.
5. **Recognition** (from the recordings, sections 2-3): downward finger flicks were rejected by the
   pose rule; horizontal movements were inverted by the arming rule; the stop pose is lost by the
   detector at arm's length.

The 64 % "execution success" was 9/14 dispatched actions; it never measured recognition.

## 2. Root causes in recognition

| # | Cause | Evidence |
|---|---|---|
| R1 | A downward fingertip flick curls the index finger; "pointing throughout" rejected it | session 1: hand reads as fist in 10-12 of ~12 frames of each downward stroke; 1/4 recognized, plus one wrong-direction up |
| R2 | A new hand had to be still 0.2 s; in continuous motion it armed at the end of a stroke and confirmed the return | frame trace of session 2 sweep (87.5-90.7 s); `--any-pose` sweeps: 0/12 correct, 17 opposite |
| R3 | 3D joint angles inflate on small hands; the open palm reads as "other" | open palm at 86 px: median flexion 104-131 degrees (extended <= 70); at 141 px 12-21 |
| R4 | The open palm at arm's length is lost by the detector | stop prompts: no hand in 111/151, 180/302 frames; one prompt never detected; visible ~0.5 s before loss |
| R5 | Palm length swings during wrist rotation | 27-184 px within one sweep; tracking lost in 49-78 of 360 frames of fast sweeps |

Hypotheses that the data did **not** support: a coordinate/mirroring bug (right sweeps measured
as right; the inversion was R2), the speed threshold being too strict (1.2-2.5 made no
difference), horizontal needing different thresholds (no index-swipe data; per-axis distance is
available through calibration).

## 3. Iteration history

Development data: sessions 1 + 2. Metrics: real swipes (16: finger-led 4 down + 4 up, hand 4 + 4),
stop (3); false triggers in all segments / in the 190 s of negative segments; horizontal proxy
(12 open-hand sweeps, pose ignored); semi-synthetic horizontal (8 rotated real pointing swipes).

| # | Change (strategy) | Real swipes | Stop | False (neg.) | Proxy | Synthetic | Decision |
|---|---|---|---|---|---|---|---|
| I0 | version 0.3 (= `V03_OPTIONS`, reproduces commit 88255ac exactly) | 13/16 | 0/3 | 1 (0) | 0/12, 17 false | 6/8, 0 false | baseline |
| P1 | image-space finger states (A) | 13/16 | 0/3 | 2 (2) | | | rejected: typing open-palm frames 0 -> 116 |
| P2 | image-space states only where 3D is uncertain (A) | 13/16 | 0/3 | 2 (2) | | | rejected: pointing frames in natural movement 25 -> 79 |
| A1 | arming on one rest (B) alone | 13/16 | 0/3 | 4 (1) | 6/12 | | kept, see I1 |
| A2 | pose rule: any pointing frame at start/end (A) alone | 13/16 | 0/3 | 6 (3) | | | refined in I2 |
| A3 | stable hand scale; dropout tolerance; window stillness (A, B) alone | 13/16 | 0/3 | 1-2 | | | neutral, kept (principled) |
| I1 | all of the above | 16/16 (+1 extra) | 0/3 | 9 (7) | 9/12 after onset fix | | false triggers too high |
| I2 | pointing before the stroke must be sustained | 16/16 | 0/3 | 4 (2) | 9/12 | 6/8, 4 false | kept |
| I3 | confirm at stroke end (B) | 16/16 | 0/3 | 2 (1) | 3/12 (9/12 with a 4.5 travel cap) | | rejected: +0.30 s median waiting |
| -- | end the return phase after any pause (B) | | | | | | rejected without building: natural pauses 0.2-0.37 s (max 1.4) |
| I4 | pending flick: curled finger must recover (B) | 15/16 | 0/3 | 2 (1) | 9/12 | 6/8, 2 false | kept |
| I5 | recovery also by moving back; window 0.8 s | **16/16** | 0/3 | **2 (1)** | 9/12 | 6/8, 2 false | **selected** |
| S1 | stop hold 0.5/0.6 s, holds during stabilization | 16/16 | 0/3 | 3 (2) | | | rejected |
| T1 | distance 0.5 / 0.6 / 0.7 / 1.0 | 12/16 / 12/16 / 16/16 / 12/16 | | 10 / 9 / 4 / 2 | | | 0.8 kept; basis for calibration |
| C1 | calibration raising the distance on large swipes (C) | cross-session 0/8 | | | | | rule changed |
| C2 | calibration lowers, raises only for wind-ups (C) | cross-session 8/8 and 8/8 | | 1 and 1 | | | kept |
| D1 | 3-nearest-neighbour stroke classifier (D) | 0/11 and 0/8 cross-session | | | | | rejected (ADR-026) |
| F1 | One Euro filter / 80 ms smoothing | 16/16 / 12/16 | | 2 / 5 | | | rejected (ADR-030) |

## 4. Selected recognizer - results per gesture

Wilson 95 % intervals are given where a rate is stated. "Precision" counts every confirmed swipe
of the replayed material, including those in negative segments.

| Gesture | Source | Attempts | Correct | Missed | Wrong direction | Duplicates | Recall (95 % CI) |
|---|---|---|---|---|---|---|---|
| Up | recorded (finger flick 4, hand 4) | 8 | 8 | 0 | 0 | 0 | 100 % (68-100 %) |
| Down | recorded (finger flick 4, hand 4) | 8 | 8 | 0 | 0 | 0 | 100 % (68-100 %) |
| Up + down | mirrored replay (simulated other hand) | 16 | 16 | 0 | 0 | 0 | 100 % (81-100 %) |
| Right | semi-synthetic (rotated real hand swipes) | 4 | 4 | 0 | 0 | 0 | not a recall claim |
| Left | semi-synthetic | 4 | 2 | 2 (suppressed as returns after a false down) | 0 | 0 | not a recall claim |
| Right / left | proxy: open-hand sweeps, pose ignored | 6 / 6 | 6 / 3 | 0 / 3 | 0 / 3 inverted | 0 | not a recall claim |
| Half-heart | synthetic hands only (both hands, three sizes) | - | - | - | - | 0 (held 4 s = 1 event) | not measured |
| Stop | recorded, arm's length | 3 | 0 | 3 (detection loss) | - | 0 | 0 % |

Vertical swipes: 16 correct events, 2 false events in the whole replay (one right swipe while the
hand was raised into position in a down segment; one right movement of a held pointing hand) -
precision of swipe events 16/18 = 89 %.

## 5. False positives

Negative segments: 190 s (rest, natural movement, face touching, typing, two hands, open hand
held, fist, pointing held, thumbs up, open-hand sweeps) plus the gesture segments themselves.

| Engine | False events in negative segments | False events in gesture segments |
|---|---|---|
| version 0.3 | 0 | 1 (wrong-direction up during down flicks) |
| selected | 1 (a held pointing hand moved right) | 1 (right while positioning the hand) |

Additional risk found and documented: lowering a pointing hand out of view can be read as a
downward swipe (one recorded case, removed only by stroke-end confirmation, which was rejected).
One event in 190 s does not establish a low rate: the Poisson 95 % upper bound for one observed
event is about 4.7 events per 190 s (about 90 per hour). The 30-minute ordinary-use target needs
`record_gestures.py --session negatives --minutes 30`.

No false half-heart or stop event occurred in any segment; image-level half-heart frames: 5 of
5,579 hand frames (same before and after the tolerant rule).

## 6. Latency (recognition)

| Measure | Value |
|---|---|
| Recognition processing per frame (27,135 replayed frames) | version 0.3 0.112 ms mean (p95 0.37); selected 0.156 ms (p95 0.52) |
| Stroke start to confirmation, pointing swipes | median 0.25-0.33 s (the time of the movement itself) |
| Recognizer waiting after criteria met, pointing swipes | 0 s (early confirmation) |
| Recognizer waiting, finger flicks | 0.30-0.56 s (finger recovery, by design) |
| Half-heart / stop hold | 0.5 s / 0.8 s |

## 7. Smoothing and frame rate

| Filter | Jitter of a held hand (hand lengths, median of 8) | Lag at 0.5 hand lengths | Swipes | False |
|---|---|---|---|---|
| none | 0.129 | 0 ms | 16/16 | 2 |
| moving average 20 ms | 0.119 | 0 ms | 16/16 | 2 |
| **moving average 40 ms (kept)** | 0.113 | 0 ms | 16/16 | 2 |
| moving average 80 ms | 0.105 | 33 ms | 12/16 | 5 |
| One Euro | 0.113 | 0 ms | 16/16 | 2 |

(Lag is measured at frame resolution, 33 ms.) Replays: every 2nd frame (15 fps) - hand swipes
8/8, finger flicks fail (a flick lasts ~2 frames; an up flick measured 0.53 instead of 0.82 hand
lengths); every 3rd frame (10 fps) 10/19; 10 % of frames dropped at random 15/19, 2 false. The app
now warns below 20 fps.

## 8. Browser execution

| Test | Result |
|---|---|
| Fixture (real extension, headless Edge, 16 tests incl. rapid navigation, first Short in both markup variants, like idempotency, context rejection, tabs) | all pass, repeated 4x without failure |
| Live site, signed out, through the dispatcher | first Short: previous refused in 11 ms; 8/8 next, 4/4 previous back to back |
| Live site, signed in (like) | not tested - no account actions without the Director |

Eligible navigation success: fixture 100 % of eligible actions in the suite; live 12/12. These are
small samples. Live timings: "next" ~0.25 s on its own and ~1.0 s when made right after another
navigation (it waits for the new Short to load), "previous" 0.2-0.6 s. The video shows the
recognized gesture immediately and the confirmed browser result when it arrives.

## 9. Required data

The remaining recognition questions can only be answered with recordings of the Director
(about 5 minutes per hand): `python scripts\record_gestures.py --session 4 --hand right`, then
`--hand left`; optionally `--session negatives --minutes 30`. Then
`python scripts\evaluate_gestures.py recordings\gestures_s4_*.json` (held-out evaluation) and
`python scripts\simulate_calibration.py recordings\gestures_s4_right_*.json --test recordings\gestures_s4_left_*.json`.
