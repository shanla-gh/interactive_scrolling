# Director checklist: gestures and YouTube Shorts (M2 + M3)

About 15 minutes. Record pass / fail and short notes in `PROJECT_STATUS.md` (or send them).

## 1. Start

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
scripts\run.ps1
```

Click **Start camera**. The control bar must show **Tracking only** selected.

## 2. Gesture reference

| Gesture | How | Action |
|---|---|---|
| Swipe down | Point with your index finger (other fingers folded) and move the **whole hand** down quickly, about a hand's length. Keep the finger pointing. | Next Short |
| Swipe up | Same, moving up | Previous Short |
| Thumbs up | Thumbs up, hold still ~1 s | Like |
| Stop | Open hand, fingers up, palm to the camera, hold still ~1 s | Pause / resume |
| Hand sweep right / left | Open hand, big fast sweep to your right / left | none yet (shown only) |

Tips: wait about a second between swipes; returning your hand after a swipe is ignored.
Flicking only the finger (curling it) is **not** a swipe.

## 3. Gesture test (nothing reaches YouTube)

- [ ] Click **Gesture test**. Perform each gesture twice: the banner on the video and the
      *Gesture history* show it once per gesture, with outcome "not executed - Gesture test mode".
- [ ] Hold a thumbs up for 3 s: exactly **one** THUMBS UP.
- [ ] Sit normally, touch your face, type for 20 s: **no** gestures appear.
- [ ] Show both hands at once: the Gestures tab says "ambiguous" and nothing triggers.
- [ ] Optional: *Gesture settings...* -> try Low / High, restart the app, check the choice is kept.

## 4. Browser setup (once)

- [ ] In the app's **YouTube** tab click **Copy** next to the pairing code.
- [ ] Edge: open `edge://extensions`, enable **Developer mode**, **Load unpacked**, select
      `E:\interactive_scrolling\browser_extension`.
- [ ] Click the extension icon (puzzle piece -> Interactive Scrolling Bridge), paste the code,
      **Save and connect** -> "Connected to the desktop app".
- [ ] Open https://www.youtube.com/shorts and let a Short play. The control bar shows
      **YouTube: ready (edge)**.

## 5. Live control

- [ ] Click **Live control** (the control bar turns red).
- [ ] Swipe down -> next Short; history shows "succeeded". Swipe up -> previous Short.
- [ ] One swipe moves exactly **one** Short (try a few times).
- [ ] Stop gesture -> pauses; stop again -> resumes; holding the pose does not toggle again.
- [ ] Thumbs up on a Short you have not liked -> it becomes liked (only do this on a Short you
      are happy to like). Thumbs up again on the same Short -> "no change - already liked"
      (it must **not** unlike).
- [ ] Press **Ctrl+Alt+D** while the browser is focused -> control switches to Tracking only;
      further gestures do nothing.
- [ ] Enable Live control again, switch the browser tab to another website -> gestures show
      "rejected - no YouTube Shorts tab is active".
- [ ] Minimise the browser -> gestures are rejected (Shorts tab not visible).
- [ ] Close the app, start it again: the **YouTube** tab's *Today* statistics still show your
      counts; *Clear statistics* empties them.

## 6. Report

Note anything that triggered when you did not intend it, anything that did not trigger, and
whether the gestures felt natural. These observations are used to tune the presets.
