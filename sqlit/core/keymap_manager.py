"""Keymap management utilities for sqlit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlit.shared.core.protocols import SettingsStoreProtocol
from sqlit.shared.core.store import CONFIG_DIR

from .keymap import (
    ActionKeyDef,
    KeymapProvider,
    LeaderCommandDef,
    get_keymap,
    set_keymap,
)

CUSTOM_KEYMAP_SETTINGS_KEY = "custom_keymap"
CUSTOM_KEYMAP_DIR = CONFIG_DIR / "keymaps"
LEADER_COMMAND_FIELDS = {"key", "action", "label", "category", "guard", "menu"}
ACTION_KEY_FIELDS = {"key", "action", "context", "guard", "primary", "show", "priority"}


class FileBasedKeymapProvider(KeymapProvider):
    """Keymap provider that loads from JSON file."""

    def __init__(
        self,
        name: str,
        leader_commands: list[LeaderCommandDef],
        action_keys: list[ActionKeyDef],
    ):
        self._name = name
        self._leader_commands = leader_commands
        self._action_keys = action_keys

    @property
    def name(self) -> str:
        """Get the keymap name."""
        return self._name

    def get_leader_commands(self) -> list[LeaderCommandDef]:
        """Get all leader command definitions."""
        return list(self._leader_commands)

    def get_action_keys(self) -> list[ActionKeyDef]:
        """Get all regular action key definitions."""
        return list(self._action_keys)


class KeymapManager:
    """Centralized keymap handling for the app."""

    def __init__(
        self,
        settings_store: SettingsStoreProtocol | None = None,
    ) -> None:
        from sqlit.domains.shell.store.settings import SettingsStore

        self._settings_store = settings_store or SettingsStore.get_instance()
        self._custom_keymap_name: str | None = None
        self._custom_keymap_path: Path | None = None

    def initialize(self) -> dict:
        """Initialize keymap from settings.

        Returns:
            The loaded settings dictionary.
        """
        settings = self._settings_store.load_all()
        self.load_custom_keymap(settings)
        return settings

    def load_custom_keymap(self, settings: dict) -> None:
        """Load custom keymap from settings if specified.

        Args:
            settings: Settings dictionary containing custom_keymap key.
        """
        keymap_name = settings.get(CUSTOM_KEYMAP_SETTINGS_KEY)
        if not keymap_name or not isinstance(keymap_name, str):
            return
        if keymap_name.strip() in ("", "default"):
            return

        try:
            path = self._resolve_keymap_path(keymap_name.strip())
            self._register_custom_keymap(path, keymap_name.strip())
        except Exception as exc:
            print(
                f"[sqlit] Failed to load custom keymap '{keymap_name}': {exc}",
                file=sys.stderr,
            )

    def _resolve_keymap_path(self, keymap_name: str) -> Path:
        """Resolve keymap name to file path.

        Args:
            keymap_name: Name of the keymap (without .json extension).

        Returns:
            Path to the keymap JSON file.
        """
        if keymap_name.startswith(("~", "/")) or Path(keymap_name).is_absolute():
            return Path(keymap_name).expanduser()

        name = Path(keymap_name).stem
        file_name = f"{name}.json"
        return CUSTOM_KEYMAP_DIR / file_name

    def _register_custom_keymap(self, path: Path, keymap_name: str) -> None:
        """Load and register a custom keymap from file.

        Args:
            path: Path to the keymap JSON file.
            keymap_name: Name of the keymap.

        Raises:
            ValueError: If the keymap file is invalid.
        """
        path = path.expanduser()
        if not path.exists():
            raise ValueError(f"Keymap file not found: {path}")

        keymap = self._load_keymap_from_file(path, keymap_name)
        set_keymap(keymap)
        self._custom_keymap_name = keymap_name
        self._custom_keymap_path = path.resolve()

    def _load_keymap_from_file(self, path: Path, keymap_name: str) -> FileBasedKeymapProvider:
        """Load keymap data from JSON file.

        Args:
            path: Path to the keymap JSON file.
            keymap_name: Name of the keymap.

        Returns:
            FileBasedKeymapProvider instance.

        Raises:
            ValueError: If the JSON is invalid or missing required fields.
        """
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to read keymap JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Keymap file must contain a JSON object.")

        keymap_data = payload.get("keymap", payload)
        if not isinstance(keymap_data, dict):
            raise ValueError('Keymap file "keymap" must be a JSON object.')

        leader_commands_data = keymap_data.get("leader_commands", [])
        action_keys_data = keymap_data.get("action_keys", [])

        if not isinstance(leader_commands_data, list):
            raise ValueError('"leader_commands" must be a list.')
        if not isinstance(action_keys_data, list):
            raise ValueError('"action_keys" must be a list.')

        leader_commands = self._parse_leader_commands(leader_commands_data)
        action_keys = self._parse_action_keys(action_keys_data)

        return FileBasedKeymapProvider(keymap_name, leader_commands, action_keys)

    def _parse_leader_commands(self, data: list[Any]) -> list[LeaderCommandDef]:
        """Parse leader commands from JSON data.

        Args:
            data: List of leader command dictionaries.

        Returns:
            List of LeaderCommandDef instances.

        Raises:
            ValueError: If any command is invalid.
        """
        commands = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f'Leader command at index {i} must be an object.')

            key = item.get("key")
            action = item.get("action")
            label = item.get("label")
            category = item.get("category")

            if not isinstance(key, str) or not key:
                raise ValueError(f'Leader command at index {i} missing required "key".')
            if not isinstance(action, str) or not action:
                raise ValueError(f'Leader command at index {i} missing required "action".')
            if not isinstance(label, str) or not label:
                raise ValueError(f'Leader command at index {i} missing required "label".')
            if not isinstance(category, str) or not category:
                raise ValueError(f'Leader command at index {i} missing required "category".')

            guard = item.get("guard")
            if guard is not None and not isinstance(guard, str):
                raise ValueError(f'Leader command at index {i} "guard" must be a string.')

            menu = item.get("menu", "leader")
            if not isinstance(menu, str):
                raise ValueError(f'Leader command at index {i} "menu" must be a string.')

            commands.append(
                LeaderCommandDef(
                    key=key,
                    action=action,
                    label=label,
                    category=category,
                    guard=guard,
                    menu=menu,
                )
            )

        return commands

    def _parse_action_keys(self, data: list[Any]) -> list[ActionKeyDef]:
        """Parse action keys from JSON data.

        Args:
            data: List of action key dictionaries.

        Returns:
            List of ActionKeyDef instances.

        Raises:
            ValueError: If any action key is invalid.
        """
        action_keys = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f'Action key at index {i} must be an object.')

            key = item.get("key")
            action = item.get("action")

            if not isinstance(key, str) or not key:
                raise ValueError(f'Action key at index {i} missing required "key".')
            if not isinstance(action, str) or not action:
                raise ValueError(f'Action key at index {i} missing required "action".')

            context = item.get("context")
            if context is not None and not isinstance(context, str):
                raise ValueError(f'Action key at index {i} "context" must be a string.')

            guard = item.get("guard")
            if guard is not None and not isinstance(guard, str):
                raise ValueError(f'Action key at index {i} "guard" must be a string.')

            primary = item.get("primary", True)
            if not isinstance(primary, bool):
                raise ValueError(f'Action key at index {i} "primary" must be a boolean.')

            show = item.get("show", False)
            if not isinstance(show, bool):
                raise ValueError(f'Action key at index {i} "show" must be a boolean.')

            priority = item.get("priority", False)
            if not isinstance(priority, bool):
                raise ValueError(f'Action key at index {i} "priority" must be a boolean.')

            action_keys.append(
                ActionKeyDef(
                    key=key,
                    action=action,
                    context=context,
                    guard=guard,
                    primary=primary,
                    show=show,
                    priority=priority,
                )
            )

        return action_keys

    def get_custom_keymap_name(self) -> str | None:
        """Get the name of the currently loaded custom keymap.

        Returns:
            Keymap name or None if using default keymap.
        """
        return self._custom_keymap_name

    def get_custom_keymap_path(self) -> Path | None:
        """Get the path to the currently loaded custom keymap file.

        Returns:
            Path to keymap file or None if using default keymap.
        """
        return self._custom_keymap_path

    def reset_to_default(self) -> None:
        """Reset to the default keymap."""
        from .keymap import reset_keymap

        reset_keymap()
        self._custom_keymap_name = None
        self._custom_keymap_path = None
