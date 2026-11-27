# Gesture benchmark - Engineering Brief 007 (baseline protection)

Date: 2026-11-27. Version 0.7.0b1. Continues [GESTURE_BENCHMARK_006.md](GESTURE_BENCHMARK_006.md).

The Director approved the practical feel of 0.6.0b1. This brief protects that behaviour:
**the recognizer is unchanged in 0.7.0b1** (no gesture candidate passed the regression gate).
All recordings are development data from one person; nothing here is independent validation.

## 1. Frozen baseline (CP 26.1)

`docs/benchmarks/baselines/v0.6.0b1_*.json` (aggregate counts only) - the approved engine at
commit 195a214, default "any hand shape", on the four recordings:

| Condition | File | Highlights |
|---|---|---|
| as recorded (30 fps) | `v0.6.0b1_recorded.json` | finger down 18/18, up 8/8, 0 wrong; fist 20/32 (1 wrong); open hand 12/12; ordinary activity 11 in 249 s; confirmation median 0.258 s, p95 0.817 s |
| pointing finger only | `v0.6.0b1_recorded_finger_only.json` | ordinary activity 6 in 249 s |
| 15 fps (synthetic) | `v0.6.0b1_fps15.json` | finger up 4/8 (3 wrong), down 15/18 (3 wrong) |
| 20 fps (synthetic) | `v0.6.0b1_fps20.json` | finger up 7/8 (1 wrong) |
| 10 % frame loss (synthetic) | `v0.6.0b1_drop10.json` | finger up 6/8 (2 wrong) |

Defaults recorded with the baseline: style any hand shape, pointing distance 0.8, whole-hand
distance 0.5, minimum speed 2.0 hand lengths/s, settle 0.4 s, direction ratio 1.8 (29 deg),
duplicate-hand filter on (< 0.3 s), tracking-gap rules on; mappings up -> next Short, down ->
previous Short, right -> next tab, left -> previous tab, half-heart -> like, open palm -> pause.

## 2. Regression gate (CP 26.5)

`python scripts/benchmark_motion.py recordings/gestures_*.json --baseline
docs/benchmarks/baselines/v0.6.0b1_recorded.json` compares every row and exits 1 when a direction
loses correct swipes or gains wrong-direction, extra or ordinary-activity events; it also reports
the median stroke-to-confirmation time. The unchanged engine reports "no regression" against
each baseline file.

## 3. Candidates (all rejected by the gate)

| Candidate | Purpose | Result against the baseline | Decision |
|---|---|---|---|
| Low-frame-rate return memory: below 20 fps, remember a stroke that reached half the distance and turned back | CP 26.3: a missed upward flick lets its return trigger DOWN | 15 fps: wrong-direction events unchanged, reversal down -1; 20 fps / 10 % loss / 30 fps: no change | rejected: at 15 fps the fast flick often never forms a stroke at all (undersampled), so there is nothing to remember |
| Whole-hand minimum speed 3.0 | CP 26.2: fewer accidental whole-hand swipes | ordinary activity 11 -> 9, but fist up -3, open hand right -5; confirmation median 0.258 -> 0.303 s | rejected (the speed at early confirmation is lower than a swipe's full peak) |
| Whole-hand minimum speed 3.5 | same | ordinary 11 -> 9; fist and open-hand swipes -19 in total; median 0.4 s | rejected |

## 4. What remains (unchanged from 0.6.0b1)

* Accidental swipes in ordinary activity: 11 in 249 s (any hand shape), 6 (pointing finger
  only). The 30-minute negative-activity target cannot be measured with 4 minutes of recordings.
* Below ~20 fps upward finger flicks are undersampled; their returns can be read as DOWN. The
  app shows a low-frame-rate hint below 20 fps; the webcam here delivers 30 fps.
* Independent physical data: none (all four recordings were used for development).
