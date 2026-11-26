"""Message schema between the desktop app and the browser extension (protocol version 2).

Every inbound message is parsed and validated here; anything that does not match the schema
exactly is rejected. The app only ever sends ``welcome``, ``ping`` and ``command`` messages
with one of six fixed actions, so the extension cannot be made to do anything else.

Version 2 adds the two tab-navigation commands. Version 1 extensions (0.2) may still connect;
the controller refuses tab actions for them with a request to reload the extension.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 2
SUPPORTED_PROTOCOLS = frozenset({1, 2})
MAX_MESSAGE_BYTES = 16 * 1024
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


@dataclass(frozen=True, slots=True)
class Context:
    browser_focused: bool
    focus_ts: float
    shorts: ShortsTab | None


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


Message = Hello | Context | CommandResult | Pong


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
        tab: ShortsTab | None = None
        if shorts is not None:
            _require(isinstance(shorts, dict), "shorts must be an object or null")
            tab_id = shorts.get("tab_id")
            _require(isinstance(tab_id, int) and not isinstance(tab_id, bool), "invalid tab_id")
            _require(shorts.get("is_shorts") is True, "shorts.is_shorts must be true")
            visible = shorts.get("visible")
            has_video = shorts.get("has_video")
            _require(isinstance(visible, bool) and isinstance(has_video, bool), "invalid flags")
            tab = ShortsTab(
                tab_id=tab_id,
                video_id=_optional_video_id(shorts, "video_id"),
                visible=visible,
                has_video=has_video,
                video_ready=_optional_bool(shorts, "video_ready"),
                paused=_optional_bool(shorts, "paused"),
                liked=_optional_bool(shorts, "liked"),
                signed_in=_optional_bool(shorts, "signed_in"),
            )
        return Context(focused, float(focus_ts), tab)
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


def command_message(request_id: str, action: str, video_id: str | None, timeout_ms: int) -> str:
    if action not in COMMAND_ACTIONS:
        raise ProtocolError(f"unsupported action {action!r}")
    if not _REQUEST_ID.match(request_id):
        raise ProtocolError("invalid request id")
    if action in TAB_COMMANDS:
        video_id = None  # tab commands never carry page data
    return json.dumps(
        {
            "type": "command",
            "id": request_id,
            "action": action,
            "video_id": video_id,
            "timeout_ms": int(timeout_ms),
        }
    )


WELCOME = json.dumps({"type": "welcome", "protocol": PROTOCOL_VERSION})
PING = json.dumps({"type": "ping"})
