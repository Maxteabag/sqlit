"""Tests for the state-nested KeymapManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlit.core.keymap import get_keymap, reset_keymap
from sqlit.domains.shell.app.keymap_manager import FileBasedKeymapProvider, KeymapManager


class MockSettingsStore:
    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}

    def load_all(self) -> dict:
        return self.settings

    def save_all(self, settings: dict) -> None:
        self.settings = settings

    def get(self, key: str, default=None):
        return self.settings.get(key, default)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load(tmp_path: Path, name: str, payload: dict) -> KeymapManager:
    file_path = _write(tmp_path / f"{name}.json", payload)
    manager = KeymapManager(settings_store=MockSettingsStore({"custom_keymap": str(file_path)}))
    manager.initialize()
    return manager


@pytest.fixture(autouse=True)
def reset_keymap_after_test():
    yield
    reset_keymap()


@pytest.fixture(autouse=True)
def isolate_default_keymap_file(tmp_path_factory, monkeypatch):
    """Redirect DEFAULT_KEYMAP_FILE to a per-test tmp dir.

    The loader auto-creates a scaffold keymap.json when one isn't present;
    we don't want that writing into the developer's real ~/.config/sqlit.
    """
    from sqlit.domains.shell.app import keymap_manager as km_mod
    tmp_dir = tmp_path_factory.mktemp("keymap-isolation")
    monkeypatch.setattr(km_mod, "DEFAULT_KEYMAP_FILE", tmp_dir / "keymap.json")


class TestLifecycle:
    def test_no_custom_keymap_leaves_defaults_intact(self):
        # The loader auto-creates an empty scaffold, but defaults are unchanged.
        manager = KeymapManager(settings_store=MockSettingsStore({}))
        manager.initialize()
        assert manager.load_error is None
        assert get_keymap().action("enter_insert_mode") == "i"

    def test_default_sentinel_uses_scaffold_only(self):
        manager = KeymapManager(settings_store=MockSettingsStore({"custom_keymap": "default"}))
        manager.initialize()
        assert manager.load_error is None
        assert get_keymap().action("enter_insert_mode") == "i"

    def test_scaffold_created_on_first_run(self, tmp_path_factory):
        # The autouse fixture redirected DEFAULT_KEYMAP_FILE to a fresh tmp dir.
        from sqlit.domains.shell.app import keymap_manager as km_mod
        assert not km_mod.DEFAULT_KEYMAP_FILE.exists()
        KeymapManager(settings_store=MockSettingsStore({})).initialize()
        assert km_mod.DEFAULT_KEYMAP_FILE.exists()
        body = json.loads(km_mod.DEFAULT_KEYMAP_FILE.read_text())
        assert body == {"keymap": {"action_keys": {}, "leader_commands": {}}}

    def test_invalid_json_falls_back(self, tmp_path: Path):
        path = tmp_path / "invalid.json"
        path.write_text("not valid json", encoding="utf-8")
        manager = KeymapManager(settings_store=MockSettingsStore({"custom_keymap": str(path)}))
        manager.initialize()
        assert manager.load_error and "Failed to load custom keymap" in manager.load_error
        assert not isinstance(get_keymap(), FileBasedKeymapProvider)

    def test_missing_file_falls_back(self, tmp_path: Path):
        manager = KeymapManager(
            settings_store=MockSettingsStore({"custom_keymap": str(tmp_path / "nope.json")})
        )
        manager.initialize()
        assert manager.load_error and "not found" in manager.load_error

    def test_load_error_cleared_on_clean_reinit(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json", encoding="utf-8")
        manager = KeymapManager(settings_store=MockSettingsStore({"custom_keymap": str(path)}))
        manager.initialize()
        assert manager.load_error is not None
        # Re-running with the default sentinel must clear the prior error.
        manager._settings_store = MockSettingsStore({"custom_keymap": "default"})  # type: ignore[attr-defined]
        manager.initialize()
        assert manager.load_error is None


class TestSimpleRemap:
    """Remapping a single key for an existing (state, action) pair."""

    def test_single_key_replaces_default(self, tmp_path: Path):
        _load(
            tmp_path,
            "remap",
            {"keymap": {"action_keys": {"query_normal": {"execute_query": "ctrl+enter"}}}},
        )
        keymap = get_keymap()
        assert keymap.action("execute_query") == "ctrl+enter"
        # Old "enter" no longer triggers execute_query in query_normal.
        assert not any(
            ak.key == "enter" and ak.action == "execute_query" and ak.context == "query_normal"
            for ak in keymap.get_action_keys()
        )

    def test_leader_remap(self, tmp_path: Path):
        _load(
            tmp_path,
            "leader",
            {"keymap": {"leader_commands": {"leader": {"show_help": "question_mark"}}}},
        )
        assert get_keymap().leader("show_help", "leader") == "question_mark"

    def test_unrelated_defaults_remain(self, tmp_path: Path):
        _load(
            tmp_path,
            "small",
            {"keymap": {"leader_commands": {"leader": {"change_theme": "Z"}}}},
        )
        keymap = get_keymap()
        # toggle_explorer wasn't touched — still on its default 'e'.
        assert keymap.leader("toggle_explorer", "leader") == "e"


class TestAliases:
    """List values let the user keep aliases explicitly."""

    def test_list_creates_primary_plus_aliases(self, tmp_path: Path):
        _load(
            tmp_path,
            "aliases",
            {"keymap": {"action_keys": {"tree": {"refresh_tree": ["F", "ctrl+r"]}}}},
        )
        keys = get_keymap().keys_for_action("refresh_tree")
        assert keys[0] == "F", "first entry is primary"
        assert "ctrl+r" in keys, "alias is preserved"
        # Default 'f' and 'R' both get replaced — user list is authoritative.
        assert "f" not in keys
        assert "R" not in keys

    def test_single_string_replaces_all_default_aliases(self, tmp_path: Path):
        # Default tree_cursor_down has 'j' (primary) and 'down' (alias).
        # Use ctrl+j to avoid colliding with other default tree bindings.
        _load(
            tmp_path,
            "single",
            {"keymap": {"action_keys": {"tree": {"tree_cursor_down": "ctrl+j"}}}},
        )
        keys = get_keymap().keys_for_action("tree_cursor_down")
        assert keys == ["ctrl+j"], "single-string override replaces the entire key set"


class TestStrictness:
    """Unknown (state, action) pairs are rejected with a helpful error."""

    def test_unknown_action_in_state(self, tmp_path: Path):
        manager = _load(
            tmp_path,
            "bad",
            {"keymap": {"action_keys": {"tree": {"this_action_does_not_exist": "x"}}}},
        )
        assert manager.load_error is not None
        assert "Unknown action 'this_action_does_not_exist' in state 'tree'" in manager.load_error
        assert "Known actions" in manager.load_error

    def test_unknown_state(self, tmp_path: Path):
        manager = _load(
            tmp_path,
            "bad-state",
            {"keymap": {"action_keys": {"made_up_state": {"some_action": "x"}}}},
        )
        assert manager.load_error is not None
        assert "Unknown action" in manager.load_error
        assert "made_up_state" in manager.load_error

    def test_unknown_leader_action(self, tmp_path: Path):
        manager = _load(
            tmp_path,
            "bad-leader",
            {"keymap": {"leader_commands": {"leader": {"not_a_leader_action": "x"}}}},
        )
        assert manager.load_error is not None
        assert "Unknown leader action" in manager.load_error

    def test_empty_string_in_list_is_rejected(self, tmp_path: Path):
        manager = _load(
            tmp_path,
            "empty-in-list",
            {"keymap": {"action_keys": {"tree": {"refresh_tree": ["f", ""]}}}},
        )
        assert manager.load_error is not None
        assert "every entry must be a non-empty string" in manager.load_error


class TestDefaultKeymapFile:
    """Drop ~/.config/sqlit/keymap.json with no settings edit → it loads."""

    def test_default_file_picked_up_automatically(self, tmp_path: Path, monkeypatch):
        # Point CONFIG_DIR-derived constants at a fresh dir.
        from sqlit.domains.shell.app import keymap_manager as km_mod
        default_path = tmp_path / "keymap.json"
        default_path.write_text(json.dumps(
            {"keymap": {"action_keys": {"query_normal": {"execute_query": "ctrl+enter"}}}}
        ))
        monkeypatch.setattr(km_mod, "DEFAULT_KEYMAP_FILE", default_path)

        manager = KeymapManager(settings_store=MockSettingsStore({}))
        manager.initialize()
        assert manager.load_error is None
        assert get_keymap().action("execute_query") == "ctrl+enter"

    def test_settings_override_takes_precedence(self, tmp_path: Path, monkeypatch):
        # If both default file and `custom_keymap` setting exist, the setting wins.
        from sqlit.domains.shell.app import keymap_manager as km_mod
        default_path = tmp_path / "keymap.json"
        default_path.write_text(json.dumps(
            {"keymap": {"action_keys": {"query_normal": {"execute_query": "ctrl+enter"}}}}
        ))
        monkeypatch.setattr(km_mod, "DEFAULT_KEYMAP_FILE", default_path)

        named = tmp_path / "named.json"
        named.write_text(json.dumps(
            {"keymap": {"action_keys": {"query_normal": {"execute_query": "ctrl+shift+enter"}}}}
        ))
        manager = KeymapManager(settings_store=MockSettingsStore({"custom_keymap": str(named)}))
        manager.initialize()
        assert get_keymap().action("execute_query") == "ctrl+shift+enter"

    def test_no_setting_creates_scaffold_and_loads_it(self, tmp_path: Path, monkeypatch):
        from sqlit.domains.shell.app import keymap_manager as km_mod
        target = tmp_path / "fresh-config" / "keymap.json"
        monkeypatch.setattr(km_mod, "DEFAULT_KEYMAP_FILE", target)
        assert not target.exists()
        manager = KeymapManager(settings_store=MockSettingsStore({}))
        manager.initialize()
        assert manager.load_error is None
        assert target.exists(), "scaffold must be written on first run"
        # Defaults are still in effect since the scaffold is empty.
        assert get_keymap().action("enter_insert_mode") == "i"


class TestFriendlyKeyNames:
    """User can write `:` instead of `colon`, `?` instead of `question_mark`, etc."""

    def test_question_mark_normalizes(self, tmp_path: Path):
        _load(
            tmp_path,
            "qmark",
            {"keymap": {"leader_commands": {"leader": {"show_help": "?"}}}},
        )
        # Internally stored as canonical Textual name.
        assert get_keymap().leader("show_help", "leader") == "question_mark"

    def test_colon_expands_to_all_terminal_variants(self, tmp_path: Path):
        # `:` is emitted as `colon`, `shift+semicolon`, or `:` depending on
        # the terminal/platform — `_expand_user_key` covers all three so the
        # binding works everywhere.
        _load(
            tmp_path,
            "colon",
            {"keymap": {"action_keys": {"global": {"enter_command_mode": ":"}}}},
        )
        keys = get_keymap().keys_for_action("enter_command_mode")
        assert "colon" in keys
        assert "shift+semicolon" in keys
        assert ":" in keys

    def test_friendly_char_with_modifier(self, tmp_path: Path):
        _load(
            tmp_path,
            "ctrl-slash",
            {"keymap": {"action_keys": {"tree": {"tree_filter": "ctrl+/"}}}},
        )
        # ctrl+/ canonicalizes to ctrl+slash.
        keys = get_keymap().keys_for_action("tree_filter")
        assert "ctrl+slash" in keys
        assert "/" not in keys
        assert "slash" not in keys

    def test_canonical_names_still_work(self, tmp_path: Path):
        # User can still write the canonical Textual name if they want to.
        _load(
            tmp_path,
            "canonical",
            {"keymap": {"leader_commands": {"leader": {"show_help": "question_mark"}}}},
        )
        assert get_keymap().leader("show_help", "leader") == "question_mark"

    def test_literal_plus_via_double_plus_preserved(self):
        """`ctrl++` means ctrl + plus key; must round-trip unchanged."""
        from sqlit.domains.shell.app.keymap_manager import _expand_user_key
        assert _expand_user_key("ctrl++") == ["ctrl++"]
        assert _expand_user_key("++") == ["++"]

    def test_shift_modifier_does_not_double_when_canonical_already_has_shift(
        self, tmp_path: Path
    ):
        """`shift+:` must not expand to `shift+shift+semicolon`.

        The friendly char `:` expands to three canonical variants, one of
        which (`shift+semicolon`) already carries a shift prefix. Naively
        concatenating the user's `shift+` prefix produces `shift+shift+...`,
        which Textual won't match — the binding silently dies.
        """
        _load(
            tmp_path,
            "shift-friendly",
            {
                "keymap": {
                    "action_keys": {
                        "query_normal": {"new_query": "shift+:"}
                    }
                }
            },
        )
        keys = get_keymap().keys_for_action("new_query")
        # No canonical key should ever start with "shift+shift+".
        bad = [k for k in keys if "shift+shift+" in k]
        assert not bad, (
            f"shift+<friendly> expansion produced malformed canonical(s): {bad}; "
            f"all keys: {keys}"
        )


class TestUnbind:
    """null / "" / [] removes a default binding without adding a replacement."""

    def test_null_unbinds_default(self, tmp_path: Path):
        # Default: 'u' → undo in query_normal. User sets it to null.
        _load(
            tmp_path,
            "unbind-null",
            {"keymap": {"action_keys": {"query_normal": {"undo": None}}}},
        )
        keymap = get_keymap()
        # No key in query_normal triggers undo anymore.
        assert not any(
            ak.action == "undo" and ak.context == "query_normal"
            for ak in keymap.get_action_keys()
        )

    def test_unbind_resolves_user_vs_default_conflict(self, tmp_path: Path):
        # User wants 'u' for enter_insert_mode. Without unbinding undo this
        # collides with the default 'u' → undo. With it, the user's binding
        # works cleanly.
        manager = _load(
            tmp_path,
            "unbind-resolves",
            {
                "keymap": {
                    "action_keys": {
                        "query_normal": {
                            "enter_insert_mode": "u",
                            "undo": None,
                        }
                    }
                }
            },
        )
        assert manager.load_error is None
        keymap = get_keymap()
        assert keymap.action("enter_insert_mode") == "u"
        assert not any(ak.action == "undo" and ak.context == "query_normal"
                       for ak in keymap.get_action_keys())

    def test_empty_string_also_unbinds(self, tmp_path: Path):
        _load(
            tmp_path,
            "unbind-empty",
            {"keymap": {"action_keys": {"query_normal": {"undo": ""}}}},
        )
        assert not any(
            ak.action == "undo" and ak.context == "query_normal"
            for ak in get_keymap().get_action_keys()
        )

    def test_leader_null_unbinds(self, tmp_path: Path):
        _load(
            tmp_path,
            "unbind-leader",
            {"keymap": {"leader_commands": {"leader": {"toggle_explorer": None}}}},
        )
        assert not any(
            c.action == "toggle_explorer" and c.menu == "leader"
            for c in get_keymap().get_leader_commands()
        )


class TestConflicts:
    """User-introduced collisions abort load with a clear error."""

    def test_user_vs_default_action_key(self, tmp_path: Path):
        # Default: 'i' → enter_insert_mode in query_normal. User binds 'i' to undo.
        manager = _load(
            tmp_path,
            "conflict",
            {"keymap": {"action_keys": {"query_normal": {"undo": "i"}}}},
        )
        assert manager.load_error is not None
        assert "Conflicting keybindings detected" in manager.load_error
        assert "'i'" in manager.load_error and "query_normal" in manager.load_error

    def test_user_vs_user_action_key(self, tmp_path: Path):
        manager = _load(
            tmp_path,
            "self-conflict",
            {
                "keymap": {
                    "action_keys": {
                        "query_normal": {
                            "undo": "ctrl+x",
                            "redo": "ctrl+x",
                        }
                    }
                }
            },
        )
        assert manager.load_error is not None
        assert "Conflicting keybindings detected" in manager.load_error

    def test_user_vs_default_leader(self, tmp_path: Path):
        # Default: <leader>e → toggle_explorer. User binds <leader>e → change_theme.
        manager = _load(
            tmp_path,
            "leader-conflict",
            {"keymap": {"leader_commands": {"leader": {"change_theme": "e"}}}},
        )
        assert manager.load_error is not None
        assert "leader key 'e'" in manager.load_error

    def test_default_only_overlaps_are_tolerated(self, tmp_path: Path):
        # 'd' in tree binds two actions in defaults (state-guarded at runtime).
        # An unrelated user override must not trip on that pre-existing overlap.
        manager = _load(
            tmp_path,
            "untouched",
            {"keymap": {"action_keys": {"query_normal": {"undo": "Z"}}}},
        )
        assert manager.load_error is None


class TestStartupNotification:
    """The load error is surfaced to the user via app.notify on startup."""

    def test_notifies_when_load_error_present(self, tmp_path: Path):
        from sqlit.domains.shell.app.startup_flow import _warn_on_keymap_error

        path = tmp_path / "bad.json"
        path.write_text("not valid json", encoding="utf-8")
        manager = KeymapManager(settings_store=MockSettingsStore({"custom_keymap": str(path)}))
        manager.initialize()
        assert manager.load_error is not None

        notifications: list[tuple[str, str]] = []
        scheduled: list = []

        class FakeApp:
            _keymap_manager = manager

            def notify(self, message: str, *, severity: str = "information", timeout: float = 5) -> None:
                notifications.append((severity, message))

            def call_after_refresh(self, callback, *args, **kwargs) -> None:
                scheduled.append((callback, args, kwargs))

        _warn_on_keymap_error(FakeApp(), is_headless=False)  # type: ignore[arg-type]
        # notify is deferred via call_after_refresh; run the scheduled callback.
        assert len(scheduled) == 1
        callback, args, kwargs = scheduled[0]
        callback(*args, **kwargs)
        assert len(notifications) == 1
        severity, message = notifications[0]
        assert severity == "error"
        assert "Failed to load custom keymap" in message
        assert "Defaults are in effect" in message

    def test_silent_when_no_load_error(self, tmp_path: Path):
        from sqlit.domains.shell.app.startup_flow import _warn_on_keymap_error

        manager = KeymapManager(settings_store=MockSettingsStore({}))
        manager.initialize()
        assert manager.load_error is None

        scheduled: list = []
        notifications: list[tuple[str, str]] = []

        class FakeApp:
            _keymap_manager = manager

            def notify(self, message: str, *, severity: str = "information", timeout: float = 5) -> None:
                notifications.append((severity, message))

            def call_after_refresh(self, callback, *args, **kwargs) -> None:
                scheduled.append((callback, args, kwargs))

        _warn_on_keymap_error(FakeApp(), is_headless=False)  # type: ignore[arg-type]
        # Nothing scheduled or notified when load_error is None.
        assert scheduled == []
        assert notifications == []


class TestMetadataInheritance:
    """Action metadata (label, category, guard, priority, show) always comes from defaults."""

    def test_leader_inherits_label_and_category(self, tmp_path: Path):
        _load(
            tmp_path,
            "leader-meta",
            {"keymap": {"leader_commands": {"leader": {"show_help": "question_mark"}}}},
        )
        match = next(
            c for c in get_keymap().get_leader_commands()
            if c.action == "show_help" and c.menu == "leader"
        )
        assert match.key == "question_mark"
        assert match.label == "Help"          # inherited
        assert match.category == "Actions"    # inherited

    def test_action_key_inherits_flags(self, tmp_path: Path):
        # leader_key in 'global' is primary=True, priority=True by default.
        _load(
            tmp_path,
            "flags",
            {"keymap": {"action_keys": {"global": {"leader_key": "comma"}}}},
        )
        match = next(
            ak for ak in get_keymap().get_action_keys()
            if ak.action == "leader_key" and ak.context == "global"
        )
        assert match.key == "comma"
        assert match.primary is True
        assert match.priority is True
