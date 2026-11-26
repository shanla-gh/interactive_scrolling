"""Small defects found in Integration Audit 002.

* Settings: a failed write left its temporary file in the settings folder.
* Bridge: the number of authenticated browser connections was unbounded.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from interactive_scrolling.integrations.youtube import bridge as bridge_module
from interactive_scrolling.integrations.youtube.bridge import ALLOWED_ORIGINS, BridgeServer
from interactive_scrolling.storage import settings_store
from interactive_scrolling.storage.settings_store import SettingsStore, UserSettings
from tests.helpers import wait_until


def test_failed_settings_write_leaves_no_temporary_file(tmp_path: Path, monkeypatch) -> None:
    def broken_dump(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(settings_store.json, "dump", broken_dump)
    store = SettingsStore(tmp_path / "settings.json")
    assert store.save(UserSettings()) is False
    assert list(tmp_path.iterdir()) == []


def test_bridge_limits_simultaneous_connections(monkeypatch) -> None:
    monkeypatch.setattr(bridge_module, "MAX_CONNECTIONS", 2)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    token = "connection-limit-token-000000"
    bridge = BridgeServer(port, token)
    assert bridge.start()
    sockets = []
    try:
        for _ in range(3):
            ws = connect(f"ws://127.0.0.1:{port}/bridge", origin=next(iter(ALLOWED_ORIGINS)))
            ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol": 1,
                        "token": token,
                        "browser": "edge",
                        "extension_version": "t",
                    }
                )
            )
            sockets.append(ws)
        assert json.loads(sockets[0].recv(timeout=3))["type"] == "welcome"
        assert json.loads(sockets[1].recv(timeout=3))["type"] == "welcome"
        with pytest.raises(ConnectionClosed) as info:
            sockets[2].recv(timeout=3)
        assert info.value.rcvd.code == 1013
        assert wait_until(lambda: len(bridge.clients()) == 2)
    finally:
        for ws in sockets:
            ws.close()
        bridge.stop()
