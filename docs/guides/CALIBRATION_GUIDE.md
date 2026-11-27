# Quick Calibration guide

Quick Calibration adapts the gesture recognition to the size and speed of *your* movements.
It is optional: the standard settings work for many people.

## Why calibrate

The swipe distance that works depends on your own movements. Before an upward finger flick,
most people first curl the finger slightly (a small "wind-up" downwards). If the required
distance is smaller than that wind-up, the wind-up is taken as a downward swipe; if it is
larger than your flick, the flick is missed. Calibration measures both and chooses a distance
between them.

## How it works (about two minutes)

1. Start the camera, then open **Gesture recognition -> Practice and calibrate... -> Start
   Quick Calibration**. Browser control is paused while the window is open.
2. For each gesture the window shows a drawing and one sentence. Do the gesture **three times**
   the way you would normally do it (swipes), or show and hold the pose (half-heart, open palm).
3. After each demonstration it says "Captured n of 3". If a demonstration cannot be used it
   says why, for example:
   * "Your hand is far from the camera: move it a little closer."
   * "That went to your right - please move to your left."
   * "Movement too short: move a little further."
   * "Hold the heart shape: thumb pointing down below the curved index finger, with a gap."
   Press **Repeat** to redo that gesture or **Skip** to keep the standard for it.
4. The summary lists what would change, e.g. "Vertical swipes: distance 0.77 hand lengths
   (your swipes 0.85-1.18)". Nothing changes until you press **Use my profile**.
5. **Redo up / down / ... / stop** recalibrates a single gesture. **Restore standard
   recognition** goes back to the Balanced preset (your gesture-to-action mapping and hand
   choice are kept).

## What is changed, and the limits

* Swipe distance for up/down and for left/right separately, minimum swipe speed, and the
  allowed swipe duration. The distance is lowered for small movements and raised only as far
  as your own wind-ups require - so calibrating with large swipes does not make later small ones
  fail. It never goes below 0.5 or above 1.4 hand lengths.
* Your own half-heart shape (measured angles and distances) is added: poses close to it are
  accepted in addition to the standard shape. Essentials stay required: a gap between thumb and
  fingertip (not a pinch), the thumb below the fingertip, a curved index finger.
* The open palm may tilt more if yours is held at an angle (up to 70 degrees).
* Only these numbers are stored, in your settings file. No video, images or hand recordings
  are kept (unless you tick "save the hand-landmark numbers" for analysis).
* One profile applies to both hands. It is recorded which hand was used; separate left/right
  profiles were not added because no recording yet shows that they would help.
* Recalibrate if you change how you sit, the camera or your gesture style.

## Evidence

Simulated on the two existing recordings: calibrating on one session and testing on the other
recognized 8 of 8 swipes in both directions with one false swipe each - the same false-swipe
count as the standard settings. This is one person and a small sample; your own calibration
and the Director validation are what count.
