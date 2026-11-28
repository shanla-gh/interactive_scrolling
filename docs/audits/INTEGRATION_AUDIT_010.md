# Integration Audit 010 (product redesign, Brief 008)

Date: 2026-11-28. Scope: the whole application after the Normal Mode redesign, the live Shorts
preview (extension 0.5.0, protocol 3), Doomscroll Together hardening and UI, Broadcast
settings, the clown makeup redesign and the Background Mode timer opt-out. Gesture
recognition is unchanged.

| Verdict | |
|---|---|
| Technical verification | **passed**: 755 tests (0 failed, 0 expected failures, 6 skipped = webcam/live, run separately), three consecutive identical runs; hardware 5/5; browser fixture tests (extension in Edge) 21/21 incl. 5 live-preview tests; packaged 0.8.0b1 self-test PASS in a fresh data folder; gesture gate "no regression" in all five frozen configurations (start and end of the brief) |
| Real YouTube | live test after the harness fix 19 of 20 runs passed (one first-navigation failure without diagnostics); before the fix 25 of 30; preview prototype on the real site in 6 runs, all scenarios as expected |
| Visual review | rendered screenshots at 1366x768 100 %, 1920x1080 125 % and 150 % (synthetic camera scene); real app window with a real live Short; clown stages on a synthetic face |
| Not verified | two physical computers (Doomscroll Together), real-person clown and transparency appearance, Chrome, audio by ear, second monitor, OBS Windows Graphics Capture |
| Director validation | **pending** (`docs/milestones/BRIEF_008_VALIDATION.md`) |

## Areas reviewed

| Area | Check | Evidence |
|---|---|---|
| Main window architecture | one runtime, dialogs created once, console/Now playing state persisted, refit on stage resize | `test_normal_mode_ui.py`, screenshots |
| Minimal top bar | only name, version, camera state, Camera settings, Normal/Broadcast, More, Start/Stop | `test_top_bar_holds_only_the_essentials` |
| Camera settings | device/resolution/fps/scan locked while running; one pipeline owns the camera | existing camera tests, `test_camera_settings_frame_rate_is_requested` |
| Gesture-control safety | strip always visible; Live in red; Stop and Ctrl+Alt+D unchanged; presentation mode never changes control mode | `test_gesture_control_stays_visible_and_safe`, `test_control_ui.py` |
| Live preview / local capture | frames only from the chosen tab, cropped, size-limited, latest-only; stops when leaving Shorts; ends on tab close / app stop | `test_live_preview.py` (15), `test_live_preview_browser.py` (5), real-site prototype |
| Browser permissions | `tabCapture`, `offscreen` added (no other change); capture needs the user's popup click; test switch used only in tests | manifest, LIVE_PREVIEW.md |
| Preview-control authorization | tab id only for the authorized preview tab, only while the app is active; tab switching never; revoked on stop | controller tests, fixture + real site |
| Browser focus | ordinary policy unchanged outside a preview session | existing bridge tests (unchanged expectations) |
| Video privacy | no storage; loopback; pairing code; hidden state clears the picture | tests above |
| Audio | not captured (API option); tab audio unaffected per design; not checked by ear | LIVE_PREVIEW.md |
| Doomscroll Together / authentication | private peers only, private bind, expiry/renewal, close codes, rate limit, reconnect without re-approval, no reconnect after deliberate close, remove | `test_coop.py` (14), `test_coop_brief008.py` (22), `test_coop_ui.py` |
| Guest permissions | next/previous/pause only (unchanged; likes and tabs refused) | `test_coop.py` |
| Shared cooldown | unchanged 1 s; not reduced (no new concurrency evidence) | `test_coop.py` |
| Developer console | history, log, recognition, performance, connection details; Copy diagnostics unchanged (no images, URLs, codes, tokens) | screenshots 02/02b, diagnostics tests |
| Transparent background | one click in Broadcast settings; fallback unchanged | `test_transparent_background_is_one_click_away_in_broadcast_settings`, compositing tests |
| Natural clown makeup | no wig/mask; eyes, brows, lips, hair spared; bounded strength; texture through lips | `test_face_features.py` (3 new tests), synthetic renders |
| Broadcast / Background Mode | settings reachable from 4 places; tray entries; timer opt-out in Background | UI tests, PERFORMANCE_008.md |
| Optional model scheduling | unchanged (segmentation only with the transparent overlay visible; face only with clown/eye analytics) | existing tests |
| Analytics and reporting | unchanged; Today numbers read the existing report | tests |
| Configuration migration | new fields (`console_expanded`, `show_now_playing`, `clown_makeup_opacity`) load with defaults from older files; hand box/label defaults off | settings tests |
| Packaging | 0.8.0b1 built (157 MB zip), extension 0.5.0 inside, self-test PASS | `docs/RELEASE.md` |
| Camera lifecycle, threads, cleanup | restarts ok in all sessions; no worker threads after close; preview timer and dialogs closed on exit | stability reports |
| Performance | PERFORMANCE_008.md | |

## Defects found and fixed in this brief

| Defect | Severity | Fix / test |
|---|---|---|
| Live YouTube failures attributed to YouTube in Brief 007 were the test harness (fresh Edge profile's first-run tabs took the foreground mid-action; post-consent `/shorts?cbrd=1` URL not matched) | Medium | test closes other tabs, matches `/shorts`; diagnostics on failure |
| Offscreen preview page throttled to about 1 frame/s with 1 s delay | High (prototype) | encoding moved to a worker (25-30 fps) |
| Tab capture letterboxes the tab; crop was distorted | Medium (prototype) | letterbox-aware crop; fixture test checks the 9:16 shape |
| Gesture strip overlapped the camera at 150 % with the console open | Medium | refit on every stage resize |
| Broadcast settings taller than a 1080 p screen at 150 % | Medium | two columns |
| Guest auto-reconnected after the Host closed it for invalid messages | High (security) | reconnect only without a close frame; `test_forged_or_replayed_messages_close_the_connection` |
| "Remove" reused the refusal path and message | Low | `remove_guest()`; test |
| Hard edges around eyes/brows in the stage 3 makeup | Medium (visual) | feathered cut-outs |
| Host listened on all interfaces and accepted any peer address | Medium (exposure) | private bind choice and peer filter; tests |
| Session codes never expired | Low | 15-minute expiry, renewal; test |

## Development failures

* Protocol version 3: two tests expected version 2 in the welcome message / as the first
  invalid version; updated (intent unchanged).
* UI wording/placement: camera state text, browser state moved to the session panel, the
  invitation code shown on its own; three tests updated accordingly.
* Running a downloaded Windows Graphics Capture binding was blocked by the session's permission
  policy; the package was deleted and approach B was evaluated from documentation instead.
* A first PrintWindow attempt captured a small helper window; corrected to the main window.
* A measurement-run overlap: a short check script ran during one "before" Background run; both
  before/after runs were repeated undisturbed.

## Open risks

| Severity | Risk |
|---|---|
| High (verification) | Doomscroll Together not tested on two computers (Wi-Fi, firewall prompt, VPN) |
| High (verification) | No real-person check of the clown makeup and the transparent background |
| Medium | Live preview needs the popup click each session and an extension reload after updating |
| Medium | One undiagnosed first-navigation failure in 20 live runs |
| Medium | UI stalls 110-180 ms on window resize in the new layout; one unexplained 393 ms stall |
| Medium | Chrome, second monitor and OBS WGC untested; audio not checked by ear |
| Medium | Accidental swipes with any hand shape; low-frame-rate limits (unchanged engine) |
| Low | Messages between Together participants are authenticated, not encrypted (documented) |
