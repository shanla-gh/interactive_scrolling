# Browser extension: install, pair, reconnect

The desktop app controls YouTube Shorts and browser tabs through a small extension
(`browser_extension/`, "Interactive Scrolling Bridge"). It is not in any browser store; it is
loaded as an *unpacked* extension.

| Browser | Status |
|---|---|
| Microsoft Edge | supported; the automated browser tests run in Edge |
| Google Chrome | the same Chromium extension APIs; loading works manually, but Chrome is **not automatically tested** (branded Chrome no longer accepts the test switch) |
| Firefox, Safari | not supported |

Permissions (kept minimal): `storage` (the pairing code and port) and access to
`https://www.youtube.com/*` only. The extension talks only to the app on this computer
(`127.0.0.1`), and only after pairing.

## Install (once)

1. In the app, open the **Browser** tab and press **Copy extension folder path**.
2. In Edge open `edge://extensions` (Chrome: `chrome://extensions`).
3. Switch on **Developer mode** (Edge: left side; Chrome: top right).
4. Choose **Load unpacked** and paste the folder path (or browse to the `browser_extension`
   folder of Interactive Scrolling).
5. Optional: pin the extension icon to the toolbar.

## Pair (once)

1. In the app's **Browser** tab press **Copy** next to the pairing code.
2. Click the extension icon, paste the code, keep the port (47815 unless you changed it) and
   save.
3. Open `https://www.youtube.com/shorts`. The app's top bar shows **Browser: Shorts ready**.

## After an update

Press **Reload** on the extension card in `edge://extensions`, then reload the Shorts tab. The
pairing code is kept. If the app reports "browser extension is outdated", the extension was not
reloaded.

## Reconnecting

The extension reconnects by itself within a few seconds when the app starts or restarts. If
the top bar keeps showing a reason:

| Top bar | What to do |
|---|---|
| Browser: browser extension not connected | Is the extension enabled and paired? Click its icon to check the code and port. |
| Browser: no YouTube Shorts tab is active in the browser | Open `youtube.com/shorts` and keep that tab selected. |
| Browser: the browser is not the active window | Tab actions work only while the browser window is in front. |
| Browser: several browsers show Shorts; click the one to control | Click into the browser you want to use. |
| Previous Short: already at the first Short (gesture recognized...) | Your gesture worked; there is no earlier Short. |
| Like: not signed in to YouTube | Liking needs a signed-in YouTube account; nothing was clicked. |

Every gesture result in the history and on the video says whether the gesture was **not
recognized** (the "Why not recognized" line) or **recognized but the browser action was
rejected or failed** (the outcome column), so the two are never confused.

## Live preview in the app (0.8.0b1, extension 0.5.0)

After updating, open `edge://extensions` (or `chrome://extensions`) and press **Reload** on
Interactive Scrolling Bridge once: version 0.5.0 asks for two new permissions, `tabCapture`
(capture the one tab you choose) and `offscreen` (a hidden page that does the capture). For an
unpacked extension the browser grants them on reload without a prompt.

1. Open a YouTube Short in the browser.
2. Click the Interactive Scrolling extension icon and choose **Show this Short in the app**.
   The browser requires this click before any tab can be captured, and shows its own "this tab
   is being shared" indicator on the tab.
3. The Short appears under **Now playing** in the app. Only the video area of that one tab is
   sent, only to the app on this computer, without sound (the tab keeps playing its sound).
4. Stop it with **Stop the preview** in the popup, **Stop preview** in the app's Browser
   section, by closing the tab, or by hiding Now playing (More -> Show Now playing).

While the preview runs and the app is the active window, your Shorts gestures go to that tab
(you do not need to switch back to the browser). Switching tabs still needs the browser in
front. If the tab leaves Shorts, the picture disappears until it shows a Short again.

Tested automatically with Microsoft Edge (real YouTube and a local fixture page). Google Chrome
implements the same APIs but was not tested here.
