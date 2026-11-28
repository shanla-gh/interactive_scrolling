# interactive_scrolling

Hands-free YouTube Shorts and browser control with ordinary laptop webcam gestures, plus
playful computer-vision effects, simple personal usage reports and a two-person co-op mode.
Free and open source. All camera processing runs locally on your computer.

> **Status: beta 0.6.0b1 (not a stable release).** Everything below is implemented and
> covered by automated tests; gesture recognition was reworked after the Director's first
> real-world test, and the Director's validation (real gestures, signed-in browser, two
> computers for co-op) is still pending. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for what is
> verified and what is not, and the [gesture guide](docs/guides/GESTURE_GUIDE.md).

## Features

**Gestures** (either hand, rule based, calibrated on recordings):

| Gesture | Default action |
|---|---|
| Move the hand up / down - any hand shape (pointing finger, fist, open hand) | Next / previous YouTube Short |
| Move the pointing finger to your right / left | Next / previous tab of the active browser window |
| Half-heart (one half of a two-handed heart), held | Like the Short |
| Open palm, held | Pause / resume |

Safe control modes (*Gestures off*, *Gesture test*, *Live control*), an emergency stop
(button, Esc, **Ctrl+Alt+D** anywhere), sensitivity presets, per-gesture on/off and mapping.
**Practice** explains after every try why a gesture was or was not recognized; **Quick
Calibration** ([guide](docs/guides/CALIBRATION_GUIDE.md)) adapts it to your movements;
**Copy diagnostics** exports the recent decisions without personal data.
Every action is confirmed from the page and reported as succeeded, no change, rejected, failed
or unknown.

**Normal Mode**: your camera with the hand skeleton next to **Now playing** - the Short from
your browser, live in the app (started from the extension popup; only that tab's video area,
locally, without sound) - with the browser connection, **Doomscroll Together** and today's
summary on the right and a collapsible diagnostics console at the bottom.
**Broadcast Mode**: compact always-on-top overlay for OBS with **Broadcast settings**
(transparent background, layers, clown). **Background Mode**: tray icon that always shows the
camera and control state.

**Wellbeing and reports** (local only, can be switched off and deleted): today's scrolling
time, sessions, longest session, actions, gestures, a transparent **Doomscroll Index**,
optional Reality Checks, limits and a reversible pause of gesture scrolling; a Gesture
Performance Report.

**Fun**: the **Progressive Clown Transformation** (red nose -> red lips -> light white makeup
as a scrolling session goes on; your face stays visible), optional **passive eye analytics**
(estimated screen-facing / looking-away time, blinks; never used for control), **Doomscroll
Wrapped** (1080x1920 PNG summary for stories), **Doomscroll Together** (two people, one feed:
both swipe, the Host's browser plays, you watch through Discord; same Wi-Fi or a private VPN -
see [the guide](docs/guides/DOOMSCROLL_TOGETHER.md)).

## Install (from source)

Requirements: Windows 10/11 x64, a webcam, Python 3.12 (`py` launcher), Microsoft Edge or
Google Chrome for browser control.

```powershell
git clone https://github.com/shanla-gh/interactive_scrolling.git
cd interactive_scrolling
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # venv, dependencies, models
scripts\run.ps1
```

`setup.ps1` downloads the three MediaPipe models once (~11.8 MB in total, verified by SHA-256);
after that everything works offline. A packaged build is described in
[docs/RELEASE.md](docs/RELEASE.md).

### Browser extension

1. In the app: **Browser -> Setup and pairing**, copy the pairing code.
2. `edge://extensions` (or `chrome://extensions`) -> *Developer mode* -> *Load unpacked* ->
   select the `browser_extension` folder. (After an update: press *Reload* on its card;
   0.8.0b1 needs this once for the live preview permissions.)
3. Click the extension icon, paste the code, *Save and connect*.

## Use

1. **Start camera**, choose **Test** under the camera, practise the gestures (nothing is
   executed).
2. Open a YouTube Short, optionally click the extension icon -> *Show this Short in the app*,
   then choose **Live**.
3. Optional: *Broadcast*, *More* (Background Mode, Broadcast settings, reports, face effects),
   *Doomscroll Together*.

A step-by-step guide with every feature is the
[Director acceptance checklist](docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md).

## Privacy

* Camera frames never leave the computer and are never written to disk; no cloud services, no
  telemetry, no accounts.
* The browser extension reads only YouTube pages; tab switching uses tab positions, never
  titles or URLs.
* Statistics contain event categories and durations only (no URLs, titles, video ids, faces or
  landmarks); eye analytics store daily totals only. Switch off and delete in *Today -> Report*.
* The live preview sends only the video area of the one tab you chose, only to the app on this
  computer, and nothing is stored.
* No face identification; face landmarks are used only for the clown effect and eye estimates.
* Doomscroll Together sends only small signed control events (next, previous, pause) over
  your own private network; no video, camera or browsing data.

## Development

```powershell
scripts\test.ps1              # format, lint, all hardware-independent tests
scripts\test.ps1 -Hardware    # including the physical webcam tests
.venv\Scripts\python.exe -m pytest tests\live --live-youtube   # optional, real website
```

Documentation: [architecture](docs/architecture/ARCHITECTURE.md),
[gestures](docs/architecture/GESTURES.md), [browser](docs/architecture/YOUTUBE_INTEGRATION.md),
[reports](docs/architecture/REPORTING.md), [UI and effects](docs/architecture/UI_AND_EFFECTS.md),
[co-op](docs/architecture/COOP.md), [decisions](docs/architecture/DECISIONS.md),
[conventions](docs/ENGINEERING_CONVENTIONS.md), [roadmap](ROADMAP.md),
[changelog](CHANGELOG.md).

## License

MIT, see [LICENSE](LICENSE). Third-party components and models:
[docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md).
