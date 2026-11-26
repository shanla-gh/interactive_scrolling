"""Persistent user settings: round trip, validation and safe fallbacks."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from interactive_scrolling.actions.types import DEFAULT_MAPPING, ActionType
from interactive_scrolling.config.settings import (
    ControlHandPreference,
    GestureSettings,
    SensitivityPreset,
)
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.storage.settings_store import (
    DEFAULT_BRIDGE_PORT,
    SettingsStore,
    UserSettings,
)


def test_first_load_creates_defaults_with_a_pairing_token(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = store.load()
    assert settings.gestures == GestureSettings()
    assert settings.mapping == DEFAULT_MAPPING
    assert settings.analytics_enabled is True
    assert settings.bridge_port == DEFAULT_BRIDGE_PORT
    assert len(settings.pairing_token) >= 16
    assert store.path.is_file()
    assert store.load().pairing_token == settings.pairing_token  # token is stable
    assert store.warnings == []


def test_settings_survive_restart(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    custom = UserSettings(
        gestures=replace(
            GestureSettings.from_preset(SensitivityPreset.HIGH),
            control_hand=ControlHandPreference.LEFT,
            enable_stop=False,
        ),
        mapping={**DEFAULT_MAPPING, GestureType.FINGER_SWIPE_DOWN: ActionType.PREVIOUS_SHORT},
        analytics_enabled=False,
        bridge_port=48001,
        pairing_token="a-custom-pairing-token-123",
    )
    assert store.save(custom)
    loaded = SettingsStore(tmp_path / "settings.json").load()
    assert loaded == custom


def test_invalid_fields_fall_back_individually(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "gestures": {
                    "stop_hold_s": 99,  # out of range
                    "thumbs_up_hold_s": 0.9,  # valid
                    "control_hand": "both",  # invalid enum
                    "enable_stop": "yes",  # wrong type
                    "cooldown_s": True,  # bool is not a number
                },
                "mapping": {
                    "thumbs_up": "switch_to_study_app",  # not allowed
                    "stop_gesture": "none",  # valid
                    "unknown_gesture": "next_short",
                },
                "analytics_enabled": "maybe",
                "bridge_port": 80,
                "pairing_token": "short",
            }
        ),
        encoding="utf-8",
    )
    store = SettingsStore(path)
    settings = store.load()
    assert settings.gestures.stop_hold_s == GestureSettings().stop_hold_s
    assert settings.gestures.thumbs_up_hold_s == 0.9
    assert settings.gestures.control_hand is ControlHandPreference.AUTO
    assert settings.gestures.enable_stop is True
    assert settings.gestures.cooldown_s == GestureSettings().cooldown_s
    assert settings.mapping[GestureType.THUMBS_UP] is ActionType.LIKE_SHORT
    assert settings.mapping[GestureType.STOP_GESTURE] is ActionType.NONE
    assert settings.analytics_enabled is True
    assert settings.bridge_port == DEFAULT_BRIDGE_PORT
    assert len(settings.pairing_token) >= 16
    assert len(store.warnings) >= 8


def test_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ not json", encoding="utf-8")
    store = SettingsStore(path)
    assert store.load().gestures == GestureSettings()
    assert "unreadable" in store.warnings[0]


def test_unwritable_location_reports_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    store = SettingsStore(blocker / "settings.json")  # parent is a file
    assert store.save(UserSettings()) is False


def test_save_is_atomic_and_leaves_no_temporary_files(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    for _ in range(3):
        assert store.save(UserSettings())
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]
