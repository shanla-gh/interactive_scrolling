# YouTube Shorts integration

## Strategy (ADR-011)

A minimal **Manifest V3 browser extension** (`browser_extension/`) plus a **loopback WebSocket
bridge** in the desktop app.

Alternatives considered:

* *Synthetic keyboard input* (ArrowDown/ArrowUp, Space): cannot tell which application or tab
  receives the keys, cannot read the like or playback state, and YouTube has no reliable like
  shortcut (the brief rules out `L`). It would be impossible to confirm outcomes or avoid
  acting on unrelated windows.
* *Browser automation* (remote debugging of the user's browser): heavyweight, requires starting
  the browser in debugging mode and would expose far more control than needed.
* *Native messaging*: equally secure but needs a registered native host executable and registry
  entries; the WebSocket bridge achieves the same boundaries with less installation.

The extension reads page state directly, so every action is **confirmed from the page**:
navigation by a changed `/shorts/<id>`, likes by `aria-pressed="true"`, playback by the video
element's `paused` state. Nothing is reported as successful merely because a request was sent.

## Installation

1. Start the app (`scripts\run.ps1`). The YouTube tab shows the bridge status, the pairing code
   (Show / Copy) and these steps.
2. Microsoft Edge: `edge://extensions` (Chrome: `chrome://extensions`), enable *Developer mode*,
   *Load unpacked*, select the repository's `browser_extension` folder.
3. Click the extension icon, paste the pairing code, keep port 47815, *Save and connect*.
4. Open a YouTube Shorts page. The app's control bar shows `YouTube: ready (edge)`.

The extension has the fixed ID `phcdgkmcjbgdligepbkfkceejlbbmlio` (public key in the manifest).
Tested with Edge 158 and Chrome 158 page structure; automated tests load it into Edge, which
still accepts `--load-extension` (branded Chrome 158 no longer does).

## Security and privacy model

| Boundary | Implementation |
|---|---|
| Network exposure | Server binds to `127.0.0.1` only |
| Who may connect | WebSocket upgrade only on `/bridge` and only with `Origin: chrome-extension://phcdgkmcjbgdligepbkfkceejlbbmlio`; web pages are refused with 403 |
| Authentication | First message must be `hello` with the pairing code (constant-time comparison) within 5 s, else close code 4001 |
| Input validation | Strict schema per message type, 16 KB size limit, binary frames refused; 5 invalid messages close the connection |
| Commands | Only `next_short`, `previous_short`, `like_short`, `toggle_playback`; no generic channel |
| Extension permissions | `storage` and host access to `https://www.youtube.com/*` only; other tabs' URLs are not readable |
| Target | Only the active tab of the last focused browser window, only if it is a visible `/shorts/` page whose video has loaded, only if it still shows the Short the app expects |
| Credentials | None collected; the user's normal browser session is used; liking while signed out is refused without clicking |
| Stored data | Pairing code and port in `chrome.storage.local`; the app stores the code in `%LOCALAPPDATA%\interactive_scrolling\settings.json` |

A local process running as the same user could read the pairing code from that file; this is
inside the operating system's trust boundary and documented as an accepted risk.

## Context policy

The controller accepts an action only when a connected browser reports, within the last 5 s,
that the active tab of its last focused window is a visible YouTube Shorts page with a loaded
video. With several browsers, the one focused most recently is the single target; equal focus
times are rejected as ambiguous. Each command carries the expected video id and the extension
re-validates everything before acting. YouTube ignores navigation until the active video has
loaded (observed on the live site), so loading Shorts are rejected as "still loading".

## Outcomes

| Action | Success means | Other outcomes |
|---|---|---|
| Next / previous | the active Short id changed within the timeout | rejected (no next / first Short, still loading, context changed), failed (did not change) |
| Like | `aria-pressed` became `true` | no change (already liked; never unliked), rejected (not signed in, YouTube asked to sign in), unknown (no confirmation) |
| Pause / resume | the video's `paused` state flipped | failed (browser blocked playback / state unchanged), rejected (no video) |
| Any | | unknown when the browser did not answer in time, disconnected, or control was disabled mid-action |

## Verification

* `tests/integration/test_youtube_bridge.py`: security boundaries and outcomes with a scripted
  extension client.
* `tests/browser/`: the real extension in headless Edge against a local fixture that reproduces
  the Shorts page structure, served at real `https://www.youtube.com/shorts/...` URLs through
  request interception (runs in CI).
* `tests/live/` (opt-in `--live-youtube`): the real website in a signed-out throw-away profile.
  One full pass recorded (next 312 ms, previous 211 ms, pause 4 ms, resume 5 ms, like refused as
  signed out); other runs were affected by the automated browser (startup tabs taking focus,
  a click ignored by the site) and are not evidence of correct behaviour either way.

## Known limitations

* Depends on YouTube's current page structure (Nov 2026); changes may break actions, which are
  then reported as failed or unknown rather than successful.
* Liking with a real account has only been verified on the fixture; real-account liking is part
  of the Director checklist.
* Chrome requires manual *Load unpacked*; Firefox is not supported.
