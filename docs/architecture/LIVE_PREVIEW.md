# Live Shorts preview ("Now playing")

Brief 008, milestone 37. The Short playing in the user's browser is shown live next to the
webcam in Normal Mode. It is the same video (not a second player, no download), mirrored
locally from one browser tab the user chose.

## Approaches evaluated (with prototypes)

| | A - extension tab capture (selected) | B - Windows Graphics Capture of the browser window | C - Win32 window capture (PrintWindow) |
|---|---|---|---|
| Prototype | `scripts/prototype_preview.py` (real YouTube), `tests/browser/test_live_preview_browser.py` (fixture with an encoded clock), `scripts/capture_live_preview.py` (real app window) | not run: running a downloaded capture binding was not permitted in this session; evaluated from its documented behaviour and the Brief 007 OBS attempt (OBS's WGC mode hung) | `scripts/prototype_window_capture.py` (ctypes only, real Edge window) |
| What is captured | exactly one tab, the one the user chose in the popup | the whole browser window: whatever tab is in front, address bar, other sites | the whole window, like B |
| Privacy when the user switches tab | still the Shorts tab (the captured tab keeps rendering); nothing else is ever captured | would show the other tab (private content) | **measured: showed the other page and the whole tab strip with other tabs' titles** |
| Browser minimized | keeps working (measured: 29 fps) | Windows delivers no new frames for minimized windows (documented) | no usable picture (measured) |
| Crop to the Short | page reports the video rectangle; crop in the browser (letterbox-aware) | needs DOM coordinates from the extension plus window/DPI mapping in the app | same as B |
| Consent | the browser requires the user's click on the extension (tab-capture invocation); the browser shows its "being shared" indicator on the tab | Windows capture picker or programmatic capture with the yellow border | none (silent) - unsuitable as a product mechanism |
| Audio | not captured; the tab keeps playing its sound normally | not captured | not captured |
| New dependencies | none (Chromium APIs: `tabCapture`, `offscreen`, WebCodecs `MediaStreamTrackProcessor`, `OffscreenCanvas`) | a native WinRT binding | none |
| Measured | 25-30 fps received, 7-12 ms browser-to-app transport (median), 23-27 ms page-to-app with a drawn clock, 30-55 KB per JPEG at 640 px height, 2 ms decode per frame in the app | - | 16.5 ms per grab of a 1280x882 window on the calling thread, but only **1.5 changing frames/s** while the Short played (PrintWindow returns stale frames of the GPU-composited video) |

Decision: **A**. It is the only approach that captures only the approved tab, keeps working when
the browser is minimized or another tab is in front, needs no new dependency and gives the user
an explicit, browser-enforced consent step. Its cost is a one-time extension reload (new
permissions) and the popup click per preview session. Chrome and Edge both implement these
APIs; automated tests run on Edge only (Chrome: manual check).

## Architecture

```
Browser (Edge/Chrome)                                         Desktop app (one process)
 popup "Show this Short in the app"  (user click = consent)
   -> service worker: tabCapture.getMediaStreamId(tabId)
   -> offscreen document (preview.html/js): getUserMedia(tab) -> MediaStreamTrackProcessor
   -> worker (preview_worker.js): crop to the Short, JPEG (q 0.72, <= 640 px high)
   -> ws://127.0.0.1:<port>/preview  (origin + pairing code)  ->  BridgeServer /preview
                                                                   PreviewFeed (latest frame only)
                                                                   PreviewView (decode on paint)
 content script: Shorts state + video rectangle ------------->  context.preview (protocol 3)
```

* **One frame, no queue.** The browser skips frames while the socket is busy (> 768 KB
  buffered) or an encode is running; the app keeps only the newest frame and decodes it only
  when the Now playing column is visible. Preview work never touches the camera/recognition
  threads (it runs on the bridge thread and the UI thread).
* **Encoding in a worker.** The offscreen document is a hidden page: its main-thread tasks are
  throttled (measured: about 1 encoded frame per second, 1 s delay). Moving crop and encode
  into a dedicated worker gave 25-30 fps.
* **Letterboxing.** Chromium fits the tab into the requested 1280x720 capture keeping the
  shape, with bars; the crop maps page coordinates through that fit (a 1280x900 viewport
  arrives pillarboxed).

## Privacy rules

* Only the video rectangle of the Short is sent; frames stop the moment the tab's URL leaves
  `/shorts/` (the service worker blanks the crop on any navigation before the page reports),
  and the app drops the last picture when the extension reports "hidden".
* Nothing is stored; the app never writes preview frames to disk.
* No audio, no microphone.
* Loopback only, same origin and pairing-code checks as the control connection; one preview
  connection at a time; frames validated (JPEG header, size <= 1 MB, finite capture time).
* The preview ends when the user stops it (popup or app), the tab closes, the app disconnects,
  or the pairing code changes.

## Control while the app is in front (CP 37.4)

The browser normally only accepts Shorts commands for the active tab of the focused window. In
a preview session the user has explicitly chosen one tab, so:

* while a preview is authorized **and** an Interactive Scrolling window is the active window,
  Shorts commands (next, previous, pause, like) carry that tab's id;
* the extension accepts a tab id only if it equals the authorized preview tab, then re-checks
  that the tab still shows a Short and the expected video;
* tab switching never uses this path (it still requires the browser to be the active window);
* outside this condition the ordinary policy applies unchanged;
* stopping the preview (or closing the tab) revokes it; a command for the old tab id is
  refused ("not the tab shown in the live preview");
* Ctrl+Alt+D / Stop disable all gesture control as before.

Measured on real YouTube: next/previous/pause through the preview path succeeded with the
Shorts tab in front, with another tab in front and with the browser minimized; after stopping,
the old tab id was refused.

## Tab switching and context changes

* The user switches tabs in the browser: the preview keeps showing the chosen Shorts tab (it
  is still the captured tab); gestures from the app still go to it.
* The chosen tab navigates away from Shorts: the picture disappears ("Your browser tab left
  YouTube Shorts"), the browser section says so, Shorts gestures are refused with "the previewed
  tab is not showing a YouTube Short"; the picture returns when the tab shows a Short again.
* The tab is closed: the preview ends.

## Measurements (development machine, Edge, 1280x900 window)

| Scenario | Received fps | Browser-to-app transport (median) | Notes |
|---|---|---|---|
| Shorts tab in front | 25-30 | 7-12 ms | real YouTube, 5 runs |
| Another tab in front | 27 | 10 ms | commands to the preview tab succeeded |
| Browser minimized | 29 | 9 ms | commands succeeded |
| Fixture with drawn clock | 26-28 | 3-5 ms | page-to-app 23-27 ms (drawing -> compositor -> capture -> crop -> encode -> transfer) |
| App painting | 24.6 painted/s | - | 2.0 ms per decode on the UI thread |

Not measured: the delay added by the app's own painting and the display (no camera aimed at
the screen) and Chrome (manual). Browser CPU with the preview on: +1.7 % of the machine
(interleaved on/off rounds; PERFORMANCE_008.md).

## Known limitations

* The popup click is needed for every preview session (browser rule); there is no way for the
  app to start a capture by itself.
* Unpacked extension: after updating, the extension must be reloaded once (new permissions).
* A paused or static Short produces few frames (the browser delivers frames when the page
  changes); the last picture stays.
* Tab capture adds about 1.7 % machine CPU in the browser (and some GPU work) while it runs.
