"""The browser bridge and YouTube controller, driven by a scripted Python extension client."""

from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import ClientConnection, connect

from interactive_scrolling.actions.types import ActionStatus, ActionType
from interactive_scrolling.integrations.youtube.bridge import ALLOWED_ORIGINS, BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from tests.helpers import wait_until

TOKEN = "pairing-token-for-tests-0123456789"
ORIGIN = next(iter(ALLOWED_ORIGINS))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server() -> Iterator[tuple[BridgeServer, YouTubeShortsController, list[bool]]]:
    sessions: list[bool] = []
    bridge = BridgeServer(free_port(), TOKEN)
    controller = YouTubeShortsController(bridge, on_shorts_session=sessions.append)
    bridge.set_change_listener(controller.refresh)  # mirror the application wiring
    assert bridge.start()
    yield bridge, controller, sessions
    bridge.stop()


class FakeExtension:
    """Speaks the extension side of the protocol and answers commands with a script."""

    def __init__(
        self,
        port: int,
        token: str = TOKEN,
        origin: str = ORIGIN,
        browser: str = "edge",
        protocol: int = 2,
    ):
        self.ws: ClientConnection = connect(
            f"ws://127.0.0.1:{port}/bridge", origin=origin, open_timeout=5
        )
        self.ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "protocol": protocol,
                    "token": token,
                    "browser": browser,
                    "extension_version": "0.3.0" if protocol >= 2 else "0.2.0",
                }
            )
        )
        self.commands: list[dict] = []
        self.respond = lambda cmd: {
            "outcome": "succeeded",
            "reason": "",
            "video_id_before": "abcdefghijk",
            "video_id_after": "bcdefghijkl",
        }
        self.welcome = json.loads(self.ws.recv(timeout=5))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        try:
            for raw in self.ws:
                message = json.loads(raw)
                if message["type"] == "command":
                    self.commands.append(message)
                    reply = self.respond(message)
                    if reply is not None:
                        self.ws.send(json.dumps({"type": "result", "id": message["id"], **reply}))
        except ConnectionClosed:
            pass

    def context(
        self,
        focus_ts: float = 1000.0,
        visible: bool = True,
        shorts: bool = True,
        loaded: bool = True,
        focused: bool = True,
    ) -> None:
        payload = {
            "type": "context",
            "browser_focused": focused,
            "focus_ts": focus_ts,
            "shorts": None,
        }
        if shorts:
            payload["shorts"] = {
                "tab_id": 1,
                "is_shorts": True,
                "video_id": "abcdefghijk",
                "visible": visible,
                "has_video": True,
                "video_ready": loaded,
                "paused": False,
                "liked": False,
                "signed_in": True,
                "age_ms": 5,
            }
        self.ws.send(json.dumps(payload))

    def close(self) -> None:
        self.ws.close()


def execute(controller: YouTubeShortsController, action=ActionType.NEXT_SHORT, timeout=1.0):
    return controller.execute(action, uuid.uuid4().hex, timeout)


def test_binds_to_loopback_only(server) -> None:
    bridge, _, _ = server
    sock = bridge._server.socket
    assert sock.getsockname()[0] == "127.0.0.1"


@pytest.mark.parametrize(
    "origin", [None, "https://www.youtube.com", "chrome-extension://otherextensionid"]
)
def test_connections_from_other_origins_are_refused(server, origin) -> None:
    bridge, _, _ = server
    with pytest.raises(InvalidStatus) as info:
        connect(f"ws://127.0.0.1:{bridge.port}/bridge", origin=origin, open_timeout=5)
    assert info.value.response.status_code == 403
    assert bridge.clients() == []


def test_wrong_path_is_refused(server) -> None:
    bridge, _, _ = server
    with pytest.raises(InvalidStatus):
        connect(f"ws://127.0.0.1:{bridge.port}/other", origin=ORIGIN, open_timeout=5)


def test_wrong_pairing_code_is_closed_with_4001(server) -> None:
    bridge, _, _ = server
    ws = connect(f"ws://127.0.0.1:{bridge.port}/bridge", origin=ORIGIN, open_timeout=5)
    ws.send(
        json.dumps(
            {
                "type": "hello",
                "protocol": 1,
                "token": "wrong-token-000000000",
                "browser": "edge",
                "extension_version": "0.2.0",
            }
        )
    )
    with pytest.raises(ConnectionClosed) as info:
        ws.recv(timeout=5)
    assert info.value.rcvd.code == 4001
    assert bridge.clients() == []


def test_first_message_must_be_hello(server) -> None:
    bridge, _, _ = server
    ws = connect(f"ws://127.0.0.1:{bridge.port}/bridge", origin=ORIGIN, open_timeout=5)
    ws.send(json.dumps({"type": "context", "browser_focused": True, "focus_ts": 1, "shorts": None}))
    with pytest.raises(ConnectionClosed):
        ws.recv(timeout=5)


def test_authenticated_extension_is_registered(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    try:
        assert ext.welcome == {"type": "welcome", "protocol": 2}
        assert wait_until(lambda: len(bridge.clients()) == 1)
        assert (
            controller.check(ActionType.NEXT_SHORT).reason
            == "waiting for the browser to report its state"
        )
    finally:
        ext.close()


def test_controller_requires_a_visible_shorts_tab(server) -> None:
    bridge, controller, sessions = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context(shorts=False)
        assert wait_until(
            lambda: "no YouTube Shorts tab" in controller.check(ActionType.NEXT_SHORT).reason
        )
        ext.context(visible=False)
        assert wait_until(lambda: "not visible" in controller.check(ActionType.NEXT_SHORT).reason)
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        assert sessions == [True]
    finally:
        ext.close()
    assert wait_until(lambda: sessions == [True, False])


def test_short_that_is_still_loading_is_not_a_target(server) -> None:
    """Regression: YouTube ignores navigation until the active video has loaded; executing
    then always failed. Loading Shorts are now rejected up front."""
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context(loaded=False)
        assert wait_until(
            lambda: controller.check(ActionType.NEXT_SHORT).reason == "the Short is still loading"
        )
        ext.context(loaded=True)
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
    finally:
        ext.close()


def test_command_round_trip_reports_confirmed_success(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        result = execute(controller)
        assert result.status is ActionStatus.SUCCEEDED
        assert result.detail == "active Short changed"
        (command,) = ext.commands
        assert command["action"] == "next_short"
        assert command["video_id"] == "abcdefghijk"
    finally:
        ext.close()


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        ("no_change", ActionStatus.NO_CHANGE),
        ("rejected", ActionStatus.REJECTED),
        ("failed", ActionStatus.FAILED),
        ("unknown", ActionStatus.UNKNOWN),
    ],
)
def test_extension_outcomes_are_passed_through(server, outcome, status) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    ext.respond = lambda cmd: {"outcome": outcome, "reason": "because"}
    try:
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.LIKE_SHORT).ready)
        result = execute(controller, ActionType.LIKE_SHORT)
        assert result.status is status
        assert result.reason == "because"
    finally:
        ext.close()


def test_missing_confirmation_is_unknown_not_success(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    ext.respond = lambda cmd: None  # never answers
    try:
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        started = time.monotonic()
        result = execute(controller, timeout=0.3)
        assert result.status is ActionStatus.UNKNOWN
        assert "no confirmation" in result.reason
        assert time.monotonic() - started < 2.0  # bounded wait
    finally:
        ext.close()


def test_disconnect_during_action_is_unknown(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)

    def drop(cmd):
        threading.Thread(target=ext.close, daemon=True).start()
        return None

    ext.respond = drop
    ext.context()
    assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
    result = execute(controller, timeout=2.0)
    assert result.status is ActionStatus.UNKNOWN
    assert "disconnected" in result.reason
    assert wait_until(
        lambda: controller.check(ActionType.NEXT_SHORT).reason == "browser extension not connected"
    )


def test_cancel_all_releases_waiting_request(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    ext.respond = lambda cmd: None
    try:
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        threading.Timer(0.2, controller.cancel_all).start()
        started = time.monotonic()
        result = execute(controller, timeout=3.0)
        assert result.status is ActionStatus.UNKNOWN
        assert "cancelled" in result.reason
        assert time.monotonic() - started < 1.5
    finally:
        ext.close()


def test_stale_context_is_not_trusted(server, monkeypatch) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        later = time.perf_counter_ns() + 6_000_000_000
        monkeypatch.setattr(controller, "_clock", lambda: later)
        assert "waiting for the browser" in controller.check(ActionType.NEXT_SHORT).reason
    finally:
        ext.close()


def test_most_recently_focused_browser_is_the_single_target(server) -> None:
    bridge, controller, _ = server
    chrome = FakeExtension(bridge.port, browser="chrome")
    edge = FakeExtension(bridge.port, browser="edge")
    try:
        chrome.context(focus_ts=2000)
        edge.context(focus_ts=1000)
        assert wait_until(lambda: controller.status().target_browser == "chrome")
        execute(controller)
        assert len(chrome.commands) == 1 and edge.commands == []
        edge.context(focus_ts=3000)
        assert wait_until(lambda: controller.status().target_browser == "edge")
    finally:
        chrome.close()
        edge.close()


def test_equal_focus_times_are_ambiguous(server) -> None:
    bridge, controller, _ = server
    a = FakeExtension(bridge.port, browser="chrome")
    b = FakeExtension(bridge.port, browser="edge")
    try:
        a.context(focus_ts=5000)
        b.context(focus_ts=5000)
        assert wait_until(
            lambda: "several browsers" in controller.check(ActionType.NEXT_SHORT).reason
        )
    finally:
        a.close()
        b.close()


def test_repeated_invalid_messages_close_the_connection(server) -> None:
    bridge, _, _ = server
    ext = FakeExtension(bridge.port)
    for _ in range(6):
        try:
            ext.ws.send('{"type": "nonsense"}')
        except ConnectionClosed:
            break
    assert wait_until(lambda: bridge.clients() == [])


def test_results_from_another_connection_are_ignored(server) -> None:
    bridge, controller, _ = server
    target = FakeExtension(bridge.port, browser="edge")
    other = FakeExtension(bridge.port, browser="chrome")
    target.respond = lambda cmd: None
    try:
        target.context(focus_ts=9000)
        other.context(focus_ts=1, shorts=False)
        assert wait_until(lambda: controller.status().target_browser == "edge")

        def forge():
            time.sleep(0.1)
            command = target.commands[-1]
            other.ws.send(
                json.dumps({"type": "result", "id": command["id"], "outcome": "succeeded"})
            )

        threading.Thread(target=forge, daemon=True).start()
        result = execute(controller, timeout=0.6)
        assert result.status is ActionStatus.UNKNOWN
    finally:
        target.close()
        other.close()


def test_port_in_use_is_reported() -> None:
    first = BridgeServer(free_port(), TOKEN)
    assert first.start()
    try:
        second = BridgeServer(first.port, TOKEN)
        assert not second.start()
        assert "unavailable" in second.error
        controller = YouTubeShortsController(second)
        assert "unavailable" in controller.check(ActionType.NEXT_SHORT).reason
    finally:
        first.stop()


def test_changing_the_pairing_code_disconnects_clients(server) -> None:
    bridge, _, _ = server
    ext = FakeExtension(bridge.port)
    assert wait_until(lambda: len(bridge.clients()) == 1)
    bridge.set_token("a-brand-new-pairing-code-000")
    assert wait_until(lambda: bridge.clients() == [])
    ext.close()


# ---------------------------------------------------------------------- tab navigation


def tab_reply(before: int, after: int | None, count: int, outcome: str = "succeeded"):
    reply = {"outcome": outcome, "reason": "", "tab_index_before": before, "tab_count": count}
    if after is not None:
        reply["tab_index_after"] = after
    return lambda cmd: reply


def test_tab_navigation_works_without_a_shorts_tab(server) -> None:
    # The user left Shorts: Shorts actions are refused, tab navigation still works.
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    ext.respond = tab_reply(1, 2, 4)
    ext.context(shorts=False)
    assert wait_until(lambda: controller.check(ActionType.NEXT_BROWSER_TAB).ready)
    assert not controller.check(ActionType.NEXT_SHORT).ready
    result = execute(controller, ActionType.NEXT_BROWSER_TAB)
    assert result.status is ActionStatus.SUCCEEDED
    assert result.detail == "tab 3 of 4 active"
    command = ext.commands[-1]
    assert command["action"] == "next_browser_tab"
    assert command["video_id"] is None  # tab commands carry no page data
    ext.close()


def test_tab_navigation_requires_the_browser_to_be_the_active_window(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    ext.context(focused=False)
    assert wait_until(lambda: bridge.clients() and bridge.clients()[0].context is not None)
    check = controller.check(ActionType.PREVIOUS_BROWSER_TAB)
    assert not check.ready
    assert check.reason == "the browser is not the active window"
    assert execute(controller, ActionType.PREVIOUS_BROWSER_TAB).status is ActionStatus.REJECTED
    assert ext.commands == []
    ext.close()


def test_tab_navigation_targets_only_the_focused_browser(server) -> None:
    bridge, controller, _ = server
    edge = FakeExtension(bridge.port, browser="edge")
    chrome = FakeExtension(bridge.port, browser="chrome")
    edge.respond = tab_reply(0, 1, 2)
    chrome.respond = tab_reply(0, 1, 2)
    edge.context(focus_ts=1000.0, focused=False, shorts=False)
    chrome.context(focus_ts=2000.0, focused=True, shorts=False)
    assert wait_until(lambda: controller.check(ActionType.NEXT_BROWSER_TAB).ready)
    assert execute(controller, ActionType.NEXT_BROWSER_TAB).status is ActionStatus.SUCCEEDED
    assert len(chrome.commands) == 1 and edge.commands == []
    edge.close()
    chrome.close()


def test_last_tab_is_reported_as_rejected_without_wrapping(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    ext.respond = lambda cmd: {
        "outcome": "rejected",
        "reason": "already at the last tab",
        "tab_index_before": 3,
        "tab_count": 4,
    }
    ext.context(shorts=False)
    assert wait_until(lambda: controller.check(ActionType.NEXT_BROWSER_TAB).ready)
    result = execute(controller, ActionType.NEXT_BROWSER_TAB)
    assert result.status is ActionStatus.REJECTED
    assert result.reason == "already at the last tab"
    ext.close()


def test_outdated_extension_cannot_switch_tabs_but_still_controls_shorts(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port, protocol=1)
    ext.context()
    assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
    check = controller.check(ActionType.NEXT_BROWSER_TAB)
    assert not check.ready and "outdated" in check.reason
    ext.close()


def test_tab_result_with_invalid_index_is_rejected_by_the_schema(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    ext.respond = lambda cmd: {"outcome": "succeeded", "reason": "", "tab_index_after": -5}
    ext.context(shorts=False)
    assert wait_until(lambda: controller.check(ActionType.NEXT_BROWSER_TAB).ready)
    # The malformed confirmation is discarded, so the outcome is unknown, never success.
    result = execute(controller, ActionType.NEXT_BROWSER_TAB, timeout=0.3)
    assert result.status is ActionStatus.UNKNOWN
    ext.close()
