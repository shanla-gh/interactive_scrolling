"""Message schema between the desktop app and the browser extension (protocol version 3).

Every inbound message is parsed and validated here; anything that does not match the schema
exactly is rejected. The app only ever sends ``welcome``, ``ping`` and ``command`` messages
with one of six fixed actions, so the extension cannot be made to do anything else.

Version 2 adds the two tab-navigation commands. Version 1 extensions (0.2) may still connect;
the controller refuses tab actions for them with a request to reload the extension.

Version 3 adds the live preview: the context reports the one tab the user chose to show in the
app (``preview``), Shorts commands may be addressed to that tab (``tab_id``), and a second
connection on ``/preview`` carries the preview frames (binary: 8-byte capture time in ms,
4-byte frame number, JPEG) and ``preview_state`` messages.
"""

from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 3
SUPPORTED_PROTOCOLS = frozenset({1, 2, 3})
MAX_MESSAGE_BYTES = 16 * 1024
MAX_PREVIEW_FRAME_BYTES = 1024 * 1024
"""One preview frame (a 640-pixel-high JPEG is typically 30-80 KB)."""
PREVIEW_STATES = frozenset({"streaming", "hidden", "stopped"})
_JPEG_MAGIC = b"\xff\xd8"
BROWSERS = frozenset({"chrome", "edge", "chromium"})
OUTCOMES = frozenset({"succeeded", "no_change", "rejected", "failed", "unknown"})
SHORTS_COMMANDS = frozenset({"next_short", "previous_short", "like_short", "toggle_playback"})
TAB_COMMANDS = frozenset({"next_browser_tab", "previous_browser_tab"})
COMMAND_ACTIONS = SHORTS_COMMANDS | TAB_COMMANDS
MAX_TABS = 10_000
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,32}$")
_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Hello:
    token: str
    browser: str
    extension_version: str
    protocol: int = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class ShortsTab:
    tab_id: int
    video_id: str | None
    visible: bool
    has_video: bool
    video_ready: bool | None
    """The active video has loaded enough to play (YouTube ignores navigation before)."""
    paused: bool | None
    liked: bool | None
    signed_in: bool | None
    can_previous: bool | None = None
    """A previous Short exists (``False`` at the first Short of a feed); ``None`` if unknown
    (extension versions before 0.4)."""
    can_next: bool | None = None


@dataclass(frozen=True, slots=True)
class PreviewTab:
    """The tab the user chose to show in the app (from the extension popup)."""

    tab_id: int
    in_front: bool
    """It is the active tab of the last focused browser window."""
    shorts: ShortsTab | None
    """Its Shorts state, or ``None`` while it does not show a Short."""


@dataclass(frozen=True, slots=True)
class Context:
    browser_focused: bool
    focus_ts: float
    shorts: ShortsTab | None
    preview: PreviewTab | None = None


@dataclass(frozen=True, slots=True)
class PreviewHello:
    token: str


@dataclass(frozen=True, slots=True)
class PreviewState:
    state: str
    reason: str


@dataclass(frozen=True, slots=True)
class PreviewFrame:
    captured_ms: float
    """Wall-clock time (ms since the epoch) when the browser read the frame."""
    number: int
    jpeg: bytes


@dataclass(frozen=True, slots=True)
class CommandResult:
    request_id: str
    outcome: str
    reason: str
    video_id_before: str | None = None
    video_id_after: str | None = None
    paused: bool | None = None
    liked: bool | None = None
    tab_index_before: int | None = None
    tab_index_after: int | None = None
    tab_count: int | None = None
    """Tab positions in the window (0-based) for tab commands; no tab ids, titles or URLs."""


@dataclass(frozen=True, slots=True)
class Pong:
    pass


Message = Hello | Context | CommandResult | Pong | PreviewHello | PreviewState


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def _optional_bool(data: dict[str, Any], key: str) -> bool | None:
    value = data.get(key)
    _require(value is None or isinstance(value, bool), f"{key} must be boolean or null")
    return value


def _optional_video_id(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    _require(isinstance(value, str) and bool(_VIDEO_ID.match(value)), f"invalid {key}")
    return value


def _optional_index(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    _require(
        isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_TABS,
        f"invalid {key}",
    )
    return value


def _short_text(data: dict[str, Any], key: str, limit: int) -> str:
    value = data.get(key, "")
    _require(isinstance(value, str) and len(value) <= limit, f"{key} must be text <= {limit}")
    return value


def _parse_shorts(shorts: Any) -> ShortsTab:
    _require(isinstance(shorts, dict), "shorts must be an object or null")
    tab_id = shorts.get("tab_id")
    _require(isinstance(tab_id, int) and not isinstance(tab_id, bool), "invalid tab_id")
    _require(shorts.get("is_shorts") is True, "shorts.is_shorts must be true")
    visible = shorts.get("visible")
    has_video = shorts.get("has_video")
    _require(isinstance(visible, bool) and isinstance(has_video, bool), "invalid flags")
    return ShortsTab(
        tab_id=tab_id,
        video_id=_optional_video_id(shorts, "video_id"),
        visible=visible,
        has_video=has_video,
        video_ready=_optional_bool(shorts, "video_ready"),
        paused=_optional_bool(shorts, "paused"),
        liked=_optional_bool(shorts, "liked"),
        signed_in=_optional_bool(shorts, "signed_in"),
        can_previous=_optional_bool(shorts, "can_previous"),
        can_next=_optional_bool(shorts, "can_next"),
    )


def _parse_preview(data: Any) -> PreviewTab | None:
    if data is None:
        return None
    _require(isinstance(data, dict), "preview must be an object or null")
    tab_id = data.get("tab_id")
    _require(isinstance(tab_id, int) and not isinstance(tab_id, bool), "invalid preview tab_id")
    in_front = data.get("in_front")
    _require(isinstance(in_front, bool), "invalid preview in_front")
    shorts = data.get("shorts")
    tab = _parse_shorts(shorts) if shorts is not None else None
    _require(tab is None or tab.tab_id == tab_id, "preview shorts belong to another tab")
    return PreviewTab(tab_id, in_front, tab)


def parse_preview_frame(raw: bytes) -> PreviewFrame:
    """Validate one binary preview frame (only accepted on the preview connection)."""
    _require(isinstance(raw, bytes), "preview frames are binary")
    _require(16 <= len(raw) <= MAX_PREVIEW_FRAME_BYTES, "preview frame size out of range")
    captured_ms = struct.unpack_from("<d", raw, 0)[0]
    number = struct.unpack_from("<I", raw, 8)[0]
    _require(math.isfinite(captured_ms) and captured_ms > 0, "invalid capture time")
    jpeg = raw[12:]
    _require(jpeg[:2] == _JPEG_MAGIC, "preview frame is not a JPEG image")
    return PreviewFrame(captured_ms, number, jpeg)


def parse(raw: str | bytes) -> Message:
    """Parse and validate one inbound message."""
    if isinstance(raw, bytes):
        raise ProtocolError("binary messages are not accepted")
    _require(len(raw.encode("utf-8")) <= MAX_MESSAGE_BYTES, "message too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc.msg}") from exc
    _require(isinstance(data, dict), "message must be an object")
    kind = data.get("type")
    if kind == "hello":
        version = data.get("protocol")
        _require(
            isinstance(version, int)
            and not isinstance(version, bool)
            and version in SUPPORTED_PROTOCOLS,
            "unsupported protocol version",
        )
        token = data.get("token")
        _require(isinstance(token, str) and 0 < len(token) <= 256, "invalid token")
        browser = data.get("browser")
        _require(browser in BROWSERS, "unknown browser")
        return Hello(token, browser, _short_text(data, "extension_version", 32), version)
    if kind == "context":
        focused = data.get("browser_focused")
        _require(isinstance(focused, bool), "browser_focused must be boolean")
        focus_ts = data.get("focus_ts")
        _require(
            isinstance(focus_ts, int | float) and not isinstance(focus_ts, bool) and focus_ts >= 0,
            "invalid focus_ts",
        )
        shorts = data.get("shorts")
        tab = _parse_shorts(shorts) if shorts is not None else None
        return Context(focused, float(focus_ts), tab, _parse_preview(data.get("preview")))
    if kind == "preview_hello":
        version = data.get("protocol")
        _require(
            isinstance(version, int) and not isinstance(version, bool) and version >= 3,
            "unsupported preview protocol version",
        )
        token = data.get("token")
        _require(isinstance(token, str) and 0 < len(token) <= 256, "invalid token")
        return PreviewHello(token)
    if kind == "preview_state":
        state = data.get("state")
        _require(state in PREVIEW_STATES, "invalid preview state")
        return PreviewState(state, _short_text(data, "reason", 200))
    if kind == "result":
        request_id = data.get("id")
        _require(isinstance(request_id, str) and bool(_REQUEST_ID.match(request_id)), "invalid id")
        outcome = data.get("outcome")
        _require(outcome in OUTCOMES, "invalid outcome")
        return CommandResult(
            request_id=request_id,
            outcome=outcome,
            reason=_short_text(data, "reason", 200),
            video_id_before=_optional_video_id(data, "video_id_before"),
            video_id_after=_optional_video_id(data, "video_id_after"),
            paused=_optional_bool(data, "paused"),
            liked=_optional_bool(data, "liked"),
            tab_index_before=_optional_index(data, "tab_index_before"),
            tab_index_after=_optional_index(data, "tab_index_after"),
            tab_count=_optional_index(data, "tab_count"),
        )
    if kind == "pong":
        return Pong()
    raise ProtocolError(f"unknown message type {kind!r}")


def command_message(
    request_id: str,
    action: str,
    video_id: str | None,
    timeout_ms: int,
    tab_id: int | None = None,
) -> str:
    """A command for the extension. ``tab_id`` addresses the authorized preview tab (Shorts
    commands only); the extension refuses any other tab."""
    if action not in COMMAND_ACTIONS:
        raise ProtocolError(f"unsupported action {action!r}")
    if not _REQUEST_ID.match(request_id):
        raise ProtocolError("invalid request id")
    if action in TAB_COMMANDS:
        video_id = None  # tab commands never carry page data
        tab_id = None
    message: dict[str, Any] = {
        "type": "command",
        "id": request_id,
        "action": action,
        "video_id": video_id,
        "timeout_ms": int(timeout_ms),
    }
    if tab_id is not None:
        message["tab_id"] = int(tab_id)
    return json.dumps(message)


WELCOME = json.dumps({"type": "welcome", "protocol": PROTOCOL_VERSION})
PING = json.dumps({"type": "ping"})
PREVIEW_WELCOME = json.dumps({"type": "preview_welcome", "protocol": PROTOCOL_VERSION})
PREVIEW_STOP = json.dumps({"type": "preview_stop"})
