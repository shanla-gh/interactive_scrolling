# M3 - YouTube Shorts Integration

Status: **technical verification passed; live-website and real-account verification by the
Director pending** ([checklist](M2_M3_DIRECTOR_CHECKLIST.md)). Design, security model and
installation: [YOUTUBE_INTEGRATION.md](../architecture/YOUTUBE_INTEGRATION.md).

| Checkpoint | Technical status | Evidence |
|---|---|---|
| CP 3.1 Browser integration strategy | Done | MV3 extension + loopback WebSocket bridge (ADR-011); permissions `storage` + `https://www.youtube.com/*`; origin pinning, pairing code, strict schema; bridge tests incl. refused origins, wrong code, invalid messages, connection cap |
| CP 3.2 Context awareness | Done | visible Shorts tab in the last focused window with a loaded video; most recently focused browser wins, ties rejected; expected video id per command; stale tab state cleared on navigation (regression test) |
| CP 3.3 Next / previous | Done | confirmed by changed Short id; first Short and broken navigation reported as rejected / failed; one command per gesture, no retries; fixture tests in Edge; live site: next 223-441 ms, previous 202-211 ms |
| CP 3.4 Like | Done (fixture); real account pending | like confirmed by `aria-pressed`; already liked -> no change (never unlikes); signed out -> rejected without clicking (fixture and live site) |
| CP 3.5 Playback | Done | pause/resume confirmed from the video element (fixture and live site, 4-5 ms) |
| CP 3.6 Connection and control UI | Done | YouTube tab (bridge, browser, Shorts context, sign-in, playback, pairing code, setup steps), control bar chip, outcomes in history |
| CP 3.7 Events and daily statistics | Done | SQLite on a writer thread; deduplicated; local-day boundaries with midnight split; opt-out and clear; DB errors never raise; no URLs/titles/video ids/camera data (`tests/unit/test_analytics.py`) |
| CP 3.8 End-to-end | Partly verified | automated: bridge <-> real extension <-> fixture page (CI), controller <-> real extension <-> live YouTube (one full pass); manual: physical gestures controlling the Director's own browser |

## Live-website runs (signed-out, automated profile)

| Run | Result |
|---|---|
| Probe (Edge, headless) | next, next, previous, pause, resume succeeded; like rejected (signed out) |
| Live test run 1 | full pass: next 312 ms, previous 211 ms, pause 4 ms, resume 5 ms, like refused |
| Live test runs 2-3 | no Shorts tab became targetable (Edge startup tabs in the automated profile); one next click ignored by the site and reported as failed |
| Probe (Chrome, headless) | the site ignores navigation clicks until the video has loaded -> readiness now requires a loaded video |

These runs depend on how YouTube treats an automated browser; the Director checklist covers
the real browser.
