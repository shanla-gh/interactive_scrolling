# Minimal Co-op Doomscroll

Code: `src/interactive_scrolling/integrations/coop/` (protocol, host, guest), `services.py`
(host/join/leave), `ui/coop_panel.py`. Tests: `tests/integration/test_coop.py`,
`tests/integration/test_coop_ui.py`.

## Model

* One **Host**, one **Guest**. The Host's YouTube Shorts tab is the only feed; both watch it
  through an external screen-sharing application (for example Discord). This project sends no
  video, camera images, audio or browsing data.
* Each computer runs its own gesture engine. The Guest's confirmed **next / previous / pause**
  gestures are sent as small signed control events; the Host executes them in its own browser
  through its own action dispatcher.
* Likes and tab switching are never shared: a Guest cannot like with the Host's account or
  touch the Host's other tabs, applications or settings. The Host keeps its own full control.

## Connection and security

| Item | Implementation |
|---|---|
| Transport | WebSocket on TCP port 47816 (configurable), opened by the Host only while a session exists; one Guest at a time (others: close 1013) |
| Network | Same local network, or a trusted private network / VPN the users already have (for example a mesh VPN). No internet relay, matchmaking, accounts or friend lists; a code alone does not make the Host reachable from the internet. Windows may ask the Host to allow the app through the firewall for private networks. |
| Session code | 80 random bits, `XXXX-XXXX-XXXX-XXXX`, new for every session, shared out of band |
| Authentication | Mutual HMAC-SHA256 challenge-response over fresh nonces; the code never travels. Five wrong codes end the session (the Host must create a new one). |
| Messages | Session key derived from the code and both nonces; every message is HMAC-signed and carries a strictly increasing sequence number (forged, modified and replayed messages are rejected; five invalid messages close the connection); 2 KB limit; strict schema |
| Approval | A Guest controls nothing until the Host clicks *Approve guest*; *Guest may control my feed* can be switched off at any time; *End session* closes it |
| Allowed requests | `next_short`, `previous_short`, `toggle_playback` only |
| Not encrypted | The events contain nothing secret ("next Short"); confidentiality was not a goal. Anyone on the network can see that a session exists and which actions are requested. |

## Shared execution

* Guest requests enter the Host's dispatcher like local gestures: they need **Live control**
  on the Host, a valid Shorts context, no action already running, and are refused after an
  emergency disable (Ctrl+Alt+D) or in Tracking only / Gesture test mode.
* **First accepted wins**: while a Guest shares control, a 1 s shared cooldown (dispatcher
  admission check) refuses the second of two near-simultaneous navigation gestures; the
  dispatcher's one-action-at-a-time rule applies as well, so both players doing the same
  gesture never skip two Shorts.
* **Duplicates and stale events**: request ids are remembered (500); a request older than 1.5 s
  (Guest clock corrected by the smallest observed offset) is refused.
* **Attribution**: every final outcome is recorded with the participant ("Sam -> Next Short
  -> Success"), counted per participant and sent to the Guest, so both see who controlled the
  feed and what actually happened.
* While joined as Guest, the Guest's local browser is not controlled; leaving restores it.

## Verification status

Automated (loopback, `tests/integration/test_coop.py`): authentication, wrong codes, the
five-attempt lockout, approval, refused likes/tabs (including a hand-crafted signed request),
simultaneous gestures, shared cooldown, duplicates, stale requests, forged/replayed messages,
unauthenticated clients, second guest, host shutdown, host-side disable, emergency disable,
attribution, and one test with the Guest in a **separate operating-system process**.

Not verified: two physical computers on a real network (Wi-Fi latency, firewall prompts,
router client isolation). This is in the Director checklist.

## Duo Wrapped

The Host can export a session card (Co-op tab, *Duo Wrapped...*) with the session duration,
shared next/previous actions and successful actions per participant, using the same 1080x1920
renderer as Doomscroll Wrapped.
