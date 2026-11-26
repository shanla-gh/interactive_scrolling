"""Persistent user settings (JSON) with per-field validation and safe fallbacks.

The file holds gesture settings, the gesture-to-action mapping, the analytics opt-out and the
browser bridge configuration. Every field is validated on load; an invalid field falls back to
its default and is reported in ``warnings`` instead of discarding the whole file. Writes are
atomic (temporary file + replace), so a crash never leaves a truncated settings file.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from interactive_scrolling.actions.types import (
    DEFAULT_MAPPING,
    ActionType,
    MappingError,
    validate_mapping,
)
from interactive_scrolling.config.settings import (
    ConfigError,
    ControlHandPreference,
    GestureSettings,
    SensitivityPreset,
)
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.storage.paths import data_dir

log = logging.getLogger(__name__)

SETTINGS_VERSION = 1
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


def _gesture_settings_to_json(settings: GestureSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields(GestureSettings):
        value = getattr(settings, f.name)
        out[f.name] = value.value if hasattr(value, "value") else value
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
    return settings


def _mapping_from_json(data: Any, warnings: list[str]) -> dict[GestureType, ActionType]:
    if not isinstance(data, dict):
        if data is not None:
            warnings.append("action mapping was not an object; defaults used")
        return dict(DEFAULT_MAPPING)
    mapping = dict(DEFAULT_MAPPING)
    for key, raw in data.items():
        try:
            gesture = GestureType(key)
            action = ActionType(raw)
            mapping = validate_mapping({**mapping, gesture: action})
        except (ValueError, MappingError) as exc:
            warnings.append(f"invalid mapping {key!r} -> {raw!r}: {exc}; default used")
    return mapping


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "settings.json"
        self.warnings: list[str] = []

    def load(self) -> UserSettings:
        """Load settings; missing or invalid content falls back to defaults (never raises)."""
        self.warnings = []
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
        gestures = _gesture_settings_from_json(raw.get("gestures"), warnings)
        mapping = _mapping_from_json(raw.get("mapping"), warnings)
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
        for warning in warnings:
            log.warning("Settings: %s", warning)
        return UserSettings(gestures, mapping, analytics, port, token)

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
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(tmp, self.path)
            return True
        except OSError as exc:
            log.error("Could not save settings to %s: %s", self.path, exc)
            return False
