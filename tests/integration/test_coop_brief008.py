"""Doomscroll Together (Co-op Lite) hardening, Brief 008: private networks only, invitations,
plain-language refusals, rate limiting and reconnection. Loopback only (no second computer).
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from interactive_scrolling.integrations.coop import protocol as p
from interactive_scrolling.integrations.coop import session as s
from interactive_scrolling.integrations.coop.session import (
    CoopError,
    CoopGuest,
    CoopHost,
    friendly_error,
    invitation_text,
    network_kind,
    parse_invitation,
    peer_allowed,
)
from tests.helpers import wait_until
from tests.integration.test_coop import join, pair  # noqa: F401 - fixture


@pytest.mark.parametrize(
    ("address", "kind"),
    [
        ("192.168.1.20", "local"),
        ("10.0.0.5", "local"),
        ("172.16.4.1", "local"),
        ("169.254.10.10", "local"),
        ("100.101.102.103", "vpn"),
        ("127.0.0.1", "loopback"),
        ("8.8.8.8", "public"),
        ("100.128.0.1", "public"),  # just outside the 100.64.0.0/10 VPN range
        ("not an address", "public"),
    ],
)
def test_network_kinds(address: str, kind: str) -> None:
    assert network_kind(address) == kind
    assert peer_allowed(address) is (kind != "public")


def test_host_refuses_to_listen_on_a_public_address() -> None:
    from interactive_scrolling.actions.dispatcher import ActionDispatcher

    dispatcher = ActionDispatcher(None)
    host = CoopHost(dispatcher, "Alex", port=0)
    try:
        with pytest.raises(ValueError, match="private network"):
            host.start(bind="8.8.8.8")
        assert not host.active
    finally:
        host.stop()
        dispatcher.shutdown()


def test_invitation_round_trip() -> None:
    code = p.new_session_code()
    text = invitation_text("Alex", "100.101.1.2", 47816, code)
    assert parse_invitation(text) == ("100.101.1.2", 47816, code)
    # Pasted from a chat with extra words and a lower-case code.
    messy = f"hey! address 192.168.0.7 port 50000 code {code.lower().replace('-', '')}"
    address, port, found = parse_invitation(messy)
    assert (address, port) == ("192.168.0.7", 50000)
    assert p.normalize_code(found) == p.normalize_code(code)
    assert parse_invitation("nothing here") == (None, None, None)


def test_wrong_code_is_explained_in_plain_words(pair) -> None:  # noqa: F811
    host, guest, _code, *_ = pair
    wrong = p.new_session_code()
    with pytest.raises(CoopError) as info:
        guest.connect("127.0.0.1", host.port, wrong)
    assert str(info.value) == "The session code is not correct. Check the invitation."
    assert info.value.friendly


def test_malformed_code_is_explained_before_connecting() -> None:
    with pytest.raises(CoopError) as info:
        CoopGuest("Sam").connect("127.0.0.1", 9, "short")
    assert "16 letters" in str(info.value)


def test_unreachable_host_is_explained_without_a_socket_error() -> None:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # nothing listens here once closed
    with pytest.raises(CoopError) as info:
        CoopGuest("Sam").connect("127.0.0.1", port, p.new_session_code(), timeout_s=2.0)
    message = str(info.value)
    # Windows reports a closed loopback port as refused after retries, or as a timeout.
    assert "not available" in message or "timed out" in message, message
    assert "Errno" not in message and "WinError" not in message


def test_friendly_errors_cover_timeouts_and_bad_addresses() -> None:
    assert "timed out" in friendly_error(TimeoutError("timed out"))
    assert "not valid" in friendly_error(OSError("[Errno 11001] getaddrinfo failed"))
    assert "cannot be reached" in friendly_error(OSError("[WinError 10065] host unreachable"))


def test_expired_invitation_is_refused_and_can_be_renewed(pair) -> None:  # noqa: F811
    host, guest, code, *_ = pair
    host._code_since -= s.INVITE_TTL_S + 1
    assert host.status().invitation_expired
    with pytest.raises(CoopError) as info:
        guest.connect("127.0.0.1", host.port, code)
    assert "expired" in str(info.value)
    new_code = host.renew_invitation()
    assert new_code != code
    guest.connect("127.0.0.1", host.port, new_code)
    assert wait_until(lambda: host.status().pending_approval)


def test_guest_name_equal_to_host_name_is_explained(pair) -> None:  # noqa: F811
    host, _guest, code, *_ = pair
    with pytest.raises(CoopError) as info:
        CoopGuest("Host").connect("127.0.0.1", host.port, code)
    assert "Choose another name" in str(info.value)


def test_guest_requests_are_rate_limited(pair) -> None:  # noqa: F811
    host, guest, code, _browser, host_dispatcher, guest_dispatcher = pair
    from interactive_scrolling.actions.types import ControlMode

    host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    join(host, guest, code, guest_dispatcher)
    replies: list[str] = []
    original = host._reply

    def capture(request_id: str, outcome: str, reason: str) -> None:
        replies.append(reason)
        original(request_id, outcome, reason)

    host._reply = capture  # type: ignore[method-assign]
    for _ in range(s.MAX_ACTIONS_PER_S + 3):
        guest._send({"type": "action", "id": uuid.uuid4().hex, "action": "toggle_playback"})
    assert wait_until(lambda: replies.count("too many requests") >= 3, timeout_s=3)


def test_guest_reconnects_after_a_dropped_connection_without_new_approval(pair) -> None:  # noqa: F811
    host, guest, code, _browser, _host_dispatcher, guest_dispatcher = pair
    join(host, guest, code, guest_dispatcher)
    # The network drops the connection: no close frame reaches the guest.
    host._guest.socket.close()
    assert wait_until(lambda: guest.reconnects == 1, timeout_s=10), guest.state
    assert wait_until(lambda: guest.approved and host.status().approved, timeout_s=5)
    assert host.status().peer == "Player 2"


def test_no_reconnect_after_the_host_removes_the_guest(pair) -> None:  # noqa: F811
    host, guest, code, _browser, _host_dispatcher, guest_dispatcher = pair
    join(host, guest, code, guest_dispatcher)
    host.approve(False)  # "Remove"
    assert wait_until(lambda: not guest.connected, timeout_s=5)
    time.sleep(s.RECONNECT_INTERVAL_S + 0.5)
    assert guest.reconnects == 0 and host.status().peer is None


def test_unexpected_protocol_version_is_explained(pair) -> None:  # noqa: F811
    from websockets.exceptions import ConnectionClosed
    from websockets.sync.client import connect

    host, *_ = pair
    ws = connect(f"ws://127.0.0.1:{host.port}/coop", open_timeout=5)
    ws.send(json.dumps({"type": "hello", "v": 99, "name": "Sam", "nonce": "0" * 32, "ms": 1}))
    with pytest.raises(ConnectionClosed) as info:
        ws.recv(timeout=5)
    assert info.value.rcvd.code == s.CLOSE_VERSION
    assert "different version" in s.refusal_message(s.CLOSE_VERSION, "")


def test_removed_guest_is_told_and_does_not_reconnect(pair) -> None:  # noqa: F811
    host, guest, code, _browser, _hd, guest_dispatcher = pair
    join(host, guest, code, guest_dispatcher)
    host.remove_guest()
    assert wait_until(lambda: not guest.connected, timeout_s=5)
    assert "removed you" in guest.state
    time.sleep(s.RECONNECT_INTERVAL_S + 0.5)
    assert guest.reconnects == 0 and host.status().peer is None and host.active
