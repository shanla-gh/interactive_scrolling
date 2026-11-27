# Gesture benchmark - Engineering Brief 005 (motion-first)

Date: 2026-11-27. Version 0.5.0b1. Continues [GESTURE_BENCHMARK_004.md](GESTURE_BENCHMARK_004.md).

**Read this first.** The only real gesture recordings are still the two development sessions
(one person, ~9 minutes). The new fist control has **no real recording**; its recall numbers
come from a semi-synthetic set (real palm motion of recorded hand swipes and sweeps, fingers
re-posed as a fist). Nothing here is independent validation. Evidence classes are marked:
**real** (recorded), **real use** (the Director's statistics), **semi-synthetic**, **synthetic**.

New tools: `scripts/analyze_motion_references.py` (which landmark carries a stroke),
`scripts/compare_strategies.py` (all strategies on all sets), `evaluate_gestures.py
--synthetic-fist`.

## 1. What the Director's test after 0.4 shows (real use)

Statistics database, 2026-11-27 09:48-09:56 (read-only copy):

| Finding | Evidence |
|---|---|
| Downward swipes **were** recognized in Live control | 13 downward swipes confirmed in about one minute |
| ...but 7 of them did nothing visible | refused with "already at the first Short": each time the feed had been scrolled back past its start (4 up, then 4 down succeeded and the 5th was refused; 2 up, 2 down, then 3 refused) |
| Quick Calibration made vertical swipes much harder | the profile stored 1.34 hand lengths and 2.5 hand lengths/s (standard 0.8 and 2.0); replaying the recorded finger flicks with these values: **8/8 -> 0/8** |
| Missed attempts cannot be counted | only confirmed gestures were stored |
| Stop and half-heart work in real use | 4 stop poses (2 live pause/resume toggles), 2 half-hearts in Practice; attempt counts unknown |

## 2. Root causes of the remaining downward problem

| # | Cause | Status |
|---|---|---|
| D1 | **Calibration defect**: a return that started after a short hold at the top and ended just before the next demonstration was classified as a wind-up as large as the swipe; the distance was set to 0.9 x the smallest demonstration and the speed raised | confirmed, fixed, Director's profile repaired by migration |
| D2 | **Feed boundary looked like a recognition failure** | confirmed from the log; the banner now says the gesture was recognized |
| D3 | **A downward finger flick is physically the return of an upward flick**: the index curls, the palm stays | measured (table below); not solvable per stroke - needs context or another motion reference |
| D4 | Missed attempts were invisible | fixed: rejections are now stored |

Motion references along the stroke direction (real; `analyze_motion_references.py`, hand lengths):

| Stroke | n | Fingertip | Fingertip relative to palm | Palm centre | Wrist | Index flexion change |
|---|---|---|---|---|---|---|
| Intended down | 9 | 2.10 (1.11-4.25) | 1.03 | 2.17 (flicks ~0.05) | 2.15 | **+113 deg** |
| Return after an up stroke | 8 | 0.81 (0.60-4.09) | 0.68 | 0.06 | 0.02 | **+137 deg** |
| Intended up | 10 | 1.86 | 0.50 | 1.12 | 0.55 | -44 deg |
| Return after a down stroke | 9 | 1.59 | 1.07 | 1.28 | 1.04 | -114 deg |

A curl-flick down (palm ~0, finger curling) and the curl back after an upward flick have the same
signature; this is why finger-only "down" depends on timing (return phase) and on the finger
recovering, and why a palm-centre reference (fist) is a natural alternative.

## 3. Strategies compared

All on the same material. Real = 16 recorded vertical finger swipes + 190 s of negatives;
fist = semi-synthetic fist swipes (4 up, 4 down, 6 right, 6 left).

| # | Strategy | Real swipes | False (in negatives) | Fist (semi-syn.) | Decision |
|---|---|---|---|---|---|
| B0 | pose-first (0.3) | 13/16 | 1 (0) | 0/20 | baseline |
| B1 | improved finger (0.4) | 16/16 | 2 (1) | 0/20 | baseline of this brief |
| M1 | + fist detector (palm centre, held fist 0.25 s), hybrid, 0.25 / 0.40 / 0.50 / 0.80 | 16/16 | 10 / 9 / 8 / 6 (6 / 6 / 5 / 4) | 20 / 20 / 20 / 16 of 20 | too many false events |
| M2 | + fist must be still 0.25 s before moving (activation cue) | 16/16 | 4 (3) | 17/20, 5 opposite | kept, see M3 |
| M3 | + fist strokes without the cue are followed and remembered | 16/16 | 4 (3) | 13/20, 0 opposite | kept |
| M3b | bug fix: a fist swipe's own return was remembered as a stroke | 16/16 | 4 (3) | **18/20**, 1 extra | **kept** |
| M4 | open-palm swipes (experimental) on the **real** open-hand sweeps | - | +2 (raising an open hand) | real sweeps **0/12, 7 opposite** | rejected (off) |
| M5 | finger: confirm at once when the palm moves with the fingertip (>= 40 %) | 16/16 | 3 (2): the hand lowered out of view came back | - | kept with M6 |
| M6 | + downward strokes in the bottom 15 % of the picture wait until the hand stops in view | 16/16 | **2 (1)** | - | **kept** |
| M7 | smaller distance for down only: 0.4 / 0.5 / 0.6 / 0.7 | upward flicks 2/4, 0/4, 0/4, 4/4 | 6, 8, 6, 2 | - | rejected (the curl back after an up flick becomes a down) |
| M8 | smaller shared distance 0.4 / 0.6 (0.15 and 0.25 below the allowed range) | upward flicks 2/4, 0/4 | 7, 9 | - | rejected |
| C1 | per-direction calibration with returns as floor | cross-session **0/8** (whole-hand returns raised the distance) | | | corrected |
| C2 | per-direction calibration, wind-ups of both directions as floor | cross-session **8/8 both ways** (flicks: up 0.61, down 0.79) | 1 each | | **kept** |
| -- | learned classifier | not repeated: the data limitation of Brief 004 (19 intended strokes) is unchanged | | | |

The remaining 2 fist false events in hybrid mode both happen while thumbs-ups are shown and
lowered (a closed hand with the thumb out, moved sideways); none in rest, typing, face touching,
natural movement or two-hand segments.

## 4. Selected architecture and default

* **Finger control remains the default** (16/16 real, 2 false events in the replay, 1 in negatives).
* **Fist control** (fist only or finger + fist) is available and marked experimental: 18/20 on
  semi-synthetic fists, but no real fist recording exists.
* Open-palm swipes stay off (rejected on real data).

## 5. Per-direction results

| Gesture | Source | Attempts | Correct | Missed | Wrong direction | Duplicates |
|---|---|---|---|---|---|---|
| Finger up | real | 8 | 8 | 0 | 0 | 0 |
| Finger down | real | 8 | 8 | 0 | 0 | 0 |
| Finger up + down | real, mirrored (simulated other hand) | 16 | 16 | 0 | 0 | 0 |
| Finger right / left | semi-synthetic (rotated) | 4 / 4 | 4 / 2 | 0 / 2 | 0 | 0 |
| Fist up / down | semi-synthetic | 4 / 4 | 3 / 4 | 1 / 0 | 0 | 0 |
| Fist right / left | semi-synthetic | 6 / 6 | 6 / 5 | 0 / 1 | 0 | 1 extra left (session 2 had 4 events for 3 prompted sweeps; the performer may have made a fourth) |
| Return scenarios | synthetic (up-return-up, down-return-down, reversals after a pause, repeats every 0.9 s, slow) | 9 scenarios | all as intended | | 0 | 0 |
| Half-heart | real use: 2 confirmed in Practice; no labeled recording | | | | | |
| Stop | real use: 4 confirmed (2 live toggles); recordings at arm's length 0/3 | | | | | |

## 6. Latency and cost

| Measure | Value |
|---|---|
| Recognition per frame (27,135 replayed frames) | finger 0.144 ms (p95 0.35), hybrid 0.149 ms (0.4: 0.156) |
| Stroke start to confirmation, pointing swipes | median 0.30 s (the movement itself) |
| Waiting after the criteria are met | 0 s for pointing and hand swipes; finger curl flicks wait for the recovery (p95 0.56 s); near the bottom edge until the hand stops |

## 7. What would settle the open questions

`python scripts\record_gestures.py --session 5 --hand right` (about 3 minutes; repeat with
`--hand left`), then `python scripts\evaluate_gestures.py recordings\gestures_s5_*.json --set
control_style=hybrid`. It records natural downward finger swipes, fist swipes in four
directions and the fist negatives; the results decide whether fist (or hybrid) control can
become the default.
