# Roadmap

## Product vision (Director-approved, 2026-11-26)

Interactive Scrolling is a lightweight, privacy-preserving, webcam-powered desktop application
combining hands-free computer interaction, social media interaction, digital wellbeing,
entertaining computer vision visualization, personal behaviour analytics and content creation.
All camera processing stays on the user's computer.

## Milestones

| Phase | Scope | Status |
|---|---|---|
| **M0 - Project Foundation** | Repository, reproducible environment, architecture, testing and CI, documentation | Completed |
| **M1 - Computer Vision & Live Visualization** | Webcam acquisition, hand tracking, skeleton overlay, motion engine, desktop UI, stability and performance | Completed (Director verified) |
| **Integration Audit 001** | Whole-codebase audit after M0/M1 | Passed |
| **M2 - Gesture Recognition Engine** | Finger swipes up/down, hand sweeps left/right, thumbs up, stop gesture; temporal state machine and false-positive prevention; configuration, presets and persistence; gesture visualization and history; safe activation (Tracking Only / Gesture Test / Live Control) | See [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| **M3 - YouTube Shorts Integration** | Browser integration, Shorts context validation, next/previous, like, play/pause, control UI, minimal local event logging and daily statistics | See [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| **Integration Audit 002** | Whole-codebase audit after M2/M3 | See [docs/audits](docs/audits) |
| **M4 - Windows Integration & Academic Comeback / Relapse** | Right-hand sweep switches to a designated study application, left-hand sweep returns to the designated social media application; context-aware execution | Not started |
| **M5 - Desktop UX & Content Creator Mode** | Three application modes (below), tray operation, compact always-on-top overlay for OBS capture | Not started |
| **M6 - Public Release** | Packaging, licensing compliance for bundled components, release documentation | Not started |

Each milestone starts only after the Director approves a new engineering brief.

## Approved control system

Hand gestures are the primary and currently exclusive control input.

| Gesture | Action |
|---|---|
| Index finger swipe down | Next Short |
| Index finger swipe up | Previous Short |
| Thumbs up | Like the current Short |
| Stop gesture (open palm hold) | Pause / resume playback |
| Right hand sweep | Switch to the designated study application (M4) |
| Left hand sweep | Return to the designated social media application (M4) |

Also approved: gesture customization, sensitivity adjustment, calibration, context-aware
execution and an emergency control disable mechanism.

## Approved future scope (not yet scheduled into a milestone)

These features are approved by the Director but have no implementation brief yet. They must
not be implemented before a brief assigns them.

* **Three application modes** - *Developer Mode* (full dashboard, skeleton, vectors,
  telemetry, gesture history, diagnostics), *Content Creator Mode* (compact, customizable,
  always-on-top webcam overlay for OBS) and *Background Mode* (system tray with optional
  minimal status). Planned for M5.
* **Anti-Doomscroll** (all optional, transparent and user-controlled): configurable scrolling
  session limits, Academic Comeback (manual and automatic), Academic Relapse tracking, Reality
  Check notifications, Study Protection, optional grayscale mode, optional intentional
  scrolling delays, daily scrolling budget, Doomscroll Index.
* **Eye tracking as passive analytics only**: estimated screen-viewing and looking-away
  duration, continuous viewing duration, broad gaze direction, blink statistics, tracking
  quality, optional gaze heatmaps, comparison of social media and study sessions. Explicitly
  excluded: eye- or blink-controlled actions, gaze-triggered playback, eye-controlled
  application switching, head-gesture control, and any inference of addiction, mental state,
  attention, dopamine levels or medical conditions.
* **Progressive Clown Transformation** (signature feature, optional and configurable): the
  webcam preview progressively turns the user into a realistic clown with continuous scrolling
  duration (stage 0 normal, 1 red nose, 2 additional makeup, 3 full transformation), tracking
  facial geometry in real time. No facial identity recognition; face landmarks only for clown
  rendering and eye analytics. Other face filters are out of scope.
* **Reporting**: Daily Activity Report, Session Statistics, Gesture History, Gesture
  Performance Report, Doomscroll / Academic Comeback / Academic Relapse counters, Doomscroll
  Index, Daily and Session Doomscroll Wrapped (high priority, with 9:16 PNG export for social
  media), local data storage. Weekly and monthly analytics and historical comparisons are
  deferred. M3 provides only the minimal event and persistence foundation.
