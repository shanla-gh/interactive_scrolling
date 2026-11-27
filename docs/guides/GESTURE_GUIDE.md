# Gesture guide

How to control YouTube Shorts and browser tabs with your hand. No technical knowledge needed.

## The six gestures

| You do | What happens (default) |
|---|---|
| Move your pointing finger **up** | Next Short |
| Move your pointing finger **down** | Previous Short |
| Move your pointing finger to **your right** | Next browser tab |
| Move your pointing finger to **your left** | Previous browser tab |
| **Half-heart** with one hand, held briefly | Like the Short |
| **Open palm** (stop), held briefly | Pause / play |

"Up" moves the feed like a touchscreen: your finger goes up, the next video comes up. You can
change any of these in **Gesture settings** (each row reads "Move finger up -> Next Short").

## How to make the movements

**Swipes.** Point with your index finger (the other fingers loosely folded) and move it one
short, quick stroke in the direction - a flick of the finger, a turn of the wrist or a small
movement of the hand all work. Then let the hand come back; the movement back is ignored.

* The fastest response: keep the finger pointing and move the hand or wrist. The swipe is
  recognized while you are still moving.
* A finger flick (the finger bends down and straightens again) also works. It is recognized
  when the finger straightens again, a fraction of a second later - otherwise just relaxing
  your finger would count as "down".
* Move straight: diagonal movements are ignored on purpose.
* To go back the other way (for example next, then previous), let your hand come back to where
  it started and pause for a moment before the opposite swipe.

**Half-heart.** One half of the heart you would make with two hands: hand upright, index
finger (or all fingers) curved over with the tip pointing down, thumb pointing down below it,
a gap between thumb and fingertip. Hold it still for half a second. Holding it longer does not
like twice; lower the hand before the next like.

**Open palm (stop).** Open hand, fingers up, palm towards the camera, held still for about
a second. Do it at a comfortable distance - an open hand far away from the camera is often
lost by the camera.

## What the screen tells you

The video shows a short state line and banners:

| You see | Meaning |
|---|---|
| READY / POINTING - READY | A hand is tracked; a swipe can start |
| MOVEMENT DETECTED: SWIPE UP | A swipe is in progress (the bar shows how far) |
| HALF HEART DETECTED - HOLD | Keep holding the pose |
| SWIPE UP (green banner) | Gesture recognized |
| ✓ Next Short / ✗ Next Short: reason | The browser result, confirmed from the page |
| Hand far from the camera ... | Move your hand closer |
| Low camera frame rate ... | More light helps; use hand movements rather than finger flicks |

The **Gesture recognition** panel shows *Why not recognized* in plain words, for example
"Finger up: movement too short (0.42 of 0.80 hand lengths). Move a little further."

## Practice and calibration

Open **Practice and calibrate...** in the Gesture recognition panel:

* **Practice** walks through all six gestures and tells you after every try whether it worked
  and, if not, why. Nothing is sent to the browser while this window is open.
* **Quick Calibration** (about two minutes) measures three demonstrations of each gesture and
  adapts the recognition to your movements. See [CALIBRATION_GUIDE.md](CALIBRATION_GUIDE.md).

## When something does not work

1. Open Practice and repeat the gesture: the window explains what was measured.
2. Press **Copy diagnostics** (Gesture recognition panel). The report - recent recognition
   decisions and browser results, no images, no page addresses - is copied to the clipboard
   and saved in `%LOCALAPPDATA%\interactive_scrolling\diagnostics\`. Send that file.
3. Browser messages: "already at the first Short" means there is no previous Short; "no YouTube
   Shorts tab is active" means the browser shows another page; "the browser is not the active
   window" means tab switching works only while the browser is in front.

## What is verified (beta)

Measured on recordings of one person: upward and downward swipes 16/16 including finger flicks,
two false swipes in the recorded material. **Not yet verified on real recordings:** left/right
swipes, the half-heart and the stop pose at a normal distance - see
`docs/benchmarks/GESTURE_BENCHMARK_004.md`.
