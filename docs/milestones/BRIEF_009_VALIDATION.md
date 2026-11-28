# Director validation - Brief 009 (beta 0.9.0b1)

About 25 minutes, plus optional recordings (another 25 minutes) that would give the first
independent evidence for the recognition targets. The UI is unchanged.

## 1. Update and start (PowerShell)

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install --no-deps -e .
scripts\run.ps1
```

The browser extension did not change (no reload needed).

## 2. Broadcast Mode responsiveness (10 minutes) - the main question

1. Open YouTube Shorts, choose **Live**, press **Broadcast**.
2. Scroll 20 Shorts forward and back the way you did when it felt worse. In particular **swipe
   down** (previous Short) with your hand low in the picture: it should now fire noticeably
   sooner (about 60-200 ms less wait).
3. Note anything that still feels late: the gesture itself not recognized, recognized but the
   Short changes late, or the overlay feedback late.
4. Repeat the same 20 swipes in **Normal** Mode. Does Broadcast still feel worse? If yes,
   *how*: missed gestures, late reaction, or something you see?

## 3. Eye and gaze overlay (5 minutes)

1. **More -> Show eye and gaze overlay (estimate)** (the face model starts).
2. Look left, right, up, down; turn your head; blink. The arrow should follow roughly and
   disappear while blinking or when you turn far away. It never controls anything.
3. Optional (3 minutes, full screen, needs the camera free - close the app first):
   ```powershell
   .venv\Scripts\python.exe scripts\evaluate_gaze_calibration.py --json reports\gaze_calibration.json
   ```
   Look at each dot until it moves. Send back the printed numbers (no images are stored).

## 4. Quick checks (5 minutes)

* Clown, transparent background, Doomscroll Together and the live preview behave as in 0.8.0b1.
* Broadcast overlay: the skeleton should look a little more direct during fast moves.

## 5. Optional recordings for independent evaluation (about 25 minutes)

Recordings stay on your computer (`recordings/`, never committed). I will treat them as
**held-out**: scored once, never inspected per event while tuning.

Close the app first (the recorder needs the camera), then:

```powershell
.venv\Scripts\python.exe scripts\record_gestures.py --session 5 --hand right
.venv\Scripts\python.exe scripts\record_gestures.py --session 5 --hand left
.venv\Scripts\python.exe scripts\record_gestures.py --session repeats
.venv\Scripts\python.exe scripts\record_gestures.py --session negatives --minutes 10
```

1. **Directional set** (session 5, each hand): follow the prompts in your natural style, also
   with the hand low in the picture.
2. **Rapid repeats** (new session `repeats`, about 3 minutes): 3 quick swipes in a row per
   direction without lowering the hand, and up-then-down, three rounds.
3. **Ordinary activity** (`negatives`, 10 min, longer is better): typing, touching your face and hair,
   reaching for a cup, talking with your hands, resting, lowering the hand out of view.

These recordings now also contain the camera driver's frame times, so the periodic-timing
candidate can be evaluated properly.

## What to report back

| Item | Result |
|---|---|
| Broadcast vs Normal: still different? How? | |
| Downward swipes faster? | |
| Eye overlay sensible? Calibration numbers (optional) | |
| Anything worse than 0.8.0b1? | |
| Recordings made (optional) | |
