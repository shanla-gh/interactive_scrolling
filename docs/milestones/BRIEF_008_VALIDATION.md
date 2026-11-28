# Director validation - Brief 008 (beta 0.8.0b1)

About 30 minutes on one computer, plus a second session with a friend for Doomscroll
Together. Gesture recognition is unchanged; this checks the redesign, the live preview, the
clown makeup, Broadcast settings and two-person play.

## 1. Update and start (PowerShell)

```powershell
cd E:\interactive_scrolling
git pull
.venv\Scripts\python.exe -m pip install --no-deps -e .
scripts\run.ps1
```

**Reload the extension once** (it asks for two new permissions): open `edge://extensions`,
find *Interactive Scrolling Bridge* (version 0.5.0) and press **Reload**.

## 2. Main window (5 minutes)

1. Top bar: name, camera state, **Camera settings**, **Normal | Broadcast**, **More**,
   **Start camera**. Is it calm and clear? Anything missing that you used every day?
2. Press **Start camera**. Under the camera: **Gestures Off | Test | Live**, the state in one
   line, **Practice**, **Gesture settings**, **Stop (Ctrl+Alt+D)**.
3. **Camera settings**: device, resolution, frame rate, mirror, what is drawn on the camera.
4. Right side: **Browser**, **Doomscroll Together**, **Today** (Report opens the details).
5. Bottom: **Activity & diagnostics** opens and closes; the app remembers it.
6. Try a smaller window (or 150 % scaling): nothing clipped, nothing hidden?

## 3. Live Shorts preview (5 minutes)

1. In Edge open a YouTube Short, click the extension icon -> **Show this Short in the app**.
2. **Now playing** shows the Short live (Edge shows its "tab is being shared" indicator).
3. Click into Interactive Scrolling (it is now the active window), choose **Live**, swipe up and
   down: the Short changes in the preview. Open palm: pause/resume.
4. Is the sound still coming from the browser, once, without echo?
5. In the browser switch to another tab: the preview keeps the Short (never the other tab);
   gestures from the app still work. Switch back.
6. Navigate the tab to the YouTube home page: the picture disappears with a message; go back to
   a Short: it returns.
7. **Stop preview** (Browser section) ends it; the browser's sharing indicator disappears.

## 4. Clown makeup (5 minutes)

1. **More -> Broadcast settings -> Clown effect** on; **Preview stage** 1, 2, 3.
2. Stage 1 red nose; stage 2 plus red lips; stage 3 plus light white makeup. Your eyes, brows,
   beard/stubble, skin and hair must stay visible; no wig, no mask edge.
3. Move the **White makeup** slider (10-70 %); talk, smile, turn your head.
4. Is the default (35 %) the right strength? Note the value you prefer.
5. Set **Preview stage** back to **Off**.

## 5. Transparent background (3 minutes)

1. Press **Broadcast**. Move the mouse over the overlay -> **Settings** (top right).
2. **Transparent background** is the first option: switch it on. Light clothing kept? Fast arm
   movements: ghosting?

## 6. Doomscroll Together with a friend (15 minutes, two computers)

Both computers need 0.8.0b1, a camera and Discord (or similar).

**Same Wi-Fi**

1. Host: open a Short, **Doomscroll Together -> Host**, *Friend joins from*: **Local network**,
   **Start session**. Windows may ask to allow the app on **private networks**: allow it for
   private networks only (or cancel; then your friend cannot connect). **Copy invitation**,
   send it.
2. Guest: **Join**, paste the invitation, **Join**. Host: **Let them in**.
3. Host: share the browser window in Discord. Guest: watch it in Discord (do not open your own
   YouTube).
4. Both choose **Live**. Each swipes next/previous; the panel shows who did each action.
5. Both swipe at the same moment: only one Short is skipped.
6. Guest presses **Stop** (Ctrl+Alt+D): the guest's gestures stop; Host: **Stop** too.
7. Host: **End session**: the guest sees that the session ended.

**Different networks (only if you both use Tailscale or a similar private VPN)**

8. Both connected to the same tailnet. Host chooses **Private VPN (e.g. Tailscale)** and repeats
   steps 1-7. The app does not install or configure Tailscale.

Note the network round trip and "confirmed after" values in **Activity & diagnostics ->
Browser and Together** on the Guest.

## What to report back

| Item | Result |
|---|---|
| Main window: clear, calm, complete? | |
| Live preview: picture, gestures from the app, sound once, tab switching | |
| Clown: natural? preferred white strength | |
| Transparent background found at once? | |
| Doomscroll Together same Wi-Fi: joined, both controlled, simultaneous gestures, stop, end | |
| Doomscroll Together over VPN (optional) | |
| Anything that felt worse than 0.7.0b1? | |
