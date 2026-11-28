# Engineering Brief 008 - checkpoint report (product redesign, live preview, Doomscroll Together)

Statuses follow `docs/ENGINEERING_CONVENTIONS.md`; "technical" = implemented and verified by
automated tests and rendered screenshots, human verification pending. Screenshots (not
committed): `E:\interactive_scrolling\screenshots\brief008\` - `before\` (0.7.0b1 UI) and
`after\` (three laptop configurations; synthetic camera scene), `live\` (real app with a real
live Short), `clown\` (synthetic face), `window_capture\`, `preview_proto\`.

| CP | Status | Evidence / remaining |
|---|---|---|
| Baseline | COMPLETED | f874768 / 0.7.0b1: 699 passed, 6 skipped; gesture gate no regression x5 |
| 35.1 UI audit | COMPLETED | before screenshots x3 configurations; findings in Audit 010 |
| 35.2 Visual language | COMPLETED (technical) | `ui/theme.py`; Director judgement pending |
| 35.3 Responsive layout | COMPLETED (technical) | 1366x768 100 %, 1920x1080 125 %/150 % renders; camera refit on stage resize (defect found and fixed) |
| 36.1 Minimal top bar | COMPLETED | test_top_bar_holds_only_the_essentials |
| 36.2 Camera settings | COMPLETED | dialog; fps request tested; one pipeline owns the camera (unchanged) |
| 36.3 Gesture-control accessibility | COMPLETED | strip under the camera; Ctrl+Alt+D, Stop, tray unchanged; mode change never enables Live (test) |
| 37.1 Feasibility | COMPLETED | A tab capture prototyped on real YouTube; C PrintWindow prototyped; B (WGC) not run - see LIVE_PREVIEW.md |
| 37.2 Architecture | COMPLETED | tab capture -> offscreen worker -> loopback `/preview`; `docs/architecture/LIVE_PREVIEW.md` |
| 37.3 Normal Mode integration | COMPLETED (technical) | Now playing column; real app screenshot with a live Short; hide = capture stops |
| 37.4 Focus and targeting | COMPLETED (technical) | preview-tab control only with an authorized preview and the app active; tests (fixture + real site) |
| 37.5 Audio | COMPLETED (by design) / human check pending | no audio captured; tab audio unchanged per API; listening check by the Director |
| 37.6 Acceptance | COMPLETED (automated) / human pending | real YouTube: next/previous/pause from the app, other tab, minimized, leave Shorts, stop, revoke |
| 38.1 Remove tab-heavy UI | COMPLETED | five tabs removed; content in dialogs/console |
| 38.2 Browser section | COMPLETED | session panel; pairing dialog |
| 38.3 Doomscroll Together prominence | COMPLETED (technical) | right column; host/guest flows rendered with two real sessions |
| 38.4 Daily summary | COMPLETED | three numbers + Report |
| 39.1 Reconcile Co-op | COMPLETED | review findings fixed (see 39.6) |
| 39.2-39.5 Lite experience | COMPLETED (single machine) | loopback incl. separate process; **no two-computer test** |
| 39.6 Security review | COMPLETED | private-network listening/peer filter, expiry, close codes, rate limit, transport documented (not encrypted) |
| 39.7 Latency feedback | COMPLETED | round trip, confirmation time, reconnect state in the console |
| 39.8 Testing | COMPLETED (loopback) / BLOCKED (two computers) | 35 Co-op tests; procedure in BRIEF_008_VALIDATION.md |
| 40.1-40.3 Developer console | COMPLETED | console; state persisted; Copy diagnostics unchanged (no images, URLs, codes, tokens) |
| 41.1-41.4 Clown makeup | COMPLETED (technical) | wig/mask removed; makeup stages; strength slider; synthetic renders; tests |
| 41.5 Visual validation | BLOCKED - real person needed | synthetic face only |
| 42.1 Transparent background discoverability | COMPLETED | Broadcast settings (More, overlay Settings button, menu, tray) |
| 42.2 Segmentation behaviour | COMPLETED | privacy fallback unchanged |
| 42.3 Combined creator experience | COMPLETED (technical) | independent options test; models only when needed (unchanged scheduling) |
| 43.1 Live YouTube failures | COMPLETED | cause found: test harness (Edge first-run tabs, consent URL variant); test fixed |
| 43.2 Background frame drops | see PERFORMANCE_008.md | |
| 43.3 UI responsiveness | see PERFORMANCE_008.md | |
| 43.4 Performance | see PERFORMANCE_008.md | |
| 44 Gesture protection | COMPLETED | engine untouched; gate no regression x5 (start and end) |
