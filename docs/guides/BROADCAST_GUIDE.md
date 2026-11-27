# Broadcast Mode: recording YouTube Shorts with your camera overlay

Broadcast Mode replaces the dashboard with a small, always-on-top camera window that you
place over the browser. It is a view only: it does not change gesture control, never takes
the keyboard focus from the browser, and the camera, models and statistics keep running.

## Workflow (OBS or another recorder)

1. Start Interactive Scrolling and press **Start camera**.
2. Connect YouTube Shorts (see [BROWSER_EXTENSION_GUIDE.md](BROWSER_EXTENSION_GUIDE.md)); the
   top bar shows **Browser: Shorts ready**.
3. Choose **Live control** if gestures should act on the browser (the overlay shows
   **GESTURES OFF**, **GESTURE TEST** or **LIVE CONTROL** in its top-left corner).
4. Press **Broadcast Mode**. The dashboard hides; the overlay appears in the bottom-right corner.
5. Position it: drag it anywhere, drag its bottom-right corner to resize (16:9 is kept), or
   right-click -> **Position** for a corner of the screen it is on. A saved position that is no
   longer on any screen (monitor removed, scaling changed) is replaced by the bottom-right
   corner of the primary screen.
6. Optional: right-click -> **Transparent background** (removes the room around you; see below).
7. In OBS add **Display Capture** of the screen with the browser and the overlay, and record.
8. Back to the dashboard: double-click the overlay or right-click -> **Developer Mode**.

Clicking or dragging the overlay leaves the browser the active window: you can keep using
YouTube with mouse and keyboard. To stop gesture control at once press the global shortcut
(shown in the dashboard) or use the tray icon -> **Stop gesture control**.

## Overlay layers (right-click)

| Layer | Default | Notes |
|---|---|---|
| Hand skeleton | on | drawn with display-only smoothing (still-hand shimmer about 30 % lower on the recordings; recognition uses the raw landmarks) |
| Motion trails | on | the measured fingertip trail |
| Motion vectors | off | the measured velocity |
| Last gesture, Action outcome | on | "Success" appears only when the browser confirmed the action |
| Session timer and counters | off | session time and today's executed actions |
| Gesture control status | on | off / test / live control |
| Smooth skeleton (display only) | on | |
| Transparent background | off | |
| Opacity, Size, Position | | |

The clown effect, when switched on in the dashboard, is drawn on the overlay as well.

## Transparent background

Local person segmentation turns the area around you transparent. It is presentation only: hand
tracking always receives the original camera image. If no fresh segmentation is available,
the overlay **hides the camera image** and says "Background removal unavailable - camera image
hidden" rather than showing your room; it recovers by itself when segmentation is back.
Version 0.7 keeps low-confidence patches that are enclosed by your outline (light clothing
against a dark background used to let the room show through the shirt). Real image quality
depends on light and clothing and has only been checked on synthetic material so far.

## Capture methods (tested 2026-11-27 on the development machine)

| Method | Result | Evidence |
|---|---|---|
| Desktop composition (what OBS **Display Capture** records) | **works**: transparent areas show the windows behind the overlay | `scripts/verify_overlay_capture.py`, screen grab at 125 % scaling |
| Window capture via PrintWindow (comparable to OBS **Window Capture, BitBlt**) | transparent areas are **opaque black** | same script |
| OBS **Window Capture, Windows 10 (1903 and up)** | **not verified** | an automated OBS test was attempted; OBS hung while taking a source screenshot (D3D11 staging-surface error) and was closed; its configuration was restored |

Recommendation: use **Display Capture** (or capture the browser window and add the overlay
as a separate Display Capture crop). To check Window Capture yourself: OBS -> Sources -> + ->
Window Capture -> Window "Interactive Scrolling - Broadcast Mode", Capture Method "Windows 10
(1903 and up)", and look whether the transparent area shows the scene below or black.

Not provided by design: live streaming, hosting or an internal recorder - use OBS or any
screen recorder.
