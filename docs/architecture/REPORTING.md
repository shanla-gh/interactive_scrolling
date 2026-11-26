# Reporting, sessions and Anti-Doomscroll

Code: `src/interactive_scrolling/wellbeing/` (pure logic), raw queries in
`storage/analytics.py`, wiring in `services.py`, UI in `ui/report_panels.py`.

## What is measured

| Term | Definition |
|---|---|
| Shorts page open | A connected browser's active tab in its last focused window is a visible YouTube Shorts page (`shorts_session` events, since 0.2). Shown as "Shorts tab visible" in older builds. |
| **Active scrolling** | Additionally: that browser window has the operating-system focus, the Short has loaded, and the video is **playing**. Sampled once per second on the services' activity thread from the extension's reported state. |
| Scrolling session | Active intervals separated by gaps of at most **2 minutes**. Duration = active time (gaps excluded). |
| Successful navigation | A next/previous action whose effect the page confirmed (the Short id changed). |
| Estimated viewing time | Not part of these reports; it is the optional passive eye-analytics estimate (separate report). |

Active scrolling deliberately does not assume attention: a playing Short in the foreground is
counted whether or not anybody looks at it.

Persistence: `scroll_active_started` / `scroll_active_ended` events plus a `scroll_heartbeat`
every 30 s while active. An interval left open by a crash or power loss ends at that run's last
event (at most 30 s lost); an interval open in the running session runs until now. Intervals
are split at local midnight, so a session crossing midnight contributes to both days. After a
restart within the 2-minute gap the current session continues (`ActivityTracker.restore`).

No URLs, titles, video ids, account data, landmarks or images are stored. Statistics can be
switched off (nothing is recorded) and deleted (all rows removed, database vacuumed).

## Daily Activity Report ("Today" tab)

Scrolling time, number of sessions, longest session, current session; confirmed (successful)
next/previous Shorts, tab right/left, likes, pause/resume; and, separately, all recognized
gestures and the rejected / failed / unknown outcomes. Only today; no comparisons with other
days. The report is computed on the activity thread every 2 s and only displayed by the UI.

## Gesture Performance Report ("Performance" tab)

Confirmed gestures, dispatched actions, successful / failed / rejected / unknown / not executed
outcomes, action latency (dispatch to confirmation, successful actions, mean and p95 with n),
live tracking FPS, capture-to-result latency, gesture recognition time and the gesture
distribution.

**Execution success = successful actions / dispatched actions.** Dispatched means the action
passed every safety check and was sent to the browser. It measures how reliably requested
actions take effect, **not** how accurately gestures are recognized; recognition accuracy needs
labelled recordings (`scripts/evaluate_gestures.py`). Metrics without data show "-" or
"unavailable", never a made-up value.

## Doomscroll Index

```
D = today's active scrolling (min)    B = daily budget (min, default 60)
L = today's longest session (min)     S = session limit (min, default 20)

budget_part  = min(1, D / (2 B))
session_part = min(1, L / (2 S))
index        = round(100 * (0.7 * budget_part + 0.3 * session_part))
```

Within both goals the index stays at or below 50; it reaches 100 only at twice both. No
scrolling today gives 0; with statistics off it is "unavailable". Labels (playful / plain):
0-19 Barely scrolled / Low, 20-39 Casual scroller / Moderate, 40-59 Getting comfortable /
Elevated, 60-79 Deep in the feed / High, 80-100 Certified clown / Very high. Lower is better;
nothing rewards a higher score. It is an entertainment and self-awareness number, not a
medical or psychological assessment. Boundary tests: `tests/unit/test_wellbeing.py`.

## Anti-Doomscroll (optional, off by default)

* Reality Check every N minutes of a session (default 15), session-limit and daily-budget
  notices (tray notification and a banner on the video), optional break suggestion.
* **Pause gesture scrolling**: a button on the Today tab pauses next/previous-Short gestures
  until the user resumes. With "pause when a limit is reached" the pause starts automatically;
  resuming overrides it for that limit, and an automatic session pause ends with the session.
  Likes, playback, tab switching, mouse and keyboard are never affected and no application is
  opened or closed. Implemented as a dispatcher admission check, so the refusal appears in the
  gesture history ("rejected - gesture scrolling paused: session limit reached").
* Grayscale mode and intentional scrolling delays (optional in the brief) are not implemented.
* Eye tracking is never used here.
