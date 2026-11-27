# Browser integration: YouTube Shorts and tab navigation

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
| Commands | Only `next_short`, `previous_short`, `like_short`, `toggle_playback`, `next_browser_tab`, `previous_browser_tab`; no generic channel |
| Extension permissions | `storage` and host access to `https://www.youtube.com/*` only (unchanged by tab navigation, which needs no `tabs` permission); other tabs' URLs and titles are not readable |
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
loaded (observed on the live site), so loading Shorts are not sent commands.

**Transient states (Brief 004, ADR-028).** Right after a navigation the page briefly reports no
Short (the service worker drops the tab's state on the URL change and now asks the page to
report again; the page also reports URL changes within 100 ms) and the new Short loads for a few
hundred milliseconds. While a Shorts page was seen less than 1.5 s ago, "the Short is changing"
and "the Short is still loading" are *transient*: the dispatcher waits for them, at most 1.2 s,
in a single attempt (no retries). After a confirmed navigation the controller also knows the
new Short's id and waits until the page reports it, so a quick second command never carries
the previous id.

**First Short (Brief 004).** At the first Short of a feed YouTube keeps the "previous" button in
the layout but hides its host (`aria-hidden`, `visibility: hidden`, opacity 0) without
disabling it; a click does nothing. Version 0.3 clicked it and reported failure after 3 s - all
five failures of the Director's test. The page now reports `can_previous` / `can_next` and
"previous" is refused at once ("already at the first Short", 11 ms on the live site).

## Tab navigation (Brief 003)

* `next_browser_tab` / `previous_browser_tab` (default: index swipe right / left) activate the
  tab directly to the right / left of the active tab **in the focused normal window** of the
  browser. Positions come from `chrome.windows.getLastFocused({populate: true})`; titles and
  URLs are neither needed nor readable.
* Context: the app sends tab commands only to a connected browser whose context reports that
  one of its windows has the operating-system focus (`browser_focused`, read from
  `window.focused` at every report, not only from focus events). No Shorts page is required, so
  the user can navigate away from Shorts and back. If several browsers report focus, the one
  focused most recently is used; equal times are rejected.
* At the first or last tab nothing changes (`rejected`: "already at the first/last tab"); there
  is no wrap-around. Other windows and other applications are never touched (the extension only
  calls `chrome.tabs.update` on a tab of the focused window).
* Confirmation: success only if the target tab is the active tab afterwards; the result carries
  the 0-based positions and the tab count, which the app shows ("tab 3 of 4 active") and never
  stores.
* Duplicates: the dispatcher executes one action at a time and the extension ignores a command
  id it has already handled.
* Compatibility: protocol version 2. Extensions of version 0.2 (protocol 1) still control Shorts;
  for tab actions the app answers "browser extension is outdated; reload it".
* Verified with the real extension in headless Edge (`tests/browser/`): leave Shorts to the
  right, no wrap at the last and first tab, back to Shorts with Shorts control available again,
  a second window is never affected. Chrome uses the same Chromium APIs but is not automated
  (branded Chrome no longer accepts `--load-extension`).

## Outcomes

| Action | Success means | Other outcomes |
|---|---|---|
| Next / previous | the active Short id changed within the timeout | rejected (no next / first Short, still loading, context changed), failed (did not change) |
| Like | `aria-pressed` became `true` | no change (already liked; never unliked), rejected (not signed in, YouTube asked to sign in), unknown (no confirmation) |
| Pause / resume | the video's `paused` state flipped | failed (browser blocked playback / state unchanged), rejected (no video) |
| Next / previous tab | the neighbouring tab became the active tab | rejected (first/last tab, browser not the active window, outdated extension), failed (tab not activated) |
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
* Brief 004 live probe through the dispatcher (signed out, Shorts tab kept in front): previous
  at the first Short refused in 11 ms; 8/8 consecutive "next" and 4/4 "previous" succeeded,
  "next" taking about 1 s each because it waits for the new Short to load, "previous" 0.3-0.6 s.

## Known limitations

* Depends on YouTube's current page structure (Nov 2026); changes may break actions, which are
  then reported as failed or unknown rather than successful.
* Liking with a real account has only been verified on the fixture; real-account liking is part
  of the Director checklist.
* Chrome requires manual *Load unpacked*; Firefox is not supported.
