# Director validation - Brief 004 (beta)

About 20 minutes; the optional recording adds about 10. Nothing here needs code or threshold
changes. Write down what happens; if something fails, press **Copy diagnostics** right away
(step 8) - the file contains what is needed to analyse it.

## 1. Update (PowerShell)

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install --no-deps -e .
```

No new packages or models are needed.

## 2. Start

```powershell
scripts\run.ps1
```

On the first start a banner says **SCROLL DIRECTION UPDATED**: moving the finger up now shows
the next Short (your settings still had "down = next"; any mapping you changed yourself is
kept).

## 3. Reload the browser extension

In Edge open `edge://extensions` (Chrome: `chrome://extensions`), find **Interactive Scrolling
Bridge** and press **Reload**. It must show version **0.4.0**. The pairing stays.

## 4. Practice (3 minutes)

1. Press **Start camera**.
2. In the **Gesture recognition** panel press **Practice and calibrate... -> Start practice**.
3. Do each gesture the way that feels natural. After every try the window says
   "✓ Recognized" or *why not* (for example "movement too short (0.42 of 0.80 hand lengths)").
   Each gesture needs three recognitions; **Skip** moves on.
4. Note for each gesture: how many tries were needed, and any message you did not understand.

## 5. Quick Calibration (2 minutes, optional but recommended)

**Practice and calibrate... -> Start Quick Calibration**: three demonstrations of each gesture.
Read the summary ("What would change") and press **Use my profile**. If a gesture keeps failing,
press **Redo ...** for that gesture. **Restore standard recognition** undoes everything.
Then repeat step 4 once and compare.

## 6. YouTube Shorts (5 minutes)

1. In Edge open `https://www.youtube.com/shorts` (signed in, if you want to test liking).
2. In the app choose **Live control**.
3. Finger **up** three times -> three new Shorts. The video in the app shows the recognized
   gesture at once and then "✓ Next Short".
4. Finger **down** three times -> back three Shorts. At the first Short the app shows
   "✗ Previous Short: already at the first Short" immediately (no 3-second wait).
5. Quick repetitions: finger up twice within about a second -> two new Shorts.
6. **Half-heart** -> the Short is liked ("✓ Like Short"). Half-heart again on the same Short ->
   "already liked" (it never un-likes). Signed out -> "not signed in to YouTube".
7. **Open palm** -> pause; again -> play.
8. Esc (or the emergency hotkey) stops all control at once.

## 7. Browser tabs (3 minutes)

1. Open three tabs in the same window (Shorts, any other page, any other page).
2. Finger to **your right** -> next tab; to **your left** -> previous tab.
3. At the last tab: "already at the last tab"; at the first: "already at the first tab".
4. Click another application, then swipe: "the browser is not the active window" (nothing
   happens in the other application).
5. Swipe back to the Shorts tab and continue scrolling.

## 8. If something does not work

Press **Copy diagnostics** in the Gesture recognition panel. The report is on the clipboard and
saved as `%LOCALAPPDATA%\interactive_scrolling\diagnostics\diagnostics-<date>.json` (with
the Microsoft Store Python:
`%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\Local\interactive_scrolling\diagnostics\`).
It contains the recent recognition decisions with measured values and the browser results -
no images, page addresses, titles or the pairing code. Send that file.

## 9. Recordings that would answer the open questions (optional, ~10 minutes)

The recognizer has never seen your left/right swipes, your half-heart or your stop pose at a
normal distance. One guided recording per hand answers that (about 5 minutes each; only hand
landmark numbers are stored, in `recordings\`, which is never uploaded):

```powershell
.venv\Scripts\python.exe scripts\record_gestures.py --session 4 --hand right
.venv\Scripts\python.exe scripts\record_gestures.py --session 4 --hand left
```

Optional, for the false-trigger measurement (normal computer use, no gestures):

```powershell
.venv\Scripts\python.exe scripts\record_gestures.py --session negatives --minutes 15
```

Evaluation (or send the files):

```powershell
.venv\Scripts\python.exe scripts\evaluate_gestures.py recordings\gestures_s4_*.json
.venv\Scripts\python.exe scripts\simulate_calibration.py (Get-Item recordings\gestures_s4_right_*.json) --test (Get-Item recordings\gestures_s4_left_*.json)
```

## What to report back

| Item | Result |
|---|---|
| Practice: tries needed per gesture (up, down, right, left, heart, stop) | |
| Did calibration help? | |
| Shorts: next / previous / first-Short message / like / pause | |
| Tabs: right / left / edges / other application untouched | |
| Anything that triggered by accident | |
| Overall: does it feel natural and responsive? | |
