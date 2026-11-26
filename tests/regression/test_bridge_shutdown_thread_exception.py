"""Defect: stopping the browser bridge raised an unhandled OSError in its server thread.

Found in Integration Audit 002 (a full test run reported PytestUnhandledThreadExceptionWarning):
on Windows, shutting down the websockets server can close the listening socket while
``select()`` waits on it (``OSError: [WinError 10038]``), which killed the server thread with a
traceback at application exit. The race is timing dependent, so the test reproduces the exact
exception deterministically. Fix: the error is expected during an intentional stop; an
unexpected stop is still logged and reported through ``BridgeServer.error``.
"""

from __future__ import annotations

import threading

from interactive_scrolling.integrations.youtube.bridge import BridgeServer


class ServerClosedDuringSelect:
    def serve_forever(self) -> None:
        raise OSError(10038, "An operation was attempted on something that is not a socket")


def run_serve(bridge: BridgeServer) -> list[threading.ExceptHookArgs]:
    errors: list[threading.ExceptHookArgs] = []
    previous = threading.excepthook
    threading.excepthook = errors.append
    try:
        thread = threading.Thread(target=bridge._serve, args=(ServerClosedDuringSelect(),))
        thread.start()
        thread.join(timeout=3)
    finally:
        threading.excepthook = previous
    return errors


def test_socket_closed_during_intentional_stop_is_not_an_error() -> None:
    bridge = BridgeServer(0, "token-for-shutdown-test-0000")
    bridge._stopping = True
    assert run_serve(bridge) == []
    assert bridge.error is None


def test_unexpected_server_failure_is_reported_not_swallowed() -> None:
    bridge = BridgeServer(0, "token-for-shutdown-test-0000")
    bridge._stopping = False
    assert run_serve(bridge) == []  # logged, not an unhandled thread exception
    assert bridge.error == "bridge stopped unexpectedly"
