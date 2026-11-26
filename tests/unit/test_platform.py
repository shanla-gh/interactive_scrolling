"""Process tuning helpers."""

from __future__ import annotations

import sys

import pytest

from interactive_scrolling.core.platform import disable_power_throttling


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only API")
def test_disable_power_throttling_succeeds_on_windows() -> None:
    assert disable_power_throttling() is True


def test_disable_power_throttling_is_noop_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert disable_power_throttling() is False
