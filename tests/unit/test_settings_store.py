"""Persistent user settings: round trip, validation and safe fallbacks."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from interactive_scrolling.actions.types import DEFAULT_MAPPING, ActionType
from interactive_scrolling.config.settings import (
    ControlHandPreference,
    GestureSettings,
    SensitivityPreset,
)
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.storage.settings_store import (
    DEFAULT_BRIDGE_PORT,
    MOTION_STYLE_NOTICE,
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


def test_named_preset_follows_the_current_preset_values(tmp_path: Path) -> None:
    """A stored named preset carries the values of the version that saved it; the thresholds
    are re-derived from the preset so improved defaults apply (Brief 004: half-heart hold
    0.6 -> 0.5 s). The hand and the enabled gestures are kept."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 3,
                "gestures": {
                    "preset": "balanced",
                    "half_heart_hold_s": 0.6,
                    "control_hand": "left",
                    "enable_stop": False,
                },
                "pairing_token": "an-existing-pairing-token",
            }
        ),
        encoding="utf-8",
    )
    g = SettingsStore(path).load().gestures
    assert g.half_heart_hold_s == GestureSettings().half_heart_hold_s
    assert g.control_hand is ControlHandPreference.LEFT
    assert g.enable_stop is False


def test_custom_preset_keeps_its_values(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 3,
                "gestures": {"preset": "custom", "half_heart_hold_s": 0.7},
                "pairing_token": "an-existing-pairing-token",
            }
        ),
        encoding="utf-8",
    )
    assert SettingsStore(path).load().gestures.half_heart_hold_s == 0.7


def test_version_04_calibration_that_raised_thresholds_is_repaired(tmp_path: Path) -> None:
    """The Director's 0.4 calibration stored 1.34 hand lengths and 2.5 hand lengths/s."""
    from interactive_scrolling.storage.settings_store import CALIBRATION_REPAIR_NOTICE

    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 3,
                "gestures": {
                    "preset": "personal",
                    "swipe_min_distance_palms": 1.34,
                    "swipe_min_speed_palms_s": 2.5,
                    "swipe_horizontal_distance_palms": 0.8,
                    "swipe_max_duration_s": 1.0,
                },
                "calibration": {"created": "2026-11-27T09:51", "heart_hook": 0.127},
                "pairing_token": "an-existing-pairing-token",
            }
        ),
        encoding="utf-8",
    )
    store = SettingsStore(path)
    g = store.load().gestures
    assert g.swipe_min_distance_palms == 0.8 and g.swipe_min_speed_palms_s == 2.0
    assert g.swipe_max_duration_s == 1.0  # values that only relaxed recognition are kept
    assert store.migrations == [CALIBRATION_REPAIR_NOTICE]
    assert store.load().calibration.heart_hook == 0.127


def test_new_calibration_is_not_touched(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 4,
                "gestures": {"preset": "personal", "swipe_min_distance_palms": 0.9},
                "calibration": {"method": 2},
                "pairing_token": "an-existing-pairing-token",
            }
        ),
        encoding="utf-8",
    )
    store = SettingsStore(path)
    assert store.load().gestures.swipe_min_distance_palms == 0.9
    assert store.migrations == []


def test_control_style_survives_a_named_preset(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 5,
                "gestures": {
                    "preset": "balanced",
                    "control_style": "finger",
                    "enable_palm_swipes": True,
                },
                "pairing_token": "an-existing-pairing-token",
            }
        ),
        encoding="utf-8",
    )
    g = SettingsStore(path).load().gestures
    assert g.control_style == "finger" and g.enable_palm_swipes is True


@pytest.mark.parametrize("style", ["finger", "fist", "hybrid"])
def test_version_4_swipe_styles_become_any_hand_shape_with_a_notice(
    tmp_path: Path, style: str
) -> None:
    """Brief 006: one motion engine for every hand shape replaces the 0.5 styles (finger was
    the default), so every 0.5 file moves to it once and the user is told how to go back."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 4,
                "gestures": {"control_style": style, "enable_palm_swipes": True},
                "pairing_token": "an-existing-pairing-token",
            }
        ),
        encoding="utf-8",
    )
    store = SettingsStore(path)
    g = store.load().gestures
    assert g.control_style == "motion" and g.enable_palm_swipes is False
    assert MOTION_STYLE_NOTICE in store.migrations
    store.save(store.load())
    again = SettingsStore(path)
    again.load()
    assert MOTION_STYLE_NOTICE not in again.migrations


# ---------------------------------------------------------------- Brief 010: workspace and themes


def test_brief_009_settings_migrate_to_the_cinema_workspace(tmp_path: Path) -> None:
    """A 0.9.0b1 file (no theme, the removed Now playing toggle) keeps the user's choices and
    gets the documented defaults for the new options."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": SETTINGS_VERSION,
                "pairing_token": "x" * 32,
                "appearance": {"console_expanded": True, "show_now_playing": False},
                "creator": {"transparent_background": True},
            }
        ),
        encoding="utf-8",
    )
    settings = SettingsStore(path).load()
    a = settings.appearance
    assert a.theme == "black"  # the existing dark look
    assert a.console_expanded is True  # kept
    assert a.session_panel_expanded is True and a.focus_view is False
    assert a.left_panel_width == 0 and a.session_panel_width == 0
    assert settings.creator.transparent_background is True
    assert settings.together.player_name == "" and settings.together.host_port == 47816


def test_workspace_settings_round_trip(tmp_path: Path) -> None:
    from interactive_scrolling.config.settings import TogetherSettings

    store = SettingsStore(tmp_path / "settings.json")
    settings = store.load()
    appearance = replace(
        settings.appearance,
        theme="gray",
        session_panel_expanded=False,
        left_panel_width=420,
        session_panel_width=330,
        focus_view=True,
    )
    together = TogetherSettings(player_name="Robin", host_port=48000)
    assert store.save(replace(settings, appearance=appearance, together=together))
    again = SettingsStore(tmp_path / "settings.json").load()
    assert again.appearance == appearance and again.together == together


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("appearance", "theme", "purple"),
        ("appearance", "left_panel_width", -5),
        ("appearance", "session_panel_width", "wide"),
        ("together", "host_port", 80),
        ("together", "player_name", "x" * 40),
    ],
)
def test_invalid_workspace_values_fall_back_to_defaults(
    tmp_path: Path, section: str, field: str, value: object
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {"version": SETTINGS_VERSION, "pairing_token": "x" * 32, section: {field: value}}
        ),
        encoding="utf-8",
    )
    settings = SettingsStore(path).load()
    default = getattr(getattr(UserSettings(), section), field)
    assert getattr(getattr(settings, section), field) == default
