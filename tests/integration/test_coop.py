"""Two-person Co-op over loopback: host and guest objects in this process (one test also runs
the guest in a separate OS process). Loopback is not a two-laptop network test; that one is in
the Director checklist."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import (
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
    ControlMode,
)
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.integrations.coop import protocol as p
from interactive_scrolling.integrations.coop.session import (
    CoopError,
    CoopGuest,
    CoopGuestController,
    CoopHost,
)
from interactive_scrolling.vision.landmarks import Handedness
from tests.helpers import wait_until

G = GestureType


class Browser:
    """The host's browser: executes and confirms every action after ``delay_s``."""

    def __init__(self, delay_s: float = 0.05) -> None:
        self.delay_s = delay_s
        self.executed: list[ActionType] = []
        self.lock = threading.Lock()

    def check(self, action: ActionType) -> ControllerCheck:
        return ControllerCheck(True)

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        time.sleep(self.delay_s)
        with self.lock:
            self.executed.append(action)
        return ActionResult(ActionStatus.SUCCEEDED)

    def cancel_all(self) -> None:
        pass


def event(gesture: GestureType) -> GestureEvent:
    return GestureEvent(gesture, time.perf_counter_ns(), 1, Handedness.RIGHT)


@pytest.fixture
def pair():
    browser = Browser()
    host_dispatcher = ActionDispatcher(browser)
    host = CoopHost(host_dispatcher, "Host", port=0, bind="127.0.0.1", shared_cooldown_s=0.5)
    code = host.start()
    guest = CoopGuest("Player 2")
    guest_dispatcher = ActionDispatcher(None)
    yield host, guest, code, browser, host_dispatcher, guest_dispatcher
    guest.disconnect()
    host.stop()
    host_dispatcher.shutdown()
    guest_dispatcher.shutdown()


def join(host, guest, code, guest_dispatcher, approve: bool = True) -> None:
    guest.connect("127.0.0.1", host.port, code)
    assert wait_until(lambda: host.status().pending_approval)
    assert host.status().peer == "Player 2"
    if approve:
        host.approve()
        assert wait_until(lambda: guest.approved)
    guest_dispatcher.set_controller(CoopGuestController(guest))
    guest_dispatcher.set_mode(ControlMode.LIVE_CONTROL)


def final(records, record_id):
    for r in reversed(records):
        if r.record_id == record_id and r.status.final:
            return r
    return None


def test_session_codes_are_random_and_validated() -> None:
    codes = {p.new_session_code() for _ in range(50)}
    assert len(codes) == 50
    code = next(iter(codes))
    assert len(code) == 19 and p.normalize_code(code.lower()) == code.replace("-", "")
    with pytest.raises(p.CoopProtocolError):
        p.normalize_code("short")
    with pytest.raises(p.CoopProtocolError):
        p.valid_name("<script>")


def test_wrong_code_is_refused(pair) -> None:
    host, guest, _code, *_ = pair
    wrong = p.new_session_code()
    with pytest.raises(CoopError):
        guest.connect("127.0.0.1", host.port, wrong)
    assert host.status().peer is None


def test_repeated_wrong_codes_end_the_session(pair) -> None:
    host, *_ = pair
    for _ in range(5):
        with pytest.raises(CoopError):
            CoopGuest("Mallory").connect("127.0.0.1", host.port, p.new_session_code())
    assert wait_until(lambda: not host.active)
    assert "too many wrong session codes" in host.status().state


def test_guest_controls_the_host_feed_only_after_approval(pair) -> None:
    host, guest, code, browser, host_dispatcher, guest_dispatcher = pair
    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    records = []
    guest_dispatcher.add_record_listener(records.append)
    join(host, guest, code, guest_dispatcher, approve=False)
    early = guest_dispatcher.submit(event(G.INDEX_SWIPE_UP))
    assert wait_until(lambda: final(records, early.record_id) is not None)
    assert "approve" in final(records, early.record_id).reason
    host.approve()
    assert wait_until(lambda: guest.approved)
    record = guest_dispatcher.submit(event(G.INDEX_SWIPE_UP))
    assert wait_until(lambda: final(records, record.record_id) is not None, timeout_s=5)
    done = final(records, record.record_id)
    assert done.status is ActionStatus.SUCCEEDED, done
    assert browser.executed == [ActionType.NEXT_SHORT]
    status = host.status()
    assert status.last is not None and status.last.by == "Player 2"
    assert status.last.outcome == "succeeded"
    assert ("Player 2", "guest", 1) in status.participants
    assert wait_until(lambda: guest.last is not None and guest.last.by == "Player 2")


def test_guest_cannot_like_or_switch_tabs_on_the_host(pair) -> None:
    host, guest, code, browser, host_dispatcher, guest_dispatcher = pair
    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    records = []
    guest_dispatcher.add_record_listener(records.append)
    join(host, guest, code, guest_dispatcher)
    for gesture in (G.HALF_HEART, G.INDEX_SWIPE_RIGHT):
        record = guest_dispatcher.submit(event(gesture))
        assert wait_until(lambda r=record: final(records, r.record_id) is not None)
        assert "not shared" in final(records, record.record_id).reason
    # Even a hand-crafted, correctly signed request for a like is refused by the host.
    result = guest.request(ActionType.LIKE_SHORT, uuid.uuid4().hex, 1.0)
    assert result.status is ActionStatus.REJECTED and "not a shared action" in result.reason
    assert browser.executed == []


def test_simultaneous_gestures_execute_once(pair) -> None:
    host, guest, code, browser, host_dispatcher, guest_dispatcher = pair
    browser.delay_s = 0.2
    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    join(host, guest, code, guest_dispatcher)
    threads = [
        threading.Thread(target=lambda: host_dispatcher.submit(event(G.INDEX_SWIPE_UP))),
        threading.Thread(target=lambda: guest_dispatcher.submit(event(G.INDEX_SWIPE_UP))),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    time.sleep(1.0)
    assert browser.executed == [ActionType.NEXT_SHORT]
    assert host.status().last is not None


def test_shared_cooldown_rejects_a_second_action_right_after_the_first(pair) -> None:
    host, guest, code, browser, host_dispatcher, guest_dispatcher = pair
    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    records = []
    guest_dispatcher.add_record_listener(records.append)
    join(host, guest, code, guest_dispatcher)
    host_dispatcher.submit(event(G.INDEX_SWIPE_UP))
    assert wait_until(lambda: browser.executed == [ActionType.NEXT_SHORT])
    record = guest_dispatcher.submit(event(G.INDEX_SWIPE_DOWN))
    assert wait_until(lambda: final(records, record.record_id) is not None)
    assert "shared cooldown" in final(records, record.record_id).reason
    time.sleep(0.6)
    record = guest_dispatcher.submit(event(G.INDEX_SWIPE_DOWN))
    assert wait_until(lambda: final(records, record.record_id) is not None)
    assert final(records, record.record_id).status is ActionStatus.SUCCEEDED


def test_host_can_switch_off_shared_control_and_emergency_disable_blocks_guests(pair) -> None:
    host, guest, code, browser, host_dispatcher, guest_dispatcher = pair
    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    records = []
    guest_dispatcher.add_record_listener(records.append)
    join(host, guest, code, guest_dispatcher)
    host.set_shared_control(False)
    assert wait_until(lambda: not guest.shared_control)
    record = guest_dispatcher.submit(event(G.INDEX_SWIPE_UP))
    assert wait_until(lambda: final(records, record.record_id) is not None)
    assert "shared control is off" in final(records, record.record_id).reason
    host.set_shared_control(True)
    assert wait_until(lambda: guest.shared_control)
    host_dispatcher.emergency_disable()
    record = guest_dispatcher.submit(event(G.INDEX_SWIPE_UP))
    assert wait_until(lambda: final(records, record.record_id) is not None)
    assert final(records, record.record_id).status is ActionStatus.NOT_EXECUTED
    assert browser.executed == []


def test_replayed_duplicate_and_stale_requests_are_rejected(pair) -> None:
    host, guest, code, browser, host_dispatcher, guest_dispatcher = pair
    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    join(host, guest, code, guest_dispatcher)
    request_id = uuid.uuid4().hex
    assert guest.request(ActionType.NEXT_SHORT, request_id, 2.0).status is ActionStatus.SUCCEEDED
    time.sleep(0.6)
    duplicate = guest.request(ActionType.NEXT_SHORT, request_id, 1.0)
    assert duplicate.status is ActionStatus.REJECTED and "duplicate" in duplicate.reason
    # Stale: a request stamped 5 s in the past (e.g. delayed on the network).
    real_clock = guest._clock
    guest._clock = lambda: real_clock() - 5.0
    stale = guest.request(ActionType.NEXT_SHORT, uuid.uuid4().hex, 1.0)
    guest._clock = real_clock
    assert stale.status is ActionStatus.REJECTED and "stale" in stale.reason
    assert browser.executed == [ActionType.NEXT_SHORT]


def test_forged_or_replayed_messages_close_the_connection(pair) -> None:
    host, guest, code, browser, host_dispatcher, guest_dispatcher = pair
    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    join(host, guest, code, guest_dispatcher)
    ws = guest._ws
    forged = json.dumps(
        {
            "type": "action",
            "id": uuid.uuid4().hex,
            "action": "next_short",
            "seq": 999,
            "ms": int(time.time() * 1000),
            "mac": "0" * 64,
        }
    )
    for _ in range(5):
        ws.send(forged)
    assert wait_until(lambda: host.status().peer is None, timeout_s=5)
    assert browser.executed == []


def test_unauthenticated_clients_cannot_send_actions(pair) -> None:
    host, *_ = pair
    ws = connect(f"ws://127.0.0.1:{host.port}/coop", open_timeout=5)
    ws.send(json.dumps({"type": "action", "action": "next_short"}))
    with pytest.raises(ConnectionClosed):
        ws.recv(timeout=3)
    assert host.status().peer is None


def test_only_one_guest_can_join(pair) -> None:
    host, guest, code, _browser, _hd, guest_dispatcher = pair
    join(host, guest, code, guest_dispatcher)
    with pytest.raises(CoopError):
        CoopGuest("Third").connect("127.0.0.1", host.port, code)


def test_host_shutdown_and_disconnects_are_reported(pair) -> None:
    host, guest, code, _browser, _host_dispatcher, guest_dispatcher = pair
    join(host, guest, code, guest_dispatcher)
    host.stop()
    assert wait_until(lambda: not guest.connected, timeout_s=5)
    assert "disconnected" in guest.status().state
    check = CoopGuestController(guest).check(ActionType.NEXT_SHORT)
    assert not check.ready and "not connected" in check.reason


def test_guest_in_a_separate_process(tmp_path) -> None:
    """A real second application process joins over TCP (loopback) and skips the Short."""
    browser = Browser()
    dispatcher = ActionDispatcher(browser)
    dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    host = CoopHost(dispatcher, "Host", port=0, bind="127.0.0.1")
    code = host.start()
    script = tmp_path / "guest.py"
    script.write_text(
        "import sys, uuid, time\n"
        "from interactive_scrolling.actions.types import ActionType\n"
        "from interactive_scrolling.integrations.coop.session import CoopGuest\n"
        "g = CoopGuest('Remote')\n"
        "g.connect('127.0.0.1', int(sys.argv[1]), sys.argv[2])\n"
        "deadline = time.time() + 10\n"
        "while not g.approved and time.time() < deadline: time.sleep(0.05)\n"
        "r = g.request(ActionType.NEXT_SHORT, uuid.uuid4().hex, 3.0)\n"
        "print(r.status.value)\n"
        "g.disconnect()\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, str(script), str(host.port), code],
        stdout=subprocess.PIPE,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    try:
        assert wait_until(lambda: host.status().pending_approval, timeout_s=15)
        host.approve()
        out, _ = process.communicate(timeout=20)
        assert out.strip().splitlines()[-1] == "succeeded"
        assert browser.executed == [ActionType.NEXT_SHORT]
        assert ("Remote", "guest", 1) in host.status().participants
    finally:
        process.kill()
        host.stop()
        dispatcher.shutdown()
