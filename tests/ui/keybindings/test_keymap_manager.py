"""Tests for the KeymapManager."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from sqlit.core.keymap import get_keymap, reset_keymap
from sqlit.core.keymap_manager import KeymapManager


class MockSettingsStore:
    """Mock settings store for testing."""

    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}

    def load_all(self) -> dict:
        return self.settings

    def save_all(self, settings: dict) -> None:
        self.settings = settings

    def get(self, key: str, default=None):
        return self.settings.get(key, default)


@pytest.fixture(autouse=True)
def reset_keymap_after_test():
    """Reset keymap after each test to avoid cross-test pollution."""
    yield
    reset_keymap()


class TestKeymapManager:
    """Test the KeymapManager class."""

    def test_initialize_with_no_custom_keymap(self):
        """Should use default keymap when no custom keymap is specified."""
        settings_store = MockSettingsStore({})
        manager = KeymapManager(settings_store=settings_store)

        settings = manager.initialize()

        assert settings == {}
        assert manager.get_custom_keymap_name() is None
        assert manager.get_custom_keymap_path() is None

    def test_initialize_with_default_keymap_setting(self):
        """Should use default keymap when custom_keymap is set to 'default'."""
        settings_store = MockSettingsStore({"custom_keymap": "default"})
        manager = KeymapManager(settings_store=settings_store)

        settings = manager.initialize()

        assert settings == {"custom_keymap": "default"}
        assert manager.get_custom_keymap_name() is None

    def test_load_custom_keymap_from_file(self, tmp_path: Path):
        """Should load custom keymap from JSON file."""
        keymap_file = tmp_path / "my-custom.json"
        keymap_data = {
            "keymap": {
                "leader_commands": [
                    {
                        "key": "x",
                        "action": "quit",
                        "label": "Exit",
                        "category": "Actions",
                        "menu": "leader",
                    }
                ],
                "action_keys": [
                    {
                        "key": "ctrl+x",
                        "action": "quit",
                        "context": "global",
                        "primary": True,
                        "show": False,
                        "priority": False,
                    }
                ],
            }
        }
        keymap_file.write_text(json.dumps(keymap_data), encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)

        manager.initialize()

        assert manager.get_custom_keymap_name() == str(keymap_file)
        assert manager.get_custom_keymap_path() == keymap_file

        keymap = get_keymap()
        assert keymap.leader("quit") == "x"
        assert keymap.action("quit") == "ctrl+x"

    def test_load_custom_keymap_with_invalid_json(self, tmp_path: Path, capsys):
        """Should handle invalid JSON gracefully."""
        keymap_file = tmp_path / "invalid.json"
        keymap_file.write_text("not valid json", encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)

        manager.initialize()

        captured = capsys.readouterr()
        assert "Failed to load custom keymap" in captured.err
        assert manager.get_custom_keymap_name() is None

    def test_load_custom_keymap_with_missing_file(self, tmp_path: Path, capsys):
        """Should handle missing file gracefully."""
        keymap_file = tmp_path / "nonexistent.json"

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)

        manager.initialize()

        captured = capsys.readouterr()
        assert "Failed to load custom keymap" in captured.err
        assert "not found" in captured.err

    def test_reset_to_default(self, tmp_path: Path):
        """Should reset to default keymap."""
        keymap_file = tmp_path / "test.json"
        keymap_data = {
            "keymap": {
                "leader_commands": [
                    {
                        "key": "z",
                        "action": "quit",
                        "label": "Quit",
                        "category": "Actions",
                    }
                ],
                "action_keys": [],
            }
        }
        keymap_file.write_text(json.dumps(keymap_data), encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)
        manager.initialize()

        assert manager.get_custom_keymap_name() is not None

        manager.reset_to_default()

        assert manager.get_custom_keymap_name() is None
        assert manager.get_custom_keymap_path() is None

    def test_parse_leader_commands_with_all_fields(self, tmp_path: Path):
        """Should parse leader commands with all optional fields."""
        keymap_file = tmp_path / "full.json"
        keymap_data = {
            "keymap": {
                "leader_commands": [
                    {
                        "key": "x",
                        "action": "disconnect",
                        "label": "Disconnect",
                        "category": "Connection",
                        "guard": "has_connection",
                        "menu": "custom",
                    }
                ],
                "action_keys": [],
            }
        }
        keymap_file.write_text(json.dumps(keymap_data), encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)
        manager.initialize()

        keymap = get_keymap()
        commands = keymap.get_leader_commands()
        assert len(commands) == 1
        assert commands[0].key == "x"
        assert commands[0].action == "disconnect"
        assert commands[0].guard == "has_connection"
        assert commands[0].menu == "custom"

    def test_parse_action_keys_with_all_fields(self, tmp_path: Path):
        """Should parse action keys with all fields."""
        keymap_file = tmp_path / "actions.json"
        keymap_data = {
            "keymap": {
                "leader_commands": [],
                "action_keys": [
                    {
                        "key": "i",
                        "action": "enter_insert_mode",
                        "context": "query_normal",
                        "guard": "not_executing",
                        "primary": False,
                        "show": True,
                        "priority": True,
                    }
                ],
            }
        }
        keymap_file.write_text(json.dumps(keymap_data), encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)
        manager.initialize()

        keymap = get_keymap()
        action_keys = keymap.get_action_keys()
        assert len(action_keys) == 1
        assert action_keys[0].key == "i"
        assert action_keys[0].action == "enter_insert_mode"
        assert action_keys[0].context == "query_normal"
        assert action_keys[0].guard == "not_executing"
        assert action_keys[0].primary is False
        assert action_keys[0].show is True
        assert action_keys[0].priority is True

    def test_parse_keymap_with_nested_keymap_object(self, tmp_path: Path):
        """Should handle both nested and flat keymap structure."""
        keymap_file = tmp_path / "nested.json"
        keymap_data = {
            "keymap": {
                "leader_commands": [
                    {"key": "q", "action": "quit", "label": "Quit", "category": "Actions"}
                ],
                "action_keys": [],
            }
        }
        keymap_file.write_text(json.dumps(keymap_data), encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)
        manager.initialize()

        keymap = get_keymap()
        assert keymap.leader("quit") == "q"

    def test_invalid_leader_command_missing_required_field(self, tmp_path: Path, capsys):
        """Should error on missing required fields."""
        keymap_file = tmp_path / "invalid.json"
        keymap_data = {
            "keymap": {
                "leader_commands": [
                    {
                        "key": "q",
                        "action": "quit",
                        # Missing "label" and "category"
                    }
                ],
                "action_keys": [],
            }
        }
        keymap_file.write_text(json.dumps(keymap_data), encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)
        manager.initialize()

        captured = capsys.readouterr()
        assert "Failed to load custom keymap" in captured.err

    def test_invalid_action_key_missing_required_field(self, tmp_path: Path, capsys):
        """Should error on missing required action key fields."""
        keymap_file = tmp_path / "invalid-action.json"
        keymap_data = {
            "keymap": {
                "leader_commands": [],
                "action_keys": [
                    {
                        "key": "i",
                        # Missing "action"
                    }
                ],
            }
        }
        keymap_file.write_text(json.dumps(keymap_data), encoding="utf-8")

        settings_store = MockSettingsStore({"custom_keymap": str(keymap_file)})
        manager = KeymapManager(settings_store=settings_store)
        manager.initialize()

        captured = capsys.readouterr()
        assert "Failed to load custom keymap" in captured.err
