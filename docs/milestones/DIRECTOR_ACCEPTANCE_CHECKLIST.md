# Director acceptance checklist (Engineering Brief 003, release candidate 0.3.0rc1)

One consolidated checklist for everything implemented in Briefs 002 and 003. It replaces
`M2_M3_DIRECTOR_CHECKLIST.md` (whose thumbs-up and open-hand-sweep items are superseded). No
source code is needed. Mark each item pass / fail and add a short note; send the result (or
edit `PROJECT_STATUS.md`). About 60-75 minutes in total; sections can be done on different days.

Markers: **[2 PCs]** needs two computers, **[account]** needs your signed-in YouTube account,
**[OBS]** needs OBS Studio.

## 0. Update and start (5 min)

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
.venv\Scripts\python.exe scripts\download_model.py      # also fetches the two new models
scripts\run.ps1
```

- [ ] The window opens; a coloured dot appears in the system tray (grey = camera off).
- [ ] Browser extension: `edge://extensions` -> the "Interactive Scrolling Bridge" card ->
      **reload** (it is version 0.3.0 now). The Browser tab shows "1 browser connected".
- [ ] Click **Start camera**. The tray dot turns green; hover shows "camera ON, Tracking only".

## 1. Gestures in Gesture test (nothing is executed) (15 min)

Choose **Gesture test**. Watch the banner on the video and the gesture history.

| Gesture | How |
|---|---|
| Swipe down / up | Point with your index finger (other fingers folded) and move it down / up quickly, about a hand's length. A wrist movement is enough if the fingertip travels that far. |
| Swipe right / left | The same, to **your** right / left. |
| Half-heart | One half of a two-handed heart, made with one hand: fingers curved over to the side, index tip pointing down, thumb pointing down, tips apart. Hold ~1 s. |
| Stop | Open hand, fingers up, palm to the camera, hold ~1 s. |

- [ ] Each swipe direction, 4 times with your usual hand: exactly one matching banner per swipe.
- [ ] Each swipe direction, 4 times with the **other** hand.
- [ ] Swipe right 4 times in a row (bringing the hand back each time): **4 x SWIPE RIGHT and no
      SWIPE LEFT**. Same for left, down, up. (This checks return movements and preparation
      movements; note any opposite swipe.)
- [ ] Swipe down, bring the hand back, pause briefly, swipe up: SWIPE DOWN then SWIPE UP.
- [ ] Diagonal pointing movements: nothing (or "diagonal movement" in the Gestures tab).
- [ ] Half-heart 3 times (lower the hand in between): 3 x HALF HEART; then hold it 5 s: exactly one.
- [ ] Half-heart with the other hand works too.
- [ ] Pinch, thumbs up, a C-shaped hand, pointing still, touching your face: **no** HALF HEART.
- [ ] Stop pose: one STOP per hold (try at your normal sitting distance and at arm's length;
      note if it fails far away).
- [ ] Sit normally, type, touch your face for 30 s: no gestures.
- [ ] Optional but valuable: record the guided session so the gestures can be measured on your
      hands: `.venv\Scripts\python.exe scripts\record_gestures.py --session 3` (about 4 minutes,
      landmark numbers only, stays on your computer in `recordings\`). Then run
      `.venv\Scripts\python.exe scripts\evaluate_gestures.py recordings\gestures_*.json` and
      send the printed table.
- [ ] *Gesture settings...*: switch one gesture off and remap another; restart the app; the
      choices are kept.

## 2. Browser control in Live control (15 min) [account for the like]

Open a YouTube Shorts page in Edge and let it play. Click **Live control** (red bar).

- [ ] Swipe down -> next Short ("succeeded" in the history); swipe up -> previous Short.
- [ ] One swipe moves exactly one Short (repeat a few times).
- [ ] Open two more ordinary tabs to the right of the Shorts tab, go back to Shorts.
      Swipe right -> the next tab becomes active; swipe right again -> the next one; at the last
      tab -> "rejected - already at the last tab", nothing changes (no wrap-around).
- [ ] Swipe left until you are back on the Shorts tab; swipe down works again there.
- [ ] On a non-YouTube tab, swipe down -> "rejected - no YouTube Shorts tab is active".
- [ ] Click into the Interactive Scrolling window (browser not focused) and swipe right ->
      "rejected - the browser is not the active window"; no other application switches.
- [ ] With a second Edge window open, tab swipes only change tabs in the window you are using.
- [ ] Stop pose -> pause; stop again -> resume.
- [ ] **[account]** Half-heart on a Short you are happy to like -> it becomes liked; again ->
      "no change - already liked" (never unlikes).
- [ ] **Ctrl+Alt+D** while the browser is focused -> Tracking only; gestures do nothing.

## 3. Three UI modes (10 min) [OBS]

- [ ] Click **Creator overlay**: the main window hides; a small camera overlay floats on top.
      Drag it, resize it from the bottom-right corner, right-click for layers and opacity.
- [ ] While the overlay is shown and Live control is on, swipe in the browser: the browser keeps
      the keyboard focus (type in the address bar to check); the overlay shows the gesture and
      "Success".
- [ ] Right-click -> **Transparent background**: the room around you disappears, you and your
      hands stay visible; edges acceptable; no flashing of the room. Note how it looks with
      your lighting.
- [ ] **[OBS]** Add the overlay to OBS with *Window Capture* (try the "Windows 10 (1903 and up)"
      method, and if needed "allow transparency"/"Display Capture" with a crop) and note which
      setting shows the transparency correctly.
- [ ] Right-click -> **Background Mode**: all windows hide, the tray dot stays and shows the
      state; right-click the tray icon: Stop camera / Start camera / Disable control work;
      **Developer Mode** brings the dashboard back. Camera and Live control kept running
      throughout (no restart).
- [ ] **Quit** from the tray: the camera light goes off and the process ends.
- [ ] *View* tab -> *Appearance...*: change skeleton colour, sizes, trail length; hide gesture
      feedback; check the overlay corner/size/opacity options.

## 4. Reports, Anti-Doomscroll, Doomscroll Index (10 min)

- [ ] Watch Shorts for a few minutes (video playing, browser focused). *Today* tab: scrolling
      time grows; pause the video or switch to another app -> it stops growing.
- [ ] Counts for next/previous, tab right/left, likes and pause match what you did; "Confirmed
      gestures" also counts gestures that were not executed.
- [ ] *Performance* tab shows dispatched / successful actions, success rate, action latency,
      live FPS and latency.
- [ ] *Limits and reminders...*: enable reminders, set the session limit to 2 min and Reality
      Check to 1 min, tick "pause gesture scrolling when a limit is reached". Scroll: a Reality
      Check notice after 1 min, a limit notice after 2 min, then swipes show "rejected -
      gesture scrolling paused"; likes and tab swipes still work; **Resume gesture scrolling**
      restores it.
- [ ] The Doomscroll Index and its label are shown; "Playful wording" off gives plain labels.
- [ ] Restart the app: today's numbers are kept. *Delete all statistics* empties them.

## 5. Progressive Clown Transformation and eye analytics (10 min)

- [ ] *Today* tab -> *Face effects and eye analytics...*: enable the clown, set *Preview* to
      stage 1, 2 and 3 in turn: red nose; then makeup; then full clown with wig. It follows
      your head, turns with it, the mouth paint follows when you talk/smile, it disappears when
      you leave the frame. Note any misalignment or flicker.
- [ ] Set Preview off and thresholds to 1 / 2 / 3 minutes; scroll: the stages appear with the
      session.
- [ ] Creator overlay with transparent background and the clown together.
- [ ] Enable eye analytics, *Calibrate...* (look at the screen centre 3 s): "Calibrated".
      Scroll for a few minutes, look away sometimes: *Visual behavior* shows facing-the-screen,
      looking-away and unknown durations, blinks, tracking quality. Plausible? (Estimates only.)
- [ ] Eye analytics never changes anything in the browser.

## 6. Doomscroll Wrapped (5 min)

- [ ] *Wrapped: today...* -> preview shows your real numbers; *Save PNG* -> choose a folder;
      the 1080x1920 image looks good on your phone; no name, photo or account data on it.
- [ ] *Wrapped: session...* during a scrolling session.

## 7. Co-op Doomscroll (15 min) [2 PCs] [account optional]

Both computers on the same Wi-Fi/LAN (or the same private VPN), both running this version.

- [ ] Host: *Co-op* tab -> name -> **Create session**. Note the code and address shown. Allow
      the firewall prompt for private networks if Windows asks.
- [ ] Guest: name, Host address, code -> **Join** -> "waiting for ... to approve". Host:
      **Approve guest**.
- [ ] Host shares the Shorts window in Discord (or similar) so the Guest can see it.
- [ ] Both in Live control. Guest swipes down -> the Host's Short changes; both panels show
      "<Guest> -> Next Short -> Success". Host swipes -> attributed to the Host.
- [ ] Both swipe at the same moment -> only **one** Short skipped.
- [ ] Guest half-heart / tab swipe -> rejected ("not shared"); nothing happens on the Host.
- [ ] Host unticks *Guest may control my feed* -> Guest swipes are rejected; tick again -> work.
- [ ] Host presses Ctrl+Alt+D -> Guest swipes are rejected.
- [ ] Wrong code on the Guest -> refused.
- [ ] Guest closes the app / loses Wi-Fi -> Host shows the guest disconnected. Host ends the
      session -> Guest shows disconnected.
- [ ] Network round trip shown on the Guest; *Duo Wrapped...* on the Host.

## 8. Packaged build (5 min)

- [ ] Unzip the release build to a new folder (or run `dist\InteractiveScrolling\
      InteractiveScrolling.exe` after building, see README), run `InteractiveScrolling.exe
      --self-test`, then open `%LOCALAPPDATA%\interactive_scrolling\self-test.json`: "PASS".
- [ ] Start `InteractiveScrolling.exe`, start the camera, gestures work like in the source build.

## Report

For every failure: what you did, what happened, what you expected. Also: did the gestures feel
natural and reliable? Which ones triggered when you did not intend them?
