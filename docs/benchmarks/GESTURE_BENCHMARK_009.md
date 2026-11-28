# Gesture benchmark - Engineering Brief 009 (Motion Engine 2.0 experiments)

All numbers come from replaying the **development recordings** (four sessions, one person,
`recordings/`, local only). None of them is independent data: every recording has been
inspected in earlier briefs. Nothing here establishes the 95 % recall/precision target of
CP 52.3; that needs new, held-out recordings (procedure in BRIEF_009_VALIDATION.md).

Tools: `scripts/gesture_gate.ps1` / `scripts/gate_candidate.ps1` (five frozen 0.6.0b1
configurations: recorded, 20 fps, 15 fps, 10 % frame loss, pointing finger only),
`scripts/analyze_decision_delay.py` (stroke duration and decision delay per detector),
`scripts/benchmark_modes.py` (full application replay, see PERFORMANCE_009.md).

## 1. Where recognition time goes (CP 46.1, 48.5)

| Detector, direction | Events | Stroke (median) | Decision delay after the stroke reached its distance (median / p90) |
|---|---|---|---|
| finger up | 15 | 255 ms | 0 / 0 ms |
| finger down | 29 | 241 ms | **255 / 542 ms** |
| finger right | 3 | 433 ms | 0 / 0 ms |
| whole hand up / left / right | 9 / 16 / 16 | 184-243 ms | 0 / 0 ms |
| whole hand down | 5 | 672 ms | **432 / 497 ms** |

Only downward swipes (previous Short) waited. Two guards cause it: a downward stroke with the
hand in the bottom 15 % of the picture, and every whole-hand downward stroke, are confirmed only
once the hand **stops** inside the view, so a hand lowered out of the picture is not a swipe
(Brief 005 recorded such a false swipe). The finger-down p90 (542 ms) comes from curled-finger
flicks, which wait for the finger to re-extend.

## 2. Candidates (structured experiment log)

| # | Candidate | Gate (5 configurations) | Effect | Decision |
|---|---|---|---|---|
| A | flick counts as recovered when the fingertip moves back at 1-3 hand lengths/s | no regression | **no change** in any count or delay (the waiting events were not flicks) | rejected (no effect) |
| B | downward stroke counts as stopped below 30-60 % of its peak speed | no regression at 30 fps; 0.5: finger down 255 -> 192 ms, hand down 432 -> 367 ms | **regression at 15 fps** (one reversal lost, one duplicate) | refined -> D |
| C | bottom zone 0.85 -> 0.90 / 0.95 / 0.99 | 0.90 clean on the recordings (confirmation median 258 -> 241 ms); 0.95+: +1 false event | 0.90 **re-opened the Brief 005 false swipe** (existing regression test `test_gesture_hand_lowered_out_of_view`) | rejected |
| D | B, but only while the control hand's measured frame rate is >= 22 fps (median of recent intervals) | **no regression in all five** | finger down 255 -> **192 ms**, hand down 432 -> **367 ms**; 15/20 fps unchanged | **adopted** |
| E | engine cooldown 0.5 -> 0.35 / 0.25 s | no regression | no change at all: the recordings contain no rapid same-direction repeats | not adopted (no evidence) |
| F | whole-hand distance 0.5 -> 0.6 / 0.7 hand lengths | regression (open-hand left/right) | false events unchanged | rejected |
| G | whole-hand settle time 0.4 -> 0.6 / 0.8 s | regression (fist and open-hand rows) | false events 11 -> 10 / 9 | rejected (too many real swipes lost) |
| H | periodic (driver) frame times instead of arrival times | regression (+2 false events, duplicates) on a periodic approximation of the recordings | - | not adopted; driver times are now recorded for a proper test (`Frame.sample_ns`) |
| I | display smoothing beta 0.2 -> 0.5 (visual only) | n/a (recognition untouched) | drawn fingertip lag 3.5 -> 1.6 ms median, 9.1 -> 4.5 ms p90; still-hand shimmer 0.82 -> 0.83 of raw | adopted |

## 3. Result with the adopted engine (D) against the frozen baselines

| Configuration | Result | Ordinary-activity events | Confirmation median |
|---|---|---|---|
| recorded | no regression | 11 -> 11 (249 s) | 0.258 -> 0.258 s |
| 20 fps | no regression | 13 -> 13 | 0.273 -> 0.273 s |
| 15 fps | no regression | 10 -> 10 | 0.274 -> 0.274 s |
| 10 % frame loss | no regression | 11 -> 11 | 0.273 -> 0.273 s |
| pointing finger only | no regression | 6 -> 6 | - |

(The overall confirmation median is dominated by upward and horizontal swipes, which were
already immediate; the change is in the downward decision delay, section 1.)

Synthetic regression tests (`tests/regression/test_gesture_down_near_bottom_waits.py`): a low
downward swipe is decided after 67 ms at 30 fps (200 ms with the previous rule) and keeps the
200 ms wait at 15 fps; a hand lowered out of view is still never a swipe.

## 4. False positives (CP 46.6)

The 11 false events in 249 s of ordinary activity (any hand shape) are spread over many
behaviours: fist repositioning (right, stop), lowering out of view (down), natural movement
(down, up), opening/closing the hand (stop), resting (left), pointing and thumbs-up poses
(right, left, right). Pointing finger only: 6. The two meaningful candidates (F, G) removed at
most 2 of them while losing many real whole-hand swipes. With this amount of negative data
(4 minutes, one person) no change can be justified; a lightweight classifier was not trained
because training and evaluation would overlap on the same few minutes. **Not improved.**

## 5. Fast, repeated and degraded input

* Fast gestures: the Brief 006 duplicate-hand filter is unchanged and covered by the gate
  (drop10 and recorded rows); motion blur and dropouts are not fabricated.
* Repeated gestures: no recordings of rapid repeats exist; cooldown changes had no measurable
  effect (E). The engine waits 0.5 s per direction, the dispatcher 0.4 s globally and for the
  browser's confirmation of the previous action.
* Degraded frame rates: 15 and 20 fps unchanged by design (D applies only at >= 22 fps). The
  wrong-direction counts of the 15 fps baseline (finger up 3, finger down 3) remain.
* Higher frame rates: the development camera cannot deliver more than 30 fps (CAMERA.md), so
  60 fps recognition is untested on real data; timing uses actual frame timestamps throughout
  (no fixed frame interval in the motion code).
