# Director validation - Brief 007 (beta 0.7.0b1)

About 20 minutes. Gesture recognition is unchanged from 0.6.0b1; this checks the product
experience.

## 1. Update and start (PowerShell)

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install --no-deps -e .
scripts\run.ps1
```

The **Getting started** window appears once (also later via **Help**). The extension did not
change; no reload needed.

**Before anything else:** a Windows Security prompt "allow OBS Studio on public and private
networks?" may still be open from an automated OBS test. It is your choice; OBS works locally
either way. Cancel keeps OBS blocked from incoming network connections.

## 2. Main window (3 minutes)

1. The header says **CAMERA OFF / CAMERA ON** - it is about the camera only.
2. The bar below says **GESTURES: Gestures off | Gesture test | Live control | Stop control**
   and **Browser: ...** - is it clear at a glance whether gestures act on the browser?
3. Gesture settings: the dialog fits your screen; **Show advanced thresholds** reveals the rest.
4. Practice: the instructions no longer require a pointing finger.

## 3. Broadcast Mode (8 minutes)

1. Open YouTube Shorts in Edge, press **Broadcast Mode**. The overlay shows **GESTURES OFF** /
   **GESTURE TEST** / **LIVE CONTROL** in its corner - is that clear but unobtrusive?
2. Drag and resize the overlay; right-click -> **Position** -> a corner. Click into YouTube and
   use the keyboard (space = pause): the browser must keep the focus.
3. Right-click -> **Session timer and counters**; **Smooth skeleton** on/off: does the
   skeleton look calmer with it on, without lagging behind fast swipes?
4. **Transparent background** with light clothing: is the shirt kept (no room showing through)?
   Move your arms quickly: any ghosting?
5. OBS: Display Capture of the screen - record 20 seconds of swiping Shorts. Optional: add a
   Window Capture of "Interactive Scrolling - Broadcast Mode" with method "Windows 10 (1903 and
   up)" and note whether the transparent area is transparent or black.

## 4. Background Mode (2 minutes)

**To tray**; right-click the tray icon: camera and gesture state are shown; stop gesture
control; Developer Mode brings the window back.

## What to report back

| Item | Result |
|---|---|
| Status wording clear (camera / gestures / browser)? | |
| Broadcast overlay: positioning, focus, smoothing, control chip | |
| Transparency with light clothing, fast arms | |
| OBS Display Capture recording ok? Window Capture (WGC): transparent or black? | |
| Anything that felt worse than 0.6.0b1? | |
