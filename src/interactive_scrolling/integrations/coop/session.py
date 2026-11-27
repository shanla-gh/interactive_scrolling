"""Minimal two-person Co-op: one Host (whose browser shows the only feed) and one Guest.

Host
    Opens an authenticated WebSocket endpoint only while a session exists, accepts exactly one
    Guest, requires explicit approval before the Guest can control anything, and executes
    approved Guest requests through the Host's own :class:`ActionDispatcher`, so every safety
    rule applies (Live control only, browser context checks, one action at a time, stale
    events, emergency disable). Only next / previous Short and pause are accepted from the Guest.
    A shared cooldown (dispatcher admission check) makes the first accepted gesture win when
    both players act at once; duplicates and replays are rejected. Every result is attributed
    to the participant who triggered it.

Guest
    Authenticates with the session code, then forwards its own confirmed shared gestures to the
    Host through :class:`CoopGuestController`, which the Guest's dispatcher uses instead of the
    local browser while connected. Outcomes come back from the Host; nothing is assumed.

No video, camera images, audio or browsing data are transmitted. Participants watch the
Host's feed through their own screen-sharing application.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import logging
import socket
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
from websockets.sync.client import ClientConnection, connect
from websockets.sync.server import Server, ServerConnection, serve

from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import (
    ActionRecord,
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
)
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.integrations.coop import protocol as p
from interactive_scrolling.vision.landmarks import Handedness

log = logging.getLogger(__name__)

DEFAULT_PORT = 47816
HANDSHAKE_TIMEOUT_S = 5.0
MAX_FAILED_AUTH = 5
MAX_INVALID = 5
STALE_MS = 1500
SHARED_COOLDOWN_S = 1.0
PING_INTERVAL_S = 2.0
GESTURE_FOR_ACTION = {
    "next_short": GestureType.INDEX_SWIPE_UP,
    "previous_short": GestureType.INDEX_SWIPE_DOWN,
    "toggle_playback": GestureType.STOP_GESTURE,
}
SHARED = frozenset(ActionType(a) for a in p.SHARED_ACTIONS)


def local_addresses() -> list[str]:
    """IPv4 addresses of this computer that a Guest on the same network could use."""
    found: set[str] = set()
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(str(info[4][0]))
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("192.0.2.1", 9))  # no packet is sent; selects the outgoing interface
        found.add(s.getsockname()[0])
    return sorted(a for a in found if not a.startswith("127."))


@dataclass
class Participant:
    name: str
    role: str
    successes: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.successes.values())


@dataclass(frozen=True)
class CoopStatus:
    role: str
    """"off", "host" or "guest"."""
    state: str
    """Human-readable connection state."""
    code: str | None = None
    port: int | None = None
    addresses: tuple[str, ...] = ()
    peer: str | None = None
    approved: bool = False
    pending_approval: bool = False
    shared_control: bool = True
    rtt_ms: float | None = None
    session_s: float = 0.0
    last: p.SharedAction | None = None
    participants: tuple[tuple[str, str, int], ...] = ()
    """(name, role, successful shared actions)."""
    error: str | None = None


# ====================================================================== host


class CoopHost:
    def __init__(
        self,
        dispatcher: ActionDispatcher,
        name: str,
        port: int = DEFAULT_PORT,
        bind: str = "0.0.0.0",
        clock: Callable[[], float] = time.time,
        shared_cooldown_s: float = SHARED_COOLDOWN_S,
    ) -> None:
        self.dispatcher = dispatcher
        self.name = p.valid_name(name)
        self.port = port
        self.bind = bind
        self._clock = clock
        self.shared_cooldown_s = shared_cooldown_s
        self._lock = threading.RLock()
        self._send_lock = threading.Lock()
        self.code: str | None = None
        self._key: bytes | None = None
        self._server: Server | None = None
        self._thread: threading.Thread | None = None
        self._guest: ServerConnection | None = None
        self._guest_name: str | None = None
        self._session_key: bytes | None = None
        self._approved = False
        self._pending = False
        self.shared_control = True
        self._failed_auth = 0
        self._started = 0.0
        self._last_accept = -1e9
        self._seen_ids: OrderedDict[str, None] = OrderedDict()
        self._out_seq = 0
        self._offset_ms: float | None = None
        self._last: p.SharedAction | None = None
        self.participants: dict[str, Participant] = {}
        self.error: str | None = None
        self.history: deque[p.SharedAction] = deque(maxlen=50)
        dispatcher.add_admission_check(self.admission)
        dispatcher.add_record_listener(self._on_record)

    # ------------------------------------------------------------------ lifecycle

    @property
    def active(self) -> bool:
        return self._server is not None

    def start(self, name: str | None = None, port: int | None = None) -> str:
        """Create a session (new code) and start listening. Returns the session code."""
        self.stop()
        if name is not None:
            self.name = p.valid_name(name)
        if port is not None:
            self.port = port
        self.code = p.new_session_code()
        self._key = p.code_key(self.code)
        self._failed_auth = 0
        self.error = None
        self.participants = {self.name: Participant(self.name, "host")}
        self._last = None
        self._started = self._clock()
        self._server = serve(
            self._handle,
            self.bind,
            self.port,
            max_size=p.MAX_MESSAGE_BYTES,
            ping_interval=PING_INTERVAL_S,
            ping_timeout=PING_INTERVAL_S * 2,
            server_header=None,
        )
        self.port = self._server.socket.getsockname()[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="coop-host", daemon=True
        )
        self._thread.start()
        log.info("Co-op session created on port %d", self.port)
        return self.code

    def stop(self) -> None:
        server, self._server = self._server, None
        guest = self._guest
        if guest is not None:
            with contextlib.suppress(Exception):
                self._send({"type": "bye", "reason": "the host ended the session"})
            with contextlib.suppress(Exception):
                guest.close(1001, "session ended")
        if server is not None:
            with contextlib.suppress(OSError):
                server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        with self._lock:
            self._guest = None
            self._approved = self._pending = False
            self.code = None
            self._key = None

    # ------------------------------------------------------------------ host controls

    def approve(self, approved: bool = True) -> None:
        with self._lock:
            if self._guest is None:
                return
            self._approved = approved
            self._pending = False
        self._send({"type": "approval", "approved": approved})
        log.info("Co-op guest %s %s", self._guest_name, "approved" if approved else "refused")
        if not approved:
            self._close_guest("the host did not approve")

    def set_shared_control(self, enabled: bool) -> None:
        """Immediately allow or block Guest control (the Host keeps controlling)."""
        self.shared_control = enabled
        self._send({"type": "control", "enabled": enabled})

    def status(self) -> CoopStatus:
        with self._lock:
            peer = self._guest_name if self._guest is not None else None
            if not self.active:
                state = self.error or "no session"
            elif peer is None:
                state = "waiting for a guest"
            elif self._pending:
                state = f"{peer} wants to join"
            elif self._approved:
                state = f"connected with {peer}"
            else:
                state = "guest connected, not approved"
            return CoopStatus(
                role="host" if self.active else "off",
                state=state,
                code=self.code,
                port=self.port if self.active else None,
                addresses=tuple(local_addresses()) if self.active else (),
                peer=peer,
                approved=self._approved,
                pending_approval=self._pending,
                shared_control=self.shared_control,
                session_s=self._clock() - self._started if self.active else 0.0,
                last=self._last,
                participants=tuple((x.name, x.role, x.total) for x in self.participants.values()),
                error=self.error,
            )

    # ------------------------------------------------------------------ arbitration

    def _guest_live(self) -> bool:
        return self._guest is not None and self._approved and self.shared_control

    def admission(self, record: ActionRecord) -> str | None:
        """Shared cooldown: while a Guest shares control, the first accepted action wins."""
        if record.action not in SHARED or not self._guest_live():
            return None
        with self._lock:
            now = self._clock()
            if now - self._last_accept < self.shared_cooldown_s:
                return "shared cooldown: the other player just acted"
            self._last_accept = now
        return None

    def _on_record(self, record: ActionRecord) -> None:
        if not record.status.final or record.action not in SHARED or self._guest is None:
            return
        guest = record.source.startswith("guest")
        name = self._guest_name if guest else self.name
        shared = p.SharedAction(
            by=name or "guest",
            role="guest" if guest else "host",
            action=record.action.value,
            outcome=record.status.value,
            reason=record.reason[:120],
            at=self._clock(),
        )
        with self._lock:
            self._last = shared
            self.history.append(shared)
            if record.status is ActionStatus.SUCCEEDED and name in self.participants:
                stats = self.participants[name].successes
                stats[record.action.value] = stats.get(record.action.value, 0) + 1
        if guest:
            self._send(
                {
                    "type": "result",
                    "id": record.record_id,
                    "outcome": record.status.value,
                    "reason": record.reason[:120],
                }
            )
        self._send(
            {
                "type": "shared",
                "by": shared.by,
                "role": shared.role,
                "action": shared.action,
                "outcome": shared.outcome,
            }
        )

    # ------------------------------------------------------------------ connection

    def _send(self, payload: dict[str, Any]) -> None:
        with self._lock:
            guest, key = self._guest, self._session_key
        if guest is None or key is None:
            return
        with self._send_lock:
            self._out_seq += 1
            message = p.sign(
                key, {**payload, "seq": self._out_seq, "ms": int(self._clock() * 1000)}
            )
            with contextlib.suppress(ConnectionClosed, OSError):
                guest.send(message)

    def _close_guest(self, reason: str) -> None:
        with self._lock:
            guest = self._guest
        if guest is not None:
            with contextlib.suppress(Exception):
                guest.close(1000, reason[:100])

    def _handle(self, connection: ServerConnection) -> None:
        with self._lock:
            busy = self._guest is not None
        if busy:
            connection.close(1013, "session full")
            return
        key = self._key
        if key is None:
            connection.close(1001, "no session")
            return
        try:
            hello = p.load(connection.recv(timeout=HANDSHAKE_TIMEOUT_S))
            p.require(hello.get("type") == "hello" and hello.get("v") == p.PROTOCOL, "bad hello")
            name = p.valid_name(str(hello.get("name", "")))
            guest_nonce = hello.get("nonce")
            p.require(p.is_hex32(guest_nonce), "bad nonce")
            p.require(p.is_int(hello.get("ms")), "bad clock")
            p.require(name != self.name, "the guest must use a different name")
            host_nonce = p.new_nonce()
            connection.send(json.dumps({"type": "challenge", "v": p.PROTOCOL, "nonce": host_nonce}))
            auth = p.load(connection.recv(timeout=HANDSHAKE_TIMEOUT_S))
            expected = p.mac(key, "guest", host_nonce, guest_nonce, name)
            received = auth.get("mac")
            if (
                auth.get("type") != "auth"
                or not p.is_hex64(received)
                or not hmac.compare_digest(received, expected)
            ):
                self._failed_auth += 1
                if self._failed_auth >= MAX_FAILED_AUTH:
                    self.error = "too many wrong session codes: create a new session"
                    log.warning("Co-op: %s", self.error)
                    threading.Thread(target=self.stop, daemon=True).start()
                raise p.CoopProtocolError("wrong session code")
            connection.send(
                json.dumps(
                    {
                        "type": "welcome",
                        "v": p.PROTOCOL,
                        "host": self.name,
                        "mac": p.mac(key, "host", guest_nonce, host_nonce),
                    }
                )
            )
        except (TimeoutError, p.CoopProtocolError, ConnectionClosed) as exc:
            log.warning("Co-op guest refused: %s", exc)
            with contextlib.suppress(Exception):
                connection.close(4001, "unauthorized")
            return
        with self._lock:
            if self._guest is not None:
                connection.close(1013, "session full")
                return
            self._guest = connection
            self._guest_name = name
            self._session_key = p.session_key(key, host_nonce, guest_nonce)
            self._approved = False
            self._pending = True
            self._seen_ids.clear()
            self._offset_ms = float(hello["ms"]) - self._clock() * 1000
            self.participants[name] = Participant(name, "guest")
        log.info("Co-op guest %s authenticated; waiting for approval", name)
        self._serve_guest(connection, name)

    def _serve_guest(self, connection: ServerConnection, name: str) -> None:
        last_seq = 0
        invalid = 0
        try:
            for raw in connection:
                try:
                    data = p.verify(self._session_key or b"", p.load(raw))
                    seq = data.get("seq")
                    p.require(p.is_int(seq) and seq > last_seq, "replayed or reordered message")
                    last_seq = seq
                    self._dispatch(data)
                except p.CoopProtocolError as exc:
                    invalid += 1
                    log.warning("Co-op: invalid message from %s: %s", name, exc)
                    if invalid >= MAX_INVALID:
                        connection.close(1008, "too many invalid messages")
                        break
        except ConnectionClosed:
            pass
        finally:
            with self._lock:
                if self._guest is connection:
                    self._guest = None
                    self._approved = self._pending = False
                    self._session_key = None
            log.info("Co-op guest %s disconnected", name)

    def _dispatch(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        now_ms = self._clock() * 1000
        if kind == "ping":
            ms = data.get("ms")
            p.require(p.is_int(ms), "bad ping")
            with self._lock:
                estimate = ms - now_ms
                if self._offset_ms is None or estimate < self._offset_ms:
                    self._offset_ms = estimate  # the smallest observed offset has least delay
            self._send({"type": "pong", "echo": ms})
        elif kind == "action":
            self._guest_action(data, now_ms)
        elif kind == "bye":
            self._close_guest("guest left")
        else:
            raise p.CoopProtocolError(f"unexpected message type {kind!r}")

    def _reply(self, request_id: str, outcome: str, reason: str) -> None:
        self._send({"type": "result", "id": request_id, "outcome": outcome, "reason": reason})

    def _guest_action(self, data: dict[str, Any], now_ms: float) -> None:
        request_id, action, ms = data.get("id"), data.get("action"), data.get("ms")
        p.require(p.is_hex32(request_id), "bad id")
        p.require(isinstance(action, str) and len(action) <= 32, "bad action")
        p.require(p.is_int(ms), "bad clock")
        with self._lock:
            duplicate = request_id in self._seen_ids
            self._seen_ids[request_id] = None
            while len(self._seen_ids) > 500:
                self._seen_ids.popitem(last=False)
            approved, offset = self._approved, self._offset_ms or 0.0
        if duplicate:
            return self._reply(request_id, "rejected", "duplicate request")
        if action not in p.SHARED_ACTIONS:
            return self._reply(request_id, "rejected", "not a shared action")
        if not approved:
            return self._reply(request_id, "rejected", "the host has not approved shared control")
        if not self.shared_control:
            return self._reply(request_id, "rejected", "shared control is off on the host")
        age = now_ms - (ms - offset)
        if age > STALE_MS:
            return self._reply(request_id, "rejected", f"stale request ({age:.0f} ms old)")
        event = GestureEvent(
            GESTURE_FOR_ACTION[action],
            time.perf_counter_ns(),
            -1,
            Handedness.UNKNOWN,
            event_id=request_id,
        )
        # The result reaches the Guest through the record listener (attributed, confirmed).
        self.dispatcher.submit(event, action=ActionType(action), source="guest")
        return None


# ====================================================================== guest


class CoopError(RuntimeError):
    pass


class CoopGuest:
    def __init__(self, name: str, clock: Callable[[], float] = time.time) -> None:
        self.name = p.valid_name(name)
        self._clock = clock
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._ws: ClientConnection | None = None
        self._key: bytes | None = None
        self.host_name: str | None = None
        self.approved = False
        self.denied = False
        self.shared_control = True
        self.rtt_ms: float | None = None
        self.last: p.SharedAction | None = None
        self.state = "not connected"
        self._seq = 0
        self._last_in = 0
        self._pending: dict[str, tuple[threading.Event, list[ActionResult]]] = {}
        self._started = 0.0
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def connect(self, host: str, port: int, code: str, timeout_s: float = 5.0) -> None:
        key = p.code_key(code)
        nonce = p.new_nonce()
        try:
            ws = connect(
                f"ws://{host}:{port}/coop",
                open_timeout=timeout_s,
                max_size=p.MAX_MESSAGE_BYTES,
                ping_interval=PING_INTERVAL_S,
                ping_timeout=PING_INTERVAL_S * 2,
            )
        except (OSError, InvalidHandshake, InvalidURI, TimeoutError) as exc:
            raise CoopError(f"could not reach {host}:{port} ({exc})") from exc
        try:
            ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "v": p.PROTOCOL,
                        "name": self.name,
                        "nonce": nonce,
                        "ms": int(self._clock() * 1000),
                    }
                )
            )
            challenge = p.load(ws.recv(timeout=timeout_s))
            p.require(challenge.get("type") == "challenge", "unexpected answer")
            host_nonce = challenge.get("nonce")
            p.require(p.is_hex32(host_nonce), "bad challenge")
            ws.send(
                json.dumps(
                    {"type": "auth", "mac": p.mac(key, "guest", host_nonce, nonce, self.name)}
                )
            )
            welcome = p.load(ws.recv(timeout=timeout_s))
            p.require(welcome.get("type") == "welcome", "unexpected answer")
            proof = welcome.get("mac")
            p.require(
                p.is_hex64(proof)
                and hmac.compare_digest(proof, p.mac(key, "host", nonce, host_nonce)),
                "the host could not prove it knows the session code",
            )
            self.host_name = p.valid_name(str(welcome.get("host", "")))
        except ConnectionClosed as exc:
            ws.close()
            reason = exc.rcvd.reason if exc.rcvd else "connection closed"
            raise CoopError(f"the host refused the connection ({reason})") from exc
        except (TimeoutError, p.CoopProtocolError) as exc:
            ws.close()
            raise CoopError(f"could not join: {exc}") from exc
        self._key = p.session_key(key, host_nonce, nonce)
        self._ws = ws
        self._seq = self._last_in = 0
        self._started = self._clock()
        self.approved = self.denied = False
        self.state = f"waiting for {self.host_name} to approve"
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._reader, name="coop-guest", daemon=True),
            threading.Thread(target=self._pinger, name="coop-ping", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def disconnect(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                self._send({"type": "bye"})
            with contextlib.suppress(Exception):
                ws.close()
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=3)
        self._closed("left the session")

    def _closed(self, reason: str) -> None:
        with self._lock:
            self._ws = None
            pending = list(self._pending.values())
            self._pending.clear()
        self.approved = False
        self.state = f"disconnected: {reason}"
        for event, box in pending:
            box.append(ActionResult(ActionStatus.UNKNOWN, "connection to the host was lost"))
            event.set()

    def _send(self, payload: dict[str, Any]) -> None:
        ws, key = self._ws, self._key
        if ws is None or key is None:
            raise CoopError("not connected")
        with self._send_lock:
            self._seq += 1
            ws.send(p.sign(key, {**payload, "seq": self._seq, "ms": int(self._clock() * 1000)}))

    def _pinger(self) -> None:
        while not self._stop.wait(PING_INTERVAL_S):
            with contextlib.suppress(CoopError, ConnectionClosed, OSError):
                self._send({"type": "ping"})

    def _reader(self) -> None:
        ws = self._ws
        assert ws is not None
        reason = "connection lost"
        try:
            for raw in ws:
                try:
                    data = p.verify(self._key or b"", p.load(raw))
                    seq = data.get("seq")
                    p.require(p.is_int(seq) and seq > self._last_in, "replayed message")
                    self._last_in = seq
                    if data.get("type") == "bye":
                        reason = str(data.get("reason", "the host ended the session"))[:100]
                        break
                    self._handle(data)
                except p.CoopProtocolError as exc:
                    log.warning("Co-op: invalid message from host: %s", exc)
        except ConnectionClosed as exc:
            if exc.rcvd is not None and exc.rcvd.reason:
                reason = exc.rcvd.reason
        finally:
            if not self._stop.is_set():
                self._closed(reason)

    def _handle(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "approval":
            self.approved = data.get("approved") is True
            self.denied = not self.approved
            self.state = (
                f"connected to {self.host_name}" if self.approved else "the host did not approve"
            )
        elif kind == "control":
            self.shared_control = data.get("enabled") is True
        elif kind == "pong":
            echo = data.get("echo")
            if p.is_int(echo):
                self.rtt_ms = max(0.0, self._clock() * 1000 - echo)
        elif kind == "result":
            request_id, outcome = data.get("id"), data.get("outcome")
            if not (p.is_hex32(request_id) and outcome in p.OUTCOMES):
                raise p.CoopProtocolError("bad result")
            with self._lock:
                waiter = self._pending.pop(request_id, None)
            if waiter is not None:
                status = ActionStatus(outcome)
                reason = str(data.get("reason", ""))[:120]
                waiter[1].append(
                    ActionResult(status, f"host: {reason}" if reason else "", "on the host")
                )
                waiter[0].set()
        elif kind == "shared":
            if data.get("action") in p.SHARED_ACTIONS and data.get("outcome") in p.OUTCOMES:
                self.last = p.SharedAction(
                    by=str(data.get("by", ""))[:24],
                    role="host" if data.get("role") == "host" else "guest",
                    action=str(data["action"]),
                    outcome=str(data["outcome"]),
                    reason="",
                    at=self._clock(),
                )
        else:
            raise p.CoopProtocolError(f"unexpected message type {kind!r}")

    def request(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        event = threading.Event()
        box: list[ActionResult] = []
        with self._lock:
            self._pending[request_id] = (event, box)
        try:
            self._send({"type": "action", "id": request_id, "action": action.value})
        except (CoopError, ConnectionClosed, OSError):
            with self._lock:
                self._pending.pop(request_id, None)
            return ActionResult(ActionStatus.UNKNOWN, "connection to the host was lost")
        if not event.wait(timeout_s + 1.0):
            with self._lock:
                self._pending.pop(request_id, None)
            return ActionResult(ActionStatus.UNKNOWN, "no answer from the host in time")
        return box[0]

    def cancel_all(self) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for event, box in pending:
            box.append(ActionResult(ActionStatus.UNKNOWN, "cancelled by control disable"))
            event.set()

    def status(self) -> CoopStatus:
        return CoopStatus(
            role="guest" if self.connected else "off",
            state=self.state,
            peer=self.host_name if self.connected else None,
            approved=self.approved,
            shared_control=self.shared_control,
            rtt_ms=self.rtt_ms,
            session_s=self._clock() - self._started if self.connected else 0.0,
            last=self.last,
        )


class CoopGuestController:
    """ActionController for the Guest's dispatcher: forwards shared actions to the Host."""

    def __init__(self, guest: CoopGuest) -> None:
        self.guest = guest

    def check(self, action: ActionType) -> ControllerCheck:
        g = self.guest
        if action not in SHARED:
            return ControllerCheck(False, "not shared in co-op (next, previous and pause only)")
        if not g.connected:
            return ControllerCheck(False, "not connected to a co-op host")
        if not g.approved:
            return ControllerCheck(False, "waiting for the host to approve")
        if not g.shared_control:
            return ControllerCheck(False, "shared control is off on the host")
        return ControllerCheck(True)

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        return self.guest.request(action, request_id, timeout_s)

    def cancel_all(self) -> None:
        self.guest.cancel_all()
