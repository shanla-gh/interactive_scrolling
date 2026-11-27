# Director validation - Brief 005 (beta 0.5.0b1)

About 20 minutes; the optional recording about 6 more. The goal: compare finger and fist
swipes, especially **downward**, and tell us which feels natural.

## 1. Update and start (PowerShell)

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install --no-deps -e .
scripts\run.ps1
```

On the first start a banner says **CALIBRATION RESET - PLEASE RECALIBRATE**: your 0.4
calibration had made vertical swipes much harder (1.34 instead of 0.8 hand lengths); distance
and speed are back to the standard values, your half-heart shape is kept. The browser extension
did not change (0.4.0); no reload needed.

## 2. Downward finger swipes (5 minutes)

Press **Start camera**, then **Gesture recognition -> Practice and calibrate... -> Swipe method:
Finger swipes -> Start practice**.

1. Move your finger **down** the way that feels natural, three times. The video shows an arrow
   from where the movement started with "FINGER DOWN 0.52/0.80" (measured travel / needed).
2. Try both ways and note which is recognized more easily:
   * the whole hand or the wrist moves down with the finger pointing (recognized at once);
   * only the finger curls down (recognized when the finger straightens again).
3. If something is not recognized, read *Why not recognized* in the panel.

## 3. Fist swipes (5 minutes)

**Practice and calibrate... -> Swipe method: Fist swipes (experimental) -> Start practice**:
close the hand, hold it still briefly, then move it **up / down / to your right / to your left**,
three times each. Then try holding a fist still and opening and closing the hand: nothing may
happen.

## 4. Quick Calibration (optional, 2 minutes per method)

Same window, **Start Quick Calibration** with the method you prefer. Read "What would change"
(each direction gets its own value) and press **Use my profile**. **Redo down** repeats only the
downward swipe.

## 5. Choose and use (5 minutes)

**Gesture settings -> Swipe with**: *Index finger*, *Finger or fist* or *Fist only*. Then on
`https://www.youtube.com/shorts` in **Live control**:

1. Up three times -> next Shorts; down three times -> back.
2. Keep going down: at the first Short the banner says *already at the first Short (gesture
   recognized; nothing before this Short)* - that is not a recognition failure.
3. Quick repetition (up, up) and up-then-down after a short pause.
4. Half-heart (like) and open palm (pause / play).
5. Tabs: right / left in a window with three tabs.
6. Lower your hand out of the picture: nothing may happen.

## 6. If something does not work

Press **Copy diagnostics**. The file now also contains the rejections stored in the last seven
days (gesture, reason, measured and required value - no images, no page addresses), so missed
attempts can be analysed afterwards even if you press it later.

## 7. Short recording that would settle the open questions (optional, ~3 minutes per hand)

```powershell
.venv\Scripts\python.exe scripts\record_gestures.py --session 5 --hand right
.venv\Scripts\python.exe scripts\record_gestures.py --session 5 --hand left
.venv\Scripts\python.exe scripts\evaluate_gestures.py recordings\gestures_s5_*.json --set control_style=hybrid
```

It records natural downward finger swipes, fist calibration and fist swipes in four directions,
and the fist negatives (still fist, opening and closing, repositioning, lowering the hand out of
view). Only hand-landmark numbers are stored, in `recordings\`, which is never uploaded.

## What to report back

| Item | Result |
|---|---|
| Downward finger swipe: easy / sometimes / hard? Which way (hand, wrist, finger curl)? | |
| Fist swipes: up / down / right / left easy? | |
| Preferred style: finger, fist or both? | |
| Anything that triggered by accident (especially with fists)? | |
| Shorts, like, pause, tabs | |
