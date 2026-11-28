# Doomscroll Together

Scroll one YouTube Shorts feed with a friend. Both of you swipe with your own webcam; one
browser (the Host's) plays the Shorts. You watch the Host's feed through Discord screen sharing
(or any screen-sharing app you already use). Internally this is "Co-op Lite".

**Status (0.8.0b1):** tested on one computer (loopback, separate processes). Two physical
computers have **not** been tested yet - see the Director procedure at the end.

## What travels between the computers

Only small signed messages: "next Short", "previous Short", "pause/resume", their results, who
did them, and pings. **No** video, camera images, audio, browsing history, URLs or files.
The video reaches your friend only through the screen sharing you start yourself.

## Host (your browser plays the feed)

1. Open YouTube Shorts in your connected browser.
2. In **Doomscroll Together** (right side of the window) press **Host**.
3. Choose your name and where your friend joins from:
   * **Local network** - same Wi-Fi or office network.
   * **Private VPN (e.g. Tailscale)** - different places; both computers must be in the same
     private VPN. The app does not install or configure a VPN for you.
   * **All private networks** - listens on every private address of this computer.
4. Press **Copy invitation** and send it to your friend (any messenger). It contains the
   address, the port and a one-time session code. The code expires after 15 minutes if
   nobody joined; **New code** makes a fresh invitation.
5. When your friend connects you see "*Sam* wants to join": press **Let them in** (or
   **Decline**).
6. Start screen sharing of your browser window in Discord.
7. Switch gestures to **Live** (under your camera). Your friend's next / previous / pause
   gestures now control your feed; the panel shows who did the last action.
8. **End session** stops listening at once. **Remove** disconnects your friend. "My friend can
   control the feed" pauses their control without ending the session. The emergency stop
   (**Stop** / Ctrl+Alt+D) still stops all gesture control on your side.

Your friend can never like videos on your account, switch your tabs, control other
applications or read anything from your computer.

## Guest (you watch the Host's feed)

1. Press **Join**, paste the invitation (address, port and code are filled in), choose a name
   different from the Host's and press **Join**.
2. Wait until the Host lets you in ("Playing with *Alex*").
3. Watch the Host's screen share in Discord. Do not open your own YouTube feed - your gestures
   go to the Host's feed.
4. Switch gestures to **Live**. Next, previous and pause go to the Host; likes and tab
   switching are not shared.
5. **Leave** ends your part of the session.

If the connection drops (Wi-Fi hiccup), the app reconnects by itself for up to 30 seconds
without asking the Host again.

## Messages you may see

| Message | What to do |
|---|---|
| The session code is not correct | Paste the invitation again; codes are case-insensitive |
| This invitation has expired | Ask the Host for a new code |
| The host is not available | The Host has no session running, or a firewall on the Host blocks the port |
| The connection timed out | You are not on the same network / not both on the VPN |
| That address cannot be reached from this network | Wrong network or VPN not connected |
| The host only accepts players on a private network or VPN | You connected from a public address; use the same Wi-Fi or a private VPN |
| The host uses a different version | Both update to the same version |
| The session already has a guest | Only two people per session |

## Timing (what the numbers mean)

The diagnostics console (Activity & diagnostics -> Browser and Together) shows:

* **network round trip** - a ping between the two apps;
* **last action confirmed after** - Guest only: from sending a shared action until the Host's
  browser confirmed it (network plus the Host's execution).

Neither includes gesture recognition (measured separately on each computer) nor the delay of
Discord's screen sharing, which the app cannot measure. They are not "gesture-to-video" times.

## Security in short

See `docs/architecture/COOP.md` for details. The session code authenticates both
sides with a challenge-response; every message carries an HMAC and a sequence number, so
forged, modified and replayed messages are rejected. Messages are **not encrypted**: on a
local network others on it could read which actions you take (nothing secret); on a VPN such
as Tailscale the VPN encrypts the traffic. The Host never opens a port to the internet and
refuses public addresses. Windows may ask once whether to allow the app on private networks
when you host; the app never changes firewall rules itself.
