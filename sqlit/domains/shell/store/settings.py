"""Settings store for managing application settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlit.shared.core.store import CONFIG_DIR, JSONFileStore


def _resolve_settings_path() -> Path:
    override = os.environ.get("SQLIT_SETTINGS_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return CONFIG_DIR / "settings.json"


class SettingsStore(JSONFileStore):
    """Store for managing application settings.

    Settings are stored as a JSON object in ~/.sqlit/settings.json
    """

    _instance: SettingsStore | None = None
    _instance_path: Path | None = None

    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__(file_path or _resolve_settings_path())

    @classmethod
    def get_instance(cls) -> SettingsStore:
        """Get the singleton instance."""
        path = _resolve_settings_path()
        if cls._instance is None or cls._instance_path != path:
            cls._instance = cls(file_path=path)
            cls._instance_path = path
        return cls._instance

    def load_all(self) -> dict[str, Any]:
        """Load all settings.

        Returns:
            Dictionary of settings, or empty dict if none exist.
        """
        data = self._read_json()
        return data if isinstance(data, dict) else {}

    def save_all(self, settings: dict[str, Any]) -> None:
        """Save all settings, replacing existing.

        Args:
            settings: Dictionary of settings to save.
        """
        self._write_json(settings)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a specific setting.

        Args:
            key: Setting key.
            default: Default value if key not found.

        Returns:
            Setting value or default.
        """
        return self.load_all().get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a specific setting.

        Args:
            key: Setting key.
            value: Setting value.
        """
        settings = self.load_all()
        settings[key] = value
        self.save_all(settings)

    def delete(self, key: str) -> bool:
        """Delete a specific setting.

        Args:
            key: Setting key to delete.

        Returns:
            True if key existed and was deleted, False otherwise.
        """
        settings = self.load_all()
        if key in settings:
            del settings[key]
            self.save_all(settings)
            return True
        return False
