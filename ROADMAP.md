# Roadmap

## Product vision (Director-approved, revised 2026-11-26 in Engineering Brief 003)

Interactive Scrolling is a lightweight, free and open-source webcam application for ordinary
Windows laptops. It combines hands-free browser interaction, YouTube Shorts control,
entertaining computer-vision visualization, personal digital-wellbeing tools, simple daily
usage reports, social-media content creation and a minimal two-person co-op mode. All camera
processing stays on the user's computer; only pretrained local models and deterministic rules
are used (no cloud inference, no language models).

## Control system

Hand gestures are the only control input. All gestures work with either hand.

| Gesture | Default action |
|---|---|
| Index finger moves up | Next YouTube Short (touchscreen direction, Brief 004) |
| Index finger moves down | Previous YouTube Short |
| Index finger swipe right (your right) | Next browser tab (to the right) |
| Index finger swipe left (your left) | Previous browser tab (to the left) |
| Single-hand half-heart, held | Like the current Short |
| Open-palm stop pose, held | Pause / resume |

The four swipes are one gesture family: the index fingertip of a pointing hand moving in one
direction - a finger flick, a wrist turn or a small hand movement. Tab navigation stays inside the active window of the
supported browser; it never switches other Windows applications. Shorts actions (next,
previous, like, pause) stay restricted to a valid Shorts tab.

Eye and face tracking never control anything.

## Milestones

| Phase | Scope | Status |
|---|---|---|
| **M0** Project Foundation | Repository, environment, architecture, tests, CI, docs | Completed |
| **M1** Computer Vision & Live Visualization | Webcam, hand tracking, skeleton, motion engine, desktop UI | Completed (Director verified) |
| **M2** Gesture Recognition Engine | Temporal recognizers, presets, safe activation modes | Technically verified; Director verification pending; partly superseded by M4 |
| **M3** YouTube Shorts Integration | Companion extension, loopback bridge, confirmed actions, local events | Technically verified; Director verification pending |
| **M4** Gesture Refinement & Browser Tab Control | Four-direction index-finger swipes, half-heart like, calibration settings, tab navigation, gesture benchmark | Brief 003 |
| **M5** Three UI Modes | Developer Mode, Content Creator overlay (incl. transparent background), Background (tray) Mode, visual customization, shared runtime | Brief 003 |
| **M6** Anti-Doomscroll & Daily Reporting | Session accounting, Daily Activity Report, Gesture Performance Report, limits and Reality Checks, Doomscroll Index | Brief 003 |
| **M7** Progressive Clown Transformation | Local face landmarks, progressive clown AR effect | Brief 003 |
| **M8** Passive Eye Analytics | Screen-facing / looking-away / unknown estimation, blinks, Visual Behavior Report | Brief 003 |
| **M9** Doomscroll Wrapped | Daily and session summary, 1080x1920 PNG export | Brief 003 |
| **M10** Minimal Co-op Doomscroll | Two-person host/guest gesture control of one Shorts feed over a private LAN session | Brief 003 |
| **M11** Packaging & Release Candidate | Windows distribution, setup guide, clean-environment validation | Brief 003 |
| **Beta stabilization** (Brief 004) | Root-cause analysis of the Director's test, gesture engine rework, diagnostics, Practice and Quick Calibration, browser reliability, benchmark and Audit 006 | Implemented; Director beta validation pending |
| **Motion engine 2.0 and real-time** (Brief 009, M45-M53) | Full-app mode benchmark (Broadcast complaint investigated), faster downward decisions at >= 22 fps, repaint loop fixed, camera limits measured, driver frame times recorded, eye and gaze overlay, gaze calibration tool, Wrapped eye line | Implemented; Broadcast feel, gaze accuracy and independent recognition data need the Director |
| **Product redesign** (Brief 008, M35-M44) | Normal Mode redesign (top bar, Now playing, session panel, diagnostics console), live Shorts preview via tab capture with preview-tab control, Doomscroll Together hardening and UI, Broadcast settings, natural clown makeup | Implemented; preview, visual and two-computer checks need the Director |
| **Product experience** (Brief 007, M26-M34) | Baseline gate, clearer status and layout, Broadcast Mode status/positioning/smoothing, transparency fill, first-use guide, endurance tooling | Implemented; visual and creator usability need the Director |
| **Pose-independent motion** (Brief 006, M19-M25) | Duplicate-hand fix, any-hand-shape engine, tracking-gap rules, trajectory overlay, frame-timing diagnostics | Implemented; whole-hand swipes and accidental swipes need the Director's judgement and a new held-out recording |
| **Motion-first gestures** (Brief 005, M12-M18) | Shared motion engine, fist swipes (experimental), downward-motion analysis, per-direction calibration, motion visualization | Implemented; fist control and downward comfort need the Director's validation and session-5 recordings |

Integration audits follow M4 (003), M6 (004), M10 (005), the beta stabilization (006), the motion-first work (007) and pose-independent motion (008), product experience (009), the product redesign (010) and Motion Engine 2.0 (011).

**Next (needs the Director):** beta validation (`docs/milestones/BRIEF_009_VALIDATION.md`) and
the session-5 recordings with each hand (about 3 minutes each); a decision on finger vs fist
control; then tuning of left/right swipes, the half-heart and
the stop pose on real data, and the 30-minute false-trigger measurement. No new features until
the core interaction is accepted. Status of each checkpoint is
tracked in [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Feature definitions (Brief 003)

* **Three UI presentation modes** - *Developer Mode* (full dashboard), *Content Creator Mode*
  (compact always-on-top overlay for OBS, optional transparent background), *Background Mode*
  (system tray with camera / Live Control status and emergency disable). Presentation modes
  are independent of the execution safety states *Tracking only*, *Gesture test* and
  *Live control*.
* **Transparent background** - optional person segmentation for the Content Creator overlay
  only. It is a presentation operation: the hand tracker always receives the original frame.
  No other background or camera effects (blur, colour replacement, silhouettes) are in scope.
* **Simple reporting** - today's scrolling duration, number and longest scrolling sessions,
  next/previous, tab-switch, like and pause/resume actions, confirmed gestures, action
  outcomes and gesture performance. No weekly, monthly or historical comparisons.
* **Anti-Doomscroll** (optional, reversible) - session limit, daily budget, Reality Check
  notifications, break reminders, user-controlled suspension of gesture scrolling.
* **Doomscroll Index** - a documented deterministic 0-100 score from scrolling time relative
  to the user's own goals. Entertainment and self-awareness only, not a medical assessment.
* **Progressive Clown Transformation** - the only AR face effect: red nose, partial and full
  clown makeup as the current scrolling session grows (default 10 / 20 / 30 minutes).
* **Passive eye analytics** - estimated screen-facing, looking-away and unknown time, blinks,
  tracking quality. Never used for control or enforcement; no attention, mental-state or
  addiction inference.
* **Doomscroll Wrapped** - a daily or session summary card exported as a 1080x1920 PNG.
* **Minimal Co-op Doomscroll** - one Host and one Guest; the Host's Shorts feed is the only
  feed (watched together through an existing screen-sharing app). Only small authenticated
  control events (next, previous, pause) travel between the two computers.

## Superseded by Brief 003

* Academic Comeback / Academic Relapse (switching to a study application, study protection,
  social-versus-study comparisons) - removed from the product.
* Windows application switching (Alt+Tab style) - not part of the product.
* Open-hand horizontal sweeps - replaced by index-finger swipes left/right.
* Thumbs-up like - replaced by the single-hand half-heart.
* Optional gaze heatmaps, weekly/monthly analytics - not required for the release candidate.
* Other face filters and camera effects - out of scope.
