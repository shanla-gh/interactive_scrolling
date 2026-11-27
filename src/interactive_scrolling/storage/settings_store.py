"""Persistent user settings (JSON) with per-field validation and safe fallbacks.

The file holds gesture settings, the gesture-to-action mapping, the analytics opt-out and the
browser bridge configuration. Every field is validated on load; an invalid field falls back to
its default and is reported in ``warnings`` instead of discarding the whole file. Writes are
atomic (temporary file + replace), so a crash never leaves a truncated settings file.

Migration
---------
Version 1 files (0.2) are migrated on load and rewritten as version 2 on the next save: renamed
threshold fields keep the user's values, the vertical finger swipes map to the index swipes,
the thumbs-up mapping moves to the half-heart, and the removed application-switching actions
become the new tab-navigation defaults. Values that were still at a version 1 default take the
new default. Every migration step is listed in ``migrations``.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import secrets
import tempfile
import typing
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from interactive_scrolling.actions.types import (
    DEFAULT_MAPPING,
    LEGACY_ACTION_NAMES,
    ActionType,
    MappingError,
    validate_mapping,
)
from interactive_scrolling.config.settings import (
    GESTURE_ENABLE_FIELDS,
    AppearanceSettings,
    CalibrationProfile,
    ConfigError,
    ControlHandPreference,
    CreatorSettings,
    EffectsSettings,
    GestureSettings,
    SensitivityPreset,
    WellbeingSettings,
)
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.storage.paths import data_dir

log = logging.getLogger(__name__)

SETTINGS_VERSION = 3

_V1_RENAMED = {
    "finger_swipe_min_distance_palms": "swipe_min_distance_palms",
    "finger_swipe_min_speed_palms_s": "swipe_min_speed_palms_s",
    "finger_swipe_max_duration_s": "swipe_max_duration_s",
    "thumbs_up_hold_s": "half_heart_hold_s",
}
_V1_ENABLES = {
    "enable_finger_swipes": ("enable_swipe_down", "enable_swipe_up"),
    "enable_hand_sweeps": ("enable_swipe_left", "enable_swipe_right"),
    "enable_thumbs_up": ("enable_half_heart",),
}
_V1_DEFAULTS = {"cooldown_s": 0.6, "return_window_s": 1.0}
"""Version 1 defaults that changed; a stored value equal to them takes the new default."""
_V1_DROPPED = (
    "hand_sweep_min_distance_palms",
    "hand_sweep_min_speed_palms_s",
    "hand_sweep_max_duration_s",
)
DEFAULT_BRIDGE_PORT = 47815


def new_pairing_token() -> str:
    return secrets.token_urlsafe(24)


@dataclass(frozen=True)
class UserSettings:
    gestures: GestureSettings = field(default_factory=GestureSettings)
    mapping: dict[GestureType, ActionType] = field(default_factory=lambda: dict(DEFAULT_MAPPING))
    analytics_enabled: bool = True
    bridge_port: int = DEFAULT_BRIDGE_PORT
    pairing_token: str = field(default_factory=new_pairing_token)
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    creator: CreatorSettings = field(default_factory=CreatorSettings)
    wellbeing: WellbeingSettings = field(default_factory=WellbeingSettings)
    effects: EffectsSettings = field(default_factory=EffectsSettings)
    calibration: CalibrationProfile = field(default_factory=CalibrationProfile)


SECTIONS: dict[str, type] = {
    "appearance": AppearanceSettings,
    "creator": CreatorSettings,
    "wellbeing": WellbeingSettings,
    "effects": EffectsSettings,
    "calibration": CalibrationProfile,
}
"""Simple settings sections stored as JSON objects (fields of bool, int, float, str, enum or
optional int), validated field by field."""


def section_to_json(value: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields(value):
        item = getattr(value, f.name)
        out[f.name] = item.value if isinstance(item, enum.Enum) else item
    return out


def _coerce(raw: Any, kind: Any) -> Any:
    origin = typing.get_origin(kind)
    if origin is typing.Union or str(origin) == "<class 'types.UnionType'>":
        options = [a for a in typing.get_args(kind) if a is not type(None)]
        if raw is None:
            return None
        return _coerce(raw, options[0])
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return kind(raw)
    if kind is bool:
        if not isinstance(raw, bool):
            raise TypeError("expected true/false")
        return raw
    if kind is int:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise TypeError("expected an integer")
        return raw
    if kind is float:
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise TypeError("expected a number")
        return float(raw)
    if kind is str:
        if not isinstance(raw, str):
            raise TypeError("expected text")
        return raw
    raise TypeError(f"unsupported setting type {kind!r}")


def section_from_json(cls: type, data: Any, label: str, warnings: list[str]) -> Any:
    value = cls()
    if not isinstance(data, dict):
        if data is not None:
            warnings.append(f"{label} settings were not an object; defaults used")
        return value
    hints = typing.get_type_hints(cls)
    for f in fields(cls):
        if f.name not in data:
            continue
        raw = data[f.name]
        try:
            value = replace(value, **{f.name: _coerce(raw, hints[f.name])})
        except (ValueError, TypeError, ConfigError) as exc:
            warnings.append(f"invalid {label}.{f.name} ({raw!r}): {exc}; default used")
    return value


def _gesture_settings_to_json(settings: GestureSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields(GestureSettings):
        value = getattr(settings, f.name)
        out[f.name] = value.value if hasattr(value, "value") else value
    return out


def _migrate_gesture_settings_v1(data: dict[str, Any], migrations: list[str]) -> dict[str, Any]:
    out = {k: v for k, v in data.items() if k not in _V1_RENAMED and k not in _V1_ENABLES}
    for old, new in _V1_RENAMED.items():
        if old in data:
            out[new] = data[old]
            migrations.append(f"gesture setting {old} -> {new}")
    for old, news in _V1_ENABLES.items():
        if old in data:
            for new in news:
                out[new] = data[old]
            migrations.append(f"gesture setting {old} -> {', '.join(news)}")
    for name, old_default in _V1_DEFAULTS.items():
        if out.get(name) == old_default:
            del out[name]
            migrations.append(f"{name} was the version 1 default; new default used")
    for name in _V1_DROPPED:
        if out.pop(name, None) is not None:
            migrations.append(f"{name} removed (open-hand sweeps were replaced)")
    return out


def _gesture_settings_from_json(data: Any, warnings: list[str]) -> GestureSettings:
    settings = GestureSettings()
    if not isinstance(data, dict):
        if data is not None:
            warnings.append("gesture settings were not an object; defaults used")
        return settings
    for f in fields(GestureSettings):
        if f.name not in data:
            continue
        raw = data[f.name]
        try:
            if f.name == "preset":
                value: Any = SensitivityPreset(raw)
            elif f.name == "control_hand":
                value = ControlHandPreference(raw)
            elif isinstance(getattr(settings, f.name), bool):
                if not isinstance(raw, bool):
                    raise TypeError("expected true/false")
                value = raw
            else:
                if isinstance(raw, bool) or not isinstance(raw, int | float):
                    raise TypeError("expected a number")
                value = float(raw)
            settings = replace(settings, **{f.name: value})
        except (ValueError, TypeError, ConfigError) as exc:
            warnings.append(f"invalid value for {f.name} ({raw!r}): {exc}; default used")
    if "preset" not in data:
        # No preset stored: values that differ from the defaults are the user's own.
        defaults = GestureSettings()
        if any(
            getattr(settings, f.name) != getattr(defaults, f.name)
            for f in fields(GestureSettings)
            if f.name not in ("preset", "control_hand", *GESTURE_ENABLE_FIELDS)
        ):
            settings = replace(settings, preset=SensitivityPreset.CUSTOM)
    if not settings.preset.keeps_values:
        # Under a named preset every threshold comes from the preset (editing one switches to
        # Custom), so improved preset values of a new version apply; the hand and the enabled
        # gestures are the user's own choices and are kept.
        settings = GestureSettings.from_preset(
            settings.preset,
            control_hand=settings.control_hand,
            **{name: getattr(settings, name) for name in GESTURE_ENABLE_FIELDS},
        )
    return settings


def _mapping_from_json(data: Any, warnings: list[str]) -> dict[GestureType, ActionType]:
    if not isinstance(data, dict):
        if data is not None:
            warnings.append("action mapping was not an object; defaults used")
        return dict(DEFAULT_MAPPING)
    mapping = dict(DEFAULT_MAPPING)
    for key, raw in data.items():
        try:
            gesture = GestureType.from_stored(key)
            if isinstance(raw, str) and raw in LEGACY_ACTION_NAMES:
                continue  # removed action: keep the current default for this gesture
            action = ActionType(raw)
            mapping = validate_mapping({**mapping, gesture: action})
        except (ValueError, MappingError) as exc:
            warnings.append(f"invalid mapping {key!r} -> {raw!r}: {exc}; default used")
    return mapping


_V2_VERTICAL_DEFAULT = {"index_swipe_down": "next_short", "index_swipe_up": "previous_short"}
VERTICAL_DIRECTION_NOTICE = (
    "Scroll direction updated: move your finger UP for the next video and DOWN for the "
    "previous one (like a touchscreen). You can change this in Settings."
)


def _migrate_mapping_v2(data: dict[str, Any], migrations: list[str]) -> dict[str, Any]:
    """Version 2 default: finger down = next. Brief 004 makes finger up = next the default.
    Only an untouched old default is changed; any customised vertical mapping is kept."""
    if all(data.get(k) == v for k, v in _V2_VERTICAL_DEFAULT.items()):
        data = {**data, "index_swipe_up": "next_short", "index_swipe_down": "previous_short"}
        migrations.append(VERTICAL_DIRECTION_NOTICE)
    return data


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "settings.json"
        self.warnings: list[str] = []
        self.migrations: list[str] = []

    def load(self) -> UserSettings:
        """Load settings; missing or invalid content falls back to defaults (never raises)."""
        self.warnings = []
        self.migrations = []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            settings = UserSettings()
            self.save(settings)  # persist the generated pairing token
            return settings
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.warnings.append(f"settings file unreadable ({exc}); defaults used")
            log.warning("Settings file %s unreadable: %s", self.path, exc)
            return UserSettings()
        if not isinstance(raw, dict):
            self.warnings.append("settings file has an unexpected format; defaults used")
            return UserSettings()
        warnings = self.warnings
        version = raw.get("version", 1)
        gesture_data = raw.get("gestures")
        if version == 1 and isinstance(gesture_data, dict):
            gesture_data = _migrate_gesture_settings_v1(gesture_data, self.migrations)
        if version == 1 and isinstance(raw.get("mapping"), dict):
            self.migrations.append("action mapping migrated to the Brief 003 gestures")
        if version == 1:
            self._backup_v1()
        mapping_data = raw.get("mapping")
        if version == 2 and isinstance(mapping_data, dict):
            mapping_data = _migrate_mapping_v2(mapping_data, self.migrations)
        for step in self.migrations:
            log.info("Settings migration: %s", step)
        gestures = _gesture_settings_from_json(gesture_data, warnings)
        mapping = _mapping_from_json(mapping_data, warnings)
        analytics = raw.get("analytics_enabled", True)
        if not isinstance(analytics, bool):
            warnings.append("analytics_enabled must be true/false; default used")
            analytics = True
        port = raw.get("bridge_port", DEFAULT_BRIDGE_PORT)
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            warnings.append(f"bridge_port {port!r} invalid; default used")
            port = DEFAULT_BRIDGE_PORT
        token = raw.get("pairing_token")
        if not isinstance(token, str) or len(token) < 16:
            if token is not None:
                warnings.append("pairing token invalid; a new one was generated")
            token = new_pairing_token()
        sections = {
            name: section_from_json(cls, raw.get(name), name, warnings)
            for name, cls in SECTIONS.items()
        }
        for warning in warnings:
            log.warning("Settings: %s", warning)
        return UserSettings(gestures, mapping, analytics, port, token, **sections)

    def _backup_v1(self) -> None:
        """Keep the version 1 file next to the new one; it is never overwritten."""
        backup = self.path.with_name(self.path.name + ".v1-backup")
        if backup.exists():
            return
        try:
            backup.write_bytes(self.path.read_bytes())
            self.migrations.append(f"version 1 settings kept as {backup.name}")
        except OSError as exc:
            log.warning("Could not back up version 1 settings: %s", exc)

    def save(self, settings: UserSettings) -> bool:
        """Atomically write settings. Returns False (and logs) if the file cannot be written."""
        payload = {
            "version": SETTINGS_VERSION,
            "gestures": _gesture_settings_to_json(settings.gestures),
            "mapping": {g.value: a.value for g, a in settings.mapping.items()},
            "analytics_enabled": settings.analytics_enabled,
            "bridge_port": settings.bridge_port,
            "pairing_token": settings.pairing_token,
        }
        for name in SECTIONS:
            payload[name] = section_to_json(getattr(settings, name))
        tmp: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(tmp, self.path)
            tmp = None
            return True
        except (OSError, TypeError, ValueError) as exc:
            log.error("Could not save settings to %s: %s", self.path, exc)
            return False
        finally:
            if tmp is not None:
                Path(tmp).unlink(missing_ok=True)
