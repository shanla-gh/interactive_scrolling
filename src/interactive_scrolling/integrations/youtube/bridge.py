"""Loopback WebSocket server for the companion browser extension.

Security boundaries
-------------------
* Binds to 127.0.0.1 only; never to other interfaces.
* The HTTP upgrade is accepted only on ``/bridge`` and only from this project's extension
  origin (``chrome-extension://<fixed id>``), so web pages cannot connect.
* The first message must be ``hello`` with the pairing code shown in the app (compared in
  constant time) within ``HELLO_TIMEOUT_S``; otherwise the connection is closed with 4001.
* Messages are size limited and validated against a strict schema
  (:mod:`.protocol`); repeated invalid messages close the connection.
* The server only sends six fixed commands. There is no generic command channel.
* ``/preview`` (same origin and pairing-code checks) carries the live preview of the one tab
  the user chose in the extension popup: binary JPEG frames, each validated and size limited.
  Only one preview connection exists at a time; frames are never stored.
"""

from __future__ import annotations

import contextlib
import hmac
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response
from websockets.sync.server import Server, ServerConnection, serve

from interactive_scrolling.core.timing import Clock, now_ns
from interactive_scrolling.integrations.youtube import protocol
from interactive_scrolling.integrations.youtube.preview import PreviewFeed
from interactive_scrolling.integrations.youtube.protocol import (
    CommandResult,
    Context,
    Hello,
    PreviewHello,
    PreviewState,
    ProtocolError,
)

log = logging.getLogger(__name__)

EXTENSION_ID = "phcdgkmcjbgdligepbkfkceejlbbmlio"
"""Fixed ID of ``browser_extension/`` (derived from the public key in its manifest)."""
ALLOWED_ORIGINS = frozenset({f"chrome-extension://{EXTENSION_ID}"})
HELLO_TIMEOUT_S = 5.0
MAX_INVALID_MESSAGES = 5
MAX_CONNECTIONS = 8
"""Simultaneous authenticated browser connections (a user has a handful of browsers at most)."""


@dataclass(slots=True)
class ClientInfo:
    client_id: str
    browser: str
    extension_version: str
    connected_ns: int
    context: Context | None = None
    context_ns: int | None = None
    protocol: int = protocol.PROTOCOL_VERSION


@dataclass(slots=True)
class _Pending:
    client_id: str
    event: threading.Event = field(default_factory=threading.Event)
    result: CommandResult | None = None
    error: str | None = None


class BridgeServer:
    """Accepts authenticated extension connections and relays commands and results."""

    def __init__(
        self,
        port: int,
        token: str,
        allowed_origins: frozenset[str] = ALLOWED_ORIGINS,
        on_change: Callable[[], None] | None = None,
        clock: Clock = now_ns,
        preview: PreviewFeed | None = None,
    ) -> None:
        self.port = port
        self.preview = preview if preview is not None else PreviewFeed()
        self._preview_connection: ServerConnection | None = None
        self._token = token
        self._allowed_origins = allowed_origins
        self._on_change = on_change
        self._clock = clock
        self._lock = threading.Lock()
        self._clients: dict[str, ClientInfo] = {}
        self._connections: dict[str, ServerConnection] = {}
        self._pending: dict[str, _Pending] = {}
        self._server: Server | None = None
        self._thread: threading.Thread | None = None
        self._stopping = False
        self.error: str | None = None
        self.rejected_connections = 0

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> bool:
        """Bind and serve in a background thread. Returns False (with ``error``) on failure."""
        try:
            self._server = serve(
                self._handle,
                "127.0.0.1",
                self.port,
                process_request=self._check_request,
                # Text messages are limited to MAX_MESSAGE_BYTES by protocol.parse; only the
                # preview connection may send larger (binary) frames.
                max_size=protocol.MAX_PREVIEW_FRAME_BYTES + 64,
                ping_interval=20,
                ping_timeout=20,
                server_header=None,
            )
        except OSError as exc:
            self.error = f"port {self.port} unavailable ({exc.strerror or exc})"
            log.error("Browser bridge could not start: %s", self.error)
            return False
        self.error = None
        self._stopping = False
        self._thread = threading.Thread(
            target=self._serve, args=(self._server,), name="browser-bridge", daemon=True
        )
        self._thread.start()
        log.info("Browser bridge listening on 127.0.0.1:%d", self.port)
        return True

    def _serve(self, server: Server) -> None:
        try:
            server.serve_forever()
        except OSError:
            # On Windows, shutting down closes the listening socket while select() waits on
            # it (WinError 10038). That is the expected end of an intentional stop.
            if not self._stopping:
                log.exception("Browser bridge stopped unexpectedly")
                self.error = "bridge stopped unexpectedly"

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            self._stopping = True
            server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=3)
        with self._lock:
            pending = list(self._pending.values())
        for item in pending:
            item.error = "bridge stopped"
            item.event.set()

    def set_change_listener(self, callback: Callable[[], None] | None) -> None:
        """Called (from bridge threads) whenever a connection or its context changes."""
        self._on_change = callback

    @property
    def listening(self) -> bool:
        return self._server is not None

    def set_token(self, token: str) -> None:
        """Change the pairing code; existing connections are closed."""
        self._token = token
        with self._lock:
            connections = list(self._connections.values())
            if self._preview_connection is not None:
                connections.append(self._preview_connection)
        for connection in connections:
            connection.close(4001, "pairing code changed")

    def clients(self) -> list[ClientInfo]:
        with self._lock:
            return [
                ClientInfo(
                    c.client_id,
                    c.browser,
                    c.extension_version,
                    c.connected_ns,
                    c.context,
                    c.context_ns,
                    c.protocol,
                )
                for c in self._clients.values()
            ]

    # ------------------------------------------------------------------ commands

    def request(
        self,
        client_id: str,
        request_id: str,
        action: str,
        video_id: str | None,
        timeout_s: float,
        tab_id: int | None = None,
    ) -> CommandResult | str:
        """Send a command and wait for its result. Returns the result or an error string."""
        message = protocol.command_message(
            request_id, action, video_id, int(timeout_s * 1000), tab_id
        )
        with self._lock:
            connection = self._connections.get(client_id)
            if connection is None:
                return "browser disconnected"
            pending = _Pending(client_id)
            self._pending[request_id] = pending
        try:
            connection.send(message)
        except ConnectionClosed:
            with self._lock:
                self._pending.pop(request_id, None)
            return "browser disconnected"
        # Allow the page its full timeout plus a margin for the round trip.
        finished = pending.event.wait(timeout_s + 0.75)
        with self._lock:
            self._pending.pop(request_id, None)
        if pending.result is not None:
            return pending.result
        if pending.error is not None:
            return pending.error
        return "no confirmation from the browser in time" if not finished else "no result"

    def cancel_all(self) -> None:
        with self._lock:
            pending = list(self._pending.values())
        for item in pending:
            item.error = "cancelled by live-control disable"
            item.event.set()

    # ------------------------------------------------------------------ connection handling

    def _check_request(self, connection: ServerConnection, request: Request) -> Response | None:
        origin = request.headers.get("Origin")
        if request.path not in ("/bridge", "/preview") or origin not in self._allowed_origins:
            self.rejected_connections += 1
            log.warning("Rejected bridge connection (path %s, origin %s)", request.path, origin)
            return connection.respond(403, "Forbidden\n")
        return None

    def stop_preview(self) -> bool:
        """Ask the browser to end the live preview (revokes the preview tab authorization)."""
        return self.preview.request_stop()

    def _handle(self, connection: ServerConnection) -> None:
        request = connection.request
        if request is not None and request.path == "/preview":
            self._handle_preview(connection)
            return
        try:
            first = connection.recv(timeout=HELLO_TIMEOUT_S)
            hello = protocol.parse(first)
            if not isinstance(hello, Hello) or not hmac.compare_digest(
                hello.token.encode(), self._token.encode()
            ):
                raise ProtocolError("authentication failed")
        except (TimeoutError, ProtocolError, ConnectionClosed) as exc:
            self.rejected_connections += 1
            log.warning("Browser extension not authenticated: %s", exc)
            connection.close(4001, "unauthorized")
            return
        client = ClientInfo(
            uuid.uuid4().hex,
            hello.browser,
            hello.extension_version,
            self._clock(),
            protocol=hello.protocol,
        )
        with self._lock:
            full = len(self._clients) >= MAX_CONNECTIONS
        if full:
            self.rejected_connections += 1
            log.warning("Refused browser connection: %d already connected", MAX_CONNECTIONS)
            connection.close(1013, "too many connections")
            return
        with self._lock:
            self._clients[client.client_id] = client
            self._connections[client.client_id] = connection
        log.info("Browser extension connected (%s %s)", hello.browser, hello.extension_version)
        self._notify()
        invalid = 0
        try:
            connection.send(protocol.WELCOME)
            for raw in connection:
                try:
                    message = protocol.parse(raw)
                except ProtocolError as exc:
                    invalid += 1
                    log.warning("Invalid message from extension: %s", exc)
                    if invalid >= MAX_INVALID_MESSAGES:
                        connection.close(1008, "too many invalid messages")
                        break
                    continue
                if isinstance(message, Context):
                    with self._lock:
                        client.context = message
                        client.context_ns = self._clock()
                    self._notify()
                elif isinstance(message, CommandResult):
                    with self._lock:
                        pending = self._pending.get(message.request_id)
                    if pending is not None and pending.client_id == client.client_id:
                        pending.result = message
                        pending.event.set()
        except ConnectionClosed:
            pass
        finally:
            with self._lock:
                self._clients.pop(client.client_id, None)
                self._connections.pop(client.client_id, None)
                orphans = [p for p in self._pending.values() if p.client_id == client.client_id]
            for pending in orphans:
                pending.error = "browser disconnected during the action"
                pending.event.set()
            log.info("Browser extension disconnected (%s)", client.browser)
            self._notify()

    def _handle_preview(self, connection: ServerConnection) -> None:
        try:
            first = connection.recv(timeout=HELLO_TIMEOUT_S)
            hello = protocol.parse(first)
            if not isinstance(hello, PreviewHello) or not hmac.compare_digest(
                hello.token.encode(), self._token.encode()
            ):
                raise ProtocolError("authentication failed")
        except (TimeoutError, ProtocolError, ConnectionClosed) as exc:
            self.rejected_connections += 1
            log.warning("Preview connection not authenticated: %s", exc)
            connection.close(4001, "unauthorized")
            return
        with self._lock:
            previous, self._preview_connection = self._preview_connection, connection
        if previous is not None:
            previous.close(1000, "replaced by a new preview")

        def stop() -> None:
            with contextlib.suppress(ConnectionClosed):
                connection.send(protocol.PREVIEW_STOP)

        self.preview.attach(stop)
        log.info("Live preview connected")
        invalid = 0
        reason = "the browser ended the preview"
        try:
            connection.send(protocol.PREVIEW_WELCOME)
            for raw in connection:
                try:
                    if isinstance(raw, bytes):
                        self.preview.push(protocol.parse_preview_frame(raw))
                        continue
                    message = protocol.parse(raw)
                    if not isinstance(message, PreviewState):
                        raise ProtocolError("unexpected message on the preview connection")
                except ProtocolError as exc:
                    invalid += 1
                    log.warning("Invalid preview message: %s", exc)
                    if invalid >= MAX_INVALID_MESSAGES:
                        connection.close(1008, "too many invalid messages")
                        reason = "the preview sent invalid data"
                        break
                    continue
                self.preview.set_state(message.state, message.reason)
                if message.state == "stopped":
                    reason = message.reason or reason
        except ConnectionClosed:
            pass
        finally:
            with self._lock:
                current = self._preview_connection is connection
                if current:
                    self._preview_connection = None
            if current:
                self.preview.detach(reason)
            log.info("Live preview disconnected (%s)", reason)

    def _notify(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                log.exception("Bridge change listener failed")
