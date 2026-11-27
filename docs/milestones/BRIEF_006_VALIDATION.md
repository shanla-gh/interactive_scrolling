# Director validation - Brief 006 (beta 0.6.0b1)

About 15 minutes. The question: do swipes feel natural with whatever hand shape you use, and
do accidental swipes stay acceptable?

## 1. Update and start (PowerShell)

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install --no-deps -e .
scripts\run.ps1
```

A banner says **SWIPES NOW WORK WITH ANY HAND SHAPE** (your setting moved from "finger" to
"any hand shape"). The browser extension did not change; no reload needed.

## 2. Downward swipes (5 minutes, the main question)

**Practice and calibrate... -> Start practice** (Practice now accepts any hand shape). Swipe
**down** the way you naturally would, several times each:

1. a fast finger curl (as in your recordings - these were cancelled before by a tracking glitch);
2. the whole hand or the wrist moving down, pointing;
3. a fist, an open or a relaxed hand: **hold it still for a moment first**, then move down.

The video draws the measured path and "HAND DOWN 0.42/0.50" (or FINGER). Note which ways feel
reliable.

## 3. All four directions, fast and slow (3 minutes)

Up, down, left, right - quick and slow, with different hand shapes. Then: hold a fist still;
open and close the hand; lower the hand out of the picture - nothing may happen.

## 4. Real use (5 minutes)

On `https://www.youtube.com/shorts` in **Live control**: scroll forward and back as you like,
like a Short (half-heart), pause (open palm). Then use your hands normally for a minute (mouse,
face, talking) with Live control still on, and count anything that happened by itself.

If that is too much: **Gesture settings -> Swipe with -> Pointing finger only** (fewer accidental
swipes, the 0.5 behaviour) and repeat step 4.

## 5. If something does not work

Press **Copy diagnostics** right away. It now also contains the measured frame timing and how
often a duplicate hand was ignored.

## 6. Optional recording (about 3 minutes per hand)

```powershell
.venv\Scripts\python.exe scripts\record_gestures.py --session 5 --hand right
.venv\Scripts\python.exe scripts\record_gestures.py --session 5 --hand left
```

A new recording is the only independent test data: the existing ones were all used for
development.

## What to report back

| Item | Result |
|---|---|
| Downward swipe: which way works (finger curl / pointing hand / other hand shape)? | |
| Up, left, right with different shapes | |
| Accidental swipes in one minute of normal hand use: any hand shape / pointing finger only | |
| Preferred setting | |
