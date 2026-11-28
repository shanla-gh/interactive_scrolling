"""Strict validation of extension messages."""

from __future__ import annotations

import json

import pytest

from interactive_scrolling.integrations.youtube import protocol
from interactive_scrolling.integrations.youtube.protocol import (
    CommandResult,
    Context,
    Hello,
    ProtocolError,
    parse,
)

RID = "0" * 32


def msg(**data) -> str:
    return json.dumps(data)


def shorts(**overrides):
    base = {
        "tab_id": 4,
        "is_shorts": True,
        "video_id": "abcdefghijk",
        "visible": True,
        "has_video": True,
        "paused": False,
        "liked": None,
        "signed_in": True,
        "age_ms": 12,
    }
    base.update(overrides)
    return base


def test_valid_messages() -> None:
    assert parse(
        msg(type="hello", protocol=1, token="t" * 20, browser="edge", extension_version="0.2.0")
    ) == Hello("t" * 20, "edge", "0.2.0", 1)
    assert parse(
        msg(type="hello", protocol=2, token="t" * 20, browser="edge", extension_version="0.3.0")
    ) == Hello("t" * 20, "edge", "0.3.0", 2)
    context = parse(msg(type="context", browser_focused=True, focus_ts=1.5e12, shorts=shorts()))
    assert isinstance(context, Context) and context.shorts.video_id == "abcdefghijk"
    assert parse(msg(type="context", browser_focused=False, focus_ts=0, shorts=None)).shorts is None
    result = parse(
        msg(
            type="result",
            id=RID,
            outcome="succeeded",
            reason="",
            video_id_before="abcdefghijk",
            video_id_after="bcdefghijkl",
        )
    )
    assert isinstance(result, CommandResult) and result.video_id_after == "bcdefghijkl"
    assert isinstance(parse(msg(type="pong")), protocol.Pong)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"type":"pong"}',  # binary frames
        "not json",
        "[]",
        msg(type="eval", code="alert(1)"),
        msg(type="hello", protocol=4, token="x" * 20, browser="edge"),
        msg(type="hello", protocol=True, token="x" * 20, browser="edge"),
        msg(type="result", id=RID, outcome="succeeded", tab_index_after=-1),
        msg(type="result", id=RID, outcome="succeeded", tab_count="3"),
        msg(type="hello", protocol=1, token="", browser="edge"),
        msg(type="hello", protocol=1, token="x" * 20, browser="firefox"),
        msg(type="hello", protocol=1, token="x" * 300, browser="edge"),
        msg(type="context", browser_focused="yes", focus_ts=1, shorts=None),
        msg(type="context", browser_focused=True, focus_ts=-1, shorts=None),
        msg(type="context", browser_focused=True, focus_ts=1, shorts=shorts(video_id="../../etc")),
        msg(type="context", browser_focused=True, focus_ts=1, shorts=shorts(is_shorts=False)),
        msg(type="context", browser_focused=True, focus_ts=1, shorts=shorts(tab_id="4")),
        msg(type="context", browser_focused=True, focus_ts=1, shorts=shorts(paused="no")),
        msg(type="result", id="not-a-hex-id", outcome="succeeded"),
        msg(type="result", id=RID, outcome="maybe"),
        msg(type="result", id=RID, outcome="failed", reason="x" * 500),
        "x" * (protocol.MAX_MESSAGE_BYTES + 1),
    ],
)
def test_invalid_messages_are_rejected(raw) -> None:
    with pytest.raises(ProtocolError):
        parse(raw)


def test_only_fixed_commands_can_be_built() -> None:
    message = json.loads(protocol.command_message(RID, "next_short", "abcdefghijk", 3000))
    assert message == {
        "type": "command",
        "id": RID,
        "action": "next_short",
        "video_id": "abcdefghijk",
        "timeout_ms": 3000,
    }
    with pytest.raises(ProtocolError):
        protocol.command_message(RID, "open_url", None, 1000)
    with pytest.raises(ProtocolError):
        protocol.command_message(RID, "close_tab", None, 1000)
    with pytest.raises(ProtocolError):
        protocol.command_message("x", "next_short", None, 1000)


def test_tab_commands_never_carry_page_data() -> None:
    message = json.loads(protocol.command_message(RID, "next_browser_tab", "abcdefghijk", 2000))
    assert message["action"] == "next_browser_tab"
    assert message["video_id"] is None
