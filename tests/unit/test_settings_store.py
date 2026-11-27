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
    SETTINGS_VERSION,
    VERTICAL_DIRECTION_NOTICE,
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
        mapping={**DEFAULT_MAPPING, GestureType.INDEX_SWIPE_DOWN: ActionType.PREVIOUS_SHORT},
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
                "version": 2,
                "gestures": {
                    "stop_hold_s": 99,  # out of range
                    "half_heart_hold_s": 0.9,  # valid
                    "control_hand": "both",  # invalid enum
                    "enable_stop": "yes",  # wrong type
                    "cooldown_s": True,  # bool is not a number
                },
                "mapping": {
                    "half_heart": "open_calculator",  # not an action
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
    assert settings.gestures.half_heart_hold_s == 0.9
    assert settings.gestures.control_hand is ControlHandPreference.AUTO
    assert settings.gestures.enable_stop is True
    assert settings.gestures.cooldown_s == GestureSettings().cooldown_s
    assert settings.mapping[GestureType.HALF_HEART] is ActionType.LIKE_SHORT
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


def test_version_1_settings_are_migrated_without_losing_user_choices(tmp_path: Path) -> None:
    """A 0.2 settings file: renamed fields keep their values, removed actions take the new
    defaults, values at an old default take the new default, and the file is backed up."""
    path = tmp_path / "settings.json"
    v1 = {
        "version": 1,
        "gestures": {
            "preset": "custom",
            "finger_swipe_min_distance_palms": 0.95,
            "finger_swipe_min_speed_palms_s": 2.4,
            "hand_sweep_min_distance_palms": 0.75,
            "thumbs_up_hold_s": 0.7,
            "cooldown_s": 0.6,  # the version 1 default
            "return_window_s": 1.4,  # customized
            "control_hand": "left",
            "enable_finger_swipes": True,
            "enable_hand_sweeps": False,
            "enable_thumbs_up": True,
            "enable_stop": False,
        },
        "mapping": {
            "finger_swipe_down": "previous_short",
            "finger_swipe_up": "next_short",
            "hand_swipe_right": "switch_to_study_app",
            "hand_swipe_left": "return_to_social_app",
            "thumbs_up": "like_short",
            "stop_gesture": "toggle_playback",
        },
        "analytics_enabled": False,
        "bridge_port": 48002,
        "pairing_token": "an-existing-pairing-token",
    }
    path.write_text(json.dumps(v1), encoding="utf-8")
    store = SettingsStore(path)
    settings = store.load()
    g = settings.gestures
    assert g.preset is SensitivityPreset.CUSTOM
    assert g.swipe_min_distance_palms == 0.95
    assert g.swipe_min_speed_palms_s == 2.4
    assert g.half_heart_hold_s == 0.7
    assert g.cooldown_s == GestureSettings().cooldown_s
    assert g.return_window_s == 1.4
    assert g.control_hand is ControlHandPreference.LEFT
    assert (g.enable_swipe_down, g.enable_swipe_up) == (True, True)
    assert (g.enable_swipe_left, g.enable_swipe_right) == (False, False)
    assert g.enable_half_heart is True and g.enable_stop is False
    m = settings.mapping
    assert m[GestureType.INDEX_SWIPE_DOWN] is ActionType.PREVIOUS_SHORT
    assert m[GestureType.INDEX_SWIPE_UP] is ActionType.NEXT_SHORT
    assert m[GestureType.INDEX_SWIPE_RIGHT] is ActionType.NEXT_BROWSER_TAB
    assert m[GestureType.INDEX_SWIPE_LEFT] is ActionType.PREVIOUS_BROWSER_TAB
    assert m[GestureType.HALF_HEART] is ActionType.LIKE_SHORT
    assert settings.analytics_enabled is False
    assert settings.bridge_port == 48002
    assert settings.pairing_token == "an-existing-pairing-token"
    assert store.warnings == []
    assert store.migrations
    backup = tmp_path / "settings.json.v1-backup"
    assert json.loads(backup.read_text(encoding="utf-8")) == v1
    # Saving writes the current version; loading it again needs no migration.
    assert store.save(settings)
    again = SettingsStore(path)
    assert again.load() == settings
    assert again.migrations == []
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == SETTINGS_VERSION
    assert json.loads(backup.read_text(encoding="utf-8")) == v1


def _v2_file(path: Path, mapping: dict) -> None:
    path.write_text(
        json.dumps(
            {"version": 2, "mapping": mapping, "pairing_token": "an-existing-pairing-token"}
        ),
        encoding="utf-8",
    )


def test_version_2_default_vertical_mapping_becomes_finger_up_next(tmp_path: Path) -> None:
    """Brief 004: the Director moves the finger up to see the next Short. The untouched old
    default (down = next) is migrated once, with a notice."""
    path = tmp_path / "settings.json"
    _v2_file(
        path,
        {
            "index_swipe_down": "next_short",
            "index_swipe_up": "previous_short",
            "half_heart": "like_short",
        },
    )
    store = SettingsStore(path)
    settings = store.load()
    assert settings.mapping[GestureType.INDEX_SWIPE_UP] is ActionType.NEXT_SHORT
    assert settings.mapping[GestureType.INDEX_SWIPE_DOWN] is ActionType.PREVIOUS_SHORT
    assert store.migrations == [VERTICAL_DIRECTION_NOTICE]
    assert store.save(settings)
    again = SettingsStore(path)
    assert again.load().mapping == settings.mapping
    assert again.migrations == []


def test_version_2_customised_vertical_mapping_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _v2_file(path, {"index_swipe_down": "like_short", "index_swipe_up": "previous_short"})
    store = SettingsStore(path)
    settings = store.load()
    assert settings.mapping[GestureType.INDEX_SWIPE_DOWN] is ActionType.LIKE_SHORT
    assert settings.mapping[GestureType.INDEX_SWIPE_UP] is ActionType.PREVIOUS_SHORT
    assert store.migrations == []
