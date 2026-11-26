# Integration Audit 003 (after M4: core interaction)

Date: 2026-11-26. Scope: whole codebase with focus on the new gesture family, browser tab
control, configuration migration, threading and the unexplained UI stalls.

**Technical verification: PASSED with documented residual risks.**
**Director verification: PENDING** (physical gestures, real browser and account; consolidated
checklist in [DIRECTOR_ACCEPTANCE_CHECKLIST.md](../milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md)).

## Gesture conflicts, returns and duplicates

| Check | Evidence |
|---|---|
| Four directions distinguishable, diagonals rejected | `test_all_four_directions_with_either_hand` (both hands), `test_diagonal_movements_are_rejected_not_guessed` |
| Return movements | settle-based return phase; recordings: 13 returns suppressed, 0 opposite swipes at balanced/low/high and mirrored; regression test for the multi-part overshooting return (found here) |
| One gesture, one action | engine emits at most one event per frame and per stroke; dispatcher one-at-a-time; extension ignores repeated command ids (new for tab commands) |
| Static vs dynamic | half-heart/stop candidates cancelled during swipes; 0.4 s global cooldown |
| Tracking loss | cancels the stroke (`test_tracking_loss_mid_stroke_cancels_without_event`) |
| Old gestures | open-hand sweeps and thumbs up are negatives now: 0 events in 7 recorded segments |

## Browser context and extension security

* Tab commands only to a browser reporting OS focus; focus read from `window.focused` at
  every report (a restarted service worker cannot report stale focus).
* Tab navigation needs no new permission; tab titles/URLs are not readable by the extension
  (verified in headless Edge: `url` is undefined for non-YouTube tabs).
* Command set grew from four to six fixed commands; schema rejects negative or non-integer tab
  indices; tab commands never carry page data (`test_tab_commands_never_carry_page_data`).
* Protocol 1 extensions are accepted for Shorts but refused for tabs (outdated warning).

## Configuration migration

Version 1 settings are migrated per field (renamed thresholds keep values, removed
application-switching actions take the tab defaults, values at an old default take the new
default) and the original file is kept as `settings.json.v1-backup`
(`test_version_1_settings_are_migrated_without_losing_user_choices`). Analytics rows written
by 0.2 are kept; the identical vertical swipes are merged in reports, thumbs-up and sweeps are
shown with "(v0.2)" labels.

## Threads

New threads since 0.2 are listed in ARCHITECTURE.md. Each owns its resources; shared state is
lock-protected (activity tracker, eye analytics, co-op host) or exchanged through mailboxes and
queued signals. Shutdown joins every worker (stability sessions: 0.28 s, no worker threads left).

## UI stalls (222 ms in M1, 357 ms in M2)

Instrumentation added (`core/stall_monitor.py`, `ui/stall_probe.py`): a watchdog records every
UI stall over 150 ms with the running UI handler, the UI thread's stack, overlapping garbage
collection and pauses of the capture and processing threads; in diagnostic runs a Qt event
filter adds the event being delivered and whether the event loop was asleep.

| Run (10 min, Gesture test, 1280x720, production services) | Stalls | Attribution |
|---|---|---|
| Session A | 350 ms at startup; 266 ms at t=59 s; 363 ms at t=502 s | startup: inside `window.show()`; runtime: no application handler running, UI thread in Qt's native event loop, GC 0 ms, capture and processing threads **not** paused |
| Session B (with Qt event probe) | 264 ms at startup only | `ShowToParent` to the main window (first show) |

Findings:

1. **Fixed (A3-1)**: `ResourceMonitor.sample()` enumerated every process and thread of the
   system (psutil `num_threads()`), costing ~13 ms on the UI thread every second and more under
   load. The window never displays it. Now opt-in (regression test). After the fix the
   diagnostics handler takes 0.12 ms mean, 2 ms max (before: 6.5 ms mean, 36 ms max).
2. **Explained**: a one-time ~260-350 ms stall when the main window is first shown (native
   window creation and first layout), before the camera starts. Acceptable.
3. **Narrowed, not resolved**: two runtime stalls in 20 minutes, both while the UI thread was
   inside Qt's native event processing with no application code running, no garbage
   collection, and both worker threads continuing normally (so neither the whole process nor
   the GIL was blocked). They did not coincide with scripted resizes, mirror toggles or camera
   restarts. The remaining candidates are inside Qt / Windows message handling (for example
   window-manager or accessibility messages); the Qt probe did not catch one in its session,
   so the delivered event is not known yet. Residual risk: rare (0-2 per 10 minutes), the
   gesture pipeline and action execution continue unaffected (they do not run on the UI
   thread), only the preview freezes briefly. The monitor stays in the product and logs any
   stall over 250 ms with its attribution.

Every UI handler measured below 11 ms max (video paint 2.5 ms mean, frame update 0.25 ms).

## Dropped frames

483 (M2 session, with concurrent load) -> 404 (session A) -> 228 (session B) over 10 minutes,
i.e. 1.3 % of ~18,000 captured frames at most; processing keeps up on average (29.6-30.0 FPS
for 30.8 FPS capture) and drops occur when inference occasionally exceeds the frame interval.
Drops are by design (latest-value mailbox) and bound latency.

## Other defects found and fixed in this phase

| ID | Severity | Finding | Fix |
|---|---|---|---|
| A3-2 | Medium | Return of a swipe in several parts started a false opposite swipe at HIGH sensitivity | return phase requires a pause near the start; regression test |
| A3-3 | Low | Browser test raced the extension's reconnect timer (failed once in the baseline) | waits for the attempt |
| A3-4 | Low | UI test read a panel before its queued update | waits for the update |
| A3-5 | Low | Reading a fresh analytics store reported "no such table" until the first write (pre-existing) | reads create the schema; regression test |

## Regression

`pytest --hardware`: 445 passed, 1 skipped at the end of M4 (baseline 392 + 1 flaky); all
earlier tests retained except those describing superseded behaviour (thumbs up, open-hand
sweeps, academic actions), which were rewritten for the replacing gestures as recorded in the
commit messages.

## Remaining risks

| Severity | Risk |
|---|---|
| High (verification) | Left/right index swipes and the half-heart have no real recordings; Director recordings and checklist pending |
| Medium | Back-and-forth ambiguity: a fast preparation movement made while already pointing could switch to the opposite tab (GESTURES.md) |
| Medium | Stop pose unreliable when the open hand is far from the camera (tracking) |
| Low | Rare runtime UI stalls inside Qt's event loop (instrumented, not resolved) |
