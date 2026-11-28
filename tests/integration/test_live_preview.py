"""Live Shorts preview: the /preview connection, the frame feed and preview-tab control.

Driven by scripted Python clients that speak the extension side of protocol 3. The real
extension and the real YouTube site are covered by ``scripts/prototype_preview.py`` and the
live test (``--live-youtube``).
"""

from __future__ import annotations

import json
import struct
import time
import uuid

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from interactive_scrolling.actions.types import ActionStatus, ActionType
from interactive_scrolling.integrations.youtube import protocol
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from interactive_scrolling.integrations.youtube.preview import PreviewFeed
from tests.helpers import wait_until
from tests.integration.test_youtube_bridge import ORIGIN, TOKEN, FakeExtension, free_port


@pytest.fixture
def server():  # type: ignore[no-untyped-def]
    bridge = BridgeServer(free_port(), TOKEN)
    controller = YouTubeShortsController(bridge)
    bridge.set_change_listener(controller.refresh)
    assert bridge.start()
    yield bridge, controller, None
    bridge.stop()


JPEG = b"\xff\xd8" + b"\x00" * 200 + b"\xff\xd9"
PREVIEW_TAB = 42


def frame(number: int, captured_ms: float | None = None, body: bytes = JPEG) -> bytes:
    captured = time.time() * 1000 if captured_ms is None else captured_ms
    return struct.pack("<dI", captured, number) + body


def open_preview(port: int, token: str = TOKEN, origin: str = ORIGIN):
    ws = connect(f"ws://127.0.0.1:{port}/preview", origin=origin, open_timeout=5)
    ws.send(json.dumps({"type": "preview_hello", "protocol": 3, "token": token}))
    return ws


def preview_context(
    ext: FakeExtension,
    *,
    focused: bool = False,
    active_shorts: bool = False,
    preview_shorts: bool = True,
    video_id: str = "previewvid01",
) -> None:
    shorts_state = {
        "tab_id": PREVIEW_TAB,
        "is_shorts": True,
        "video_id": video_id,
        "visible": True,
        "has_video": True,
        "video_ready": True,
        "paused": False,
        "liked": False,
        "signed_in": True,
    }
    payload = {
        "type": "context",
        "browser_focused": focused,
        "focus_ts": 1000.0,
        "shorts": None,
        "preview": {
            "tab_id": PREVIEW_TAB,
            "in_front": False,
            "shorts": shorts_state if preview_shorts else None,
        },
    }
    if active_shorts:
        payload["shorts"] = dict(shorts_state, tab_id=7, video_id="activevid001")
    ext.ws.send(json.dumps(payload))


# ---------------------------------------------------------------------- protocol


def test_preview_frames_are_validated() -> None:
    parsed = protocol.parse_preview_frame(frame(5, 1234.5))
    assert (parsed.captured_ms, parsed.number, parsed.jpeg) == (1234.5, 5, JPEG)
    for bad in (
        b"short",
        frame(1, body=b"PNG not jpeg" * 4),
        frame(1, captured_ms=float("nan")),
        frame(1, captured_ms=-5.0),
        frame(1, body=b"\xff\xd8" + b"\x00" * (protocol.MAX_PREVIEW_FRAME_BYTES + 1)),
    ):
        with pytest.raises(protocol.ProtocolError):
            protocol.parse_preview_frame(bad)


def test_preview_context_must_describe_the_preview_tab() -> None:
    message = {
        "type": "context",
        "browser_focused": True,
        "focus_ts": 1.0,
        "shorts": None,
        "preview": {
            "tab_id": 3,
            "in_front": True,
            "shorts": {"tab_id": 4, "is_shorts": True, "visible": True, "has_video": True},
        },
    }
    with pytest.raises(protocol.ProtocolError):
        protocol.parse(json.dumps(message))
    message["preview"]["shorts"]["tab_id"] = 3
    parsed = protocol.parse(json.dumps(message))
    assert parsed.preview.tab_id == 3 and parsed.preview.shorts.tab_id == 3


def test_preview_tab_id_only_on_shorts_commands() -> None:
    rid = uuid.uuid4().hex
    shorts = json.loads(protocol.command_message(rid, "next_short", "abcdefghijk", 1000, 9))
    assert shorts["tab_id"] == 9
    tabs = json.loads(protocol.command_message(rid, "next_browser_tab", None, 1000, 9))
    assert "tab_id" not in tabs
    plain = json.loads(protocol.command_message(rid, "next_short", "abcdefghijk", 1000))
    assert "tab_id" not in plain


# ---------------------------------------------------------------------- connection


def test_preview_connection_needs_the_pairing_code(server) -> None:
    bridge, _, _ = server
    ws = open_preview(bridge.port, token="wrong-token-0000000000")
    with pytest.raises(ConnectionClosed) as info:
        ws.recv(timeout=5)
    assert info.value.rcvd.code == 4001
    assert bridge.preview.status().connected is False


def test_preview_connection_from_a_web_page_is_refused(server) -> None:
    bridge, _, _ = server
    from websockets.exceptions import InvalidStatus

    with pytest.raises(InvalidStatus):
        open_preview(bridge.port, origin="https://www.youtube.com")


def test_frames_are_received_and_only_the_latest_is_kept(server) -> None:
    bridge, _, _ = server
    ws = open_preview(bridge.port)
    assert json.loads(ws.recv(timeout=5))["type"] == "preview_welcome"
    assert wait_until(lambda: bridge.preview.status().connected)
    for number in range(1, 6):
        ws.send(frame(number))
    assert wait_until(lambda: bridge.preview.status().frames == 5)
    status = bridge.preview.status()
    assert status.state == "streaming" and status.live
    assert bridge.preview.latest().number == 5
    assert status.transport_ms is not None and status.transport_ms < 1000
    ws.send(frame(9))  # numbers 6-8 were skipped by the browser
    assert wait_until(lambda: bridge.preview.status().skipped == 3)
    ws.close()
    assert wait_until(lambda: not bridge.preview.status().connected)
    assert bridge.preview.latest() is None


def test_leaving_shorts_removes_the_picture_at_once(server) -> None:
    bridge, _, _ = server
    ws = open_preview(bridge.port)
    ws.recv(timeout=5)
    ws.send(frame(1))
    assert wait_until(lambda: bridge.preview.latest() is not None)
    ws.send(
        json.dumps(
            {
                "type": "preview_state",
                "state": "hidden",
                "reason": "the tab is not showing a YouTube Short",
            }
        )
    )
    assert wait_until(lambda: bridge.preview.status().state == "hidden")
    assert bridge.preview.latest() is None
    assert "not showing" in bridge.preview.status().reason
    ws.close()


def test_app_can_stop_the_preview(server) -> None:
    bridge, _, _ = server
    ws = open_preview(bridge.port)
    ws.recv(timeout=5)
    assert wait_until(lambda: bridge.preview.status().connected)
    assert bridge.stop_preview()
    assert json.loads(ws.recv(timeout=5)) == {"type": "preview_stop"}
    ws.close()


def test_invalid_preview_data_closes_the_connection(server) -> None:
    bridge, _, _ = server
    ws = open_preview(bridge.port)
    ws.recv(timeout=5)
    for _ in range(10):
        try:
            ws.send(b"not a frame at all, and not a jpeg either")
        except ConnectionClosed:
            break
        time.sleep(0.02)
    with pytest.raises(ConnectionClosed):
        ws.recv(timeout=5)
    assert wait_until(lambda: not bridge.preview.status().connected)


def test_a_new_preview_replaces_the_previous_one(server) -> None:
    bridge, _, _ = server
    first = open_preview(bridge.port)
    first.recv(timeout=5)
    second = open_preview(bridge.port)
    second.recv(timeout=5)
    with pytest.raises(ConnectionClosed):
        first.recv(timeout=5)
    second.send(frame(1))
    assert wait_until(lambda: bridge.preview.status().frames == 1)
    second.close()


def test_feed_reports_stale_pictures_as_not_live() -> None:
    clock = [1_000_000.0]
    feed = PreviewFeed(wall_ms=lambda: clock[0])
    feed.attach(lambda: None)
    feed.push(protocol.PreviewFrame(clock[0] - 10, 1, JPEG))
    assert feed.status().live
    clock[0] += 2500
    assert not feed.status().live
    assert feed.status().fps == 0.0


# ---------------------------------------------------------------------- preview control


def test_preview_tab_is_targeted_only_while_the_app_is_in_front(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port, protocol=3)
    # Confirm without a new video id, so the controller does not wait for a page change.
    ext.respond = lambda cmd: {"outcome": "succeeded", "reason": ""}
    try:
        preview_context(ext, focused=False, active_shorts=True)
        assert wait_until(lambda: controller.status().preview)
        # App not in front: the ordinary policy (active Shorts tab, no tab id).
        controller.app_in_front = False
        assert execute_ok(controller)
        assert "tab_id" not in ext.commands[-1]
        assert ext.commands[-1]["video_id"] == "activevid001"
        # App in front: the authorized preview tab, addressed by its id.
        controller.app_in_front = True
        status = controller.status()
        assert status.ready and status.via_preview and status.actively_scrolling
        assert execute_ok(controller)
        assert ext.commands[-1]["tab_id"] == PREVIEW_TAB
        assert ext.commands[-1]["video_id"] == "previewvid01"
    finally:
        ext.close()


def test_tab_switching_never_uses_the_preview_path(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port, protocol=3)
    try:
        preview_context(ext, focused=False)
        assert wait_until(lambda: controller.status().preview)
        controller.app_in_front = True
        result = controller.execute(ActionType.NEXT_BROWSER_TAB, uuid.uuid4().hex, 1.0)
        assert result.status is ActionStatus.REJECTED
        assert result.reason == "the browser is not the active window"
        assert ext.commands == []
    finally:
        ext.close()


def test_previewed_tab_outside_shorts_refuses_shorts_actions(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port, protocol=3)
    try:
        controller.app_in_front = True
        preview_context(ext, preview_shorts=False, active_shorts=True)
        assert wait_until(lambda: controller.status().preview)
        check = controller.check(ActionType.NEXT_SHORT)
        assert not check.ready
        assert check.reason == "the previewed tab is not showing a YouTube Short"
        assert ext.commands == []
    finally:
        ext.close()


def test_without_a_preview_the_app_in_front_changes_nothing(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port, protocol=3)
    try:
        ext.context()
        assert wait_until(lambda: controller.status().ready)
        controller.app_in_front = True
        assert not controller.status().preview
        assert execute_ok(controller)
        assert "tab_id" not in ext.commands[-1]
    finally:
        ext.close()


def execute_ok(controller) -> bool:  # type: ignore[no-untyped-def]
    result = controller.execute(ActionType.NEXT_SHORT, uuid.uuid4().hex, 1.0)
    return result.status is ActionStatus.SUCCEEDED
