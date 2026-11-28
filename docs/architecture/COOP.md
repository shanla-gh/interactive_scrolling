# Doomscroll Together (Co-op Lite)

Product name since Brief 008: **Doomscroll Together**; internal name Co-op Lite. User guide:
`docs/guides/DOOMSCROLL_TOGETHER.md`.

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
| Listening address (Brief 008) | The Host chooses the private address to listen on (local network, a private VPN such as Tailscale in 100.64.0.0/10, or all private networks); a public address is refused. Every incoming connection whose peer address is not private (RFC 1918, 100.64.0.0/10, link-local, loopback) is closed with 4005 before the handshake, so a forwarded router port does not expose the session. |
| Invitation (Brief 008) | Address, port and code as one text to copy; the Guest pastes it whole. The code expires after 15 minutes unless a Guest was approved (close 4003); *New code* renews it without ending the session. |
| Refusal reasons (Brief 008) | Close codes 4001 wrong code, 4002 name used by the Host, 4003 expired, 4004 other protocol version, 4005 not a private address, 1013 full, 1001 no session; the Guest shows one sentence for each and for socket errors (refused, timed out, unreachable, invalid address) - never a raw exception. |
| Rate limit (Brief 008) | At most 4 Guest action requests per second ("too many requests"). |
| Reconnection (Brief 008) | If the connection drops without a close frame (network), the Guest retries every 2 s for 30 s; the Host lets a Guest it approved earlier in this session (same name, same code) back in without a new approval. A deliberate close (end, remove, invalid messages, refusal) is never retried. |
| Network | Same local network, or a trusted private network / VPN the users already have (for example a mesh VPN). No internet relay, matchmaking, accounts or friend lists; a code alone does not make the Host reachable from the internet. Windows may ask the Host to allow the app through the firewall for private networks. |
| Session code | 80 random bits, `XXXX-XXXX-XXXX-XXXX`, new for every session, shared out of band |
| Authentication | Mutual HMAC-SHA256 challenge-response over fresh nonces; the code never travels. Five wrong codes end the session (the Host must create a new one). |
| Messages | Session key derived from the code and both nonces; every message is HMAC-signed and carries a strictly increasing sequence number (forged, modified and replayed messages are rejected; five invalid messages close the connection); 2 KB limit; strict schema |
| Approval | A Guest controls nothing until the Host clicks *Let them in*; *My friend can control the feed* can be switched off at any time; *Remove* disconnects the Guest; *End session* closes the session |
| Allowed requests | `next_short`, `previous_short`, `toggle_playback` only |
| Not encrypted | The events contain nothing secret ("next Short"); confidentiality was not a goal. Message signing gives authenticity and integrity, **not** confidentiality: anyone on a local network can see that a session exists and which actions are requested. Over a VPN such as Tailscale the VPN (WireGuard) encrypts the traffic. |
| Trust assumptions | The code reaches the Guest through a channel the two trust (their messenger). Both computers are on a network they trust. The app never creates firewall rules, port forwarding, relays or accounts; Windows may ask the Host once to allow the app on private networks. |

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

Brief 008 (`tests/integration/test_coop_brief008.py`): network classification and refusal of
public peers, public listening address refused, invitation parsing, expiry and renewal,
plain-language refusals (wrong code, name in use, other version, unreachable host), rate
limit, reconnection after a dropped connection without new approval, and no reconnection
after the Host removes the Guest. The UI flows (Host waiting, join request, connected, Guest
waiting/connected, join dialog, error) are rendered with two real sessions on loopback by
`scripts/capture_screenshots.py`.

Not verified: two physical computers on a real network (Wi-Fi latency, firewall prompts,
router client isolation, Tailscale). This is in `docs/milestones/BRIEF_008_VALIDATION.md`.

## Duo Wrapped

The Host can export a session card (Doomscroll Together panel, *Duo Wrapped*) with the session duration,
shared next/previous actions and successful actions per participant, using the same 1080x1920
renderer as Doomscroll Wrapped.
