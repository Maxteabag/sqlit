"""Loads the user's custom keymap and registers it with the core keymap.

Follows the same domain-service pattern as
[`ThemeManager`][sqlit.domains.shell.app.theme_manager] — a settings-driven
configuration step run during app startup. The loader looks for, in order:

1. A named keymap selected by the ``custom_keymap`` setting, resolved
   relative to ``~/.config/sqlit/keymaps/<name>.json`` (or an absolute path).
2. ``~/.config/sqlit/keymap.json`` if it exists — picked up automatically
   so a user can customize without editing settings.json.

The JSON is strictly a *key remapping*. The set of actions and the states
they live in are defined in :mod:`sqlit.core.keymap`; the user only
chooses which key(s) trigger each action::

    {
      "keymap": {
        "action_keys": {
          "<state>": {
            "<action>": "<key>"            // single key
                       | ["<key>", "..."]  // primary + aliases
          }
        },
        "leader_commands": {
          "<menu>": {
            "<action>": "<key>"
          }
        }
      }
    }

The loader validates that every ``(state, action)`` and ``(menu, action)``
pair the user names exists in the defaults; unknown ones abort the load
with a clear error. After merging, the keymap is also validated for
conflicts (two actions claiming the same key in the same state/menu); on
conflict the loader falls back to defaults and prints every collision to
stderr so the user can fix their config.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlit.core.keymap import (
    ActionKeyDef,
    DefaultKeymapProvider,
    KeymapProvider,
    LeaderCommandDef,
    set_keymap,
)
from sqlit.shared.core.protocols import SettingsStoreProtocol
from sqlit.shared.core.store import CONFIG_DIR

CUSTOM_KEYMAP_SETTINGS_KEY = "custom_keymap"
CUSTOM_KEYMAP_DIR = CONFIG_DIR / "keymaps"
# Picked up automatically when no `custom_keymap` setting is present.
# Lets a user customize their bindings by dropping a single file in
# their config dir — no settings edit, no mkdir.
DEFAULT_KEYMAP_FILE = CONFIG_DIR / "keymap.json"


class FileBasedKeymapProvider(KeymapProvider):
    """Keymap provider built by merging user overrides onto the defaults."""

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
        return self._name

    def get_leader_commands(self) -> list[LeaderCommandDef]:
        return list(self._leader_commands)

    def get_action_keys(self) -> list[ActionKeyDef]:
        return list(self._action_keys)


class KeymapManager:
    """Loads and applies a custom keymap during app startup."""

    def __init__(self, settings_store: SettingsStoreProtocol) -> None:
        self._settings_store = settings_store
        # Last load error surfaced by startup_flow once the app is mounted,
        # so the user sees it in the UI instead of only on stderr. None when
        # the most recent load succeeded or no custom keymap was requested.
        self.load_error: str | None = None

    def initialize(self) -> dict:
        settings = self._settings_store.load_all()
        self.load_custom_keymap(settings)
        return settings

    def load_custom_keymap(self, settings: dict) -> None:
        self.load_error = None
        keymap_name = settings.get(CUSTOM_KEYMAP_SETTINGS_KEY)
        if isinstance(keymap_name, str) and keymap_name.strip() not in ("", "default"):
            # Explicit named keymap from settings — power-user path.
            try:
                path = self._resolve_keymap_path(keymap_name.strip())
                self._register_custom_keymap(path, keymap_name.strip())
            except Exception as exc:
                self.load_error = f"Failed to load custom keymap '{keymap_name}': {exc}"
            return

        # No setting → look for the default file. Silently absent is fine; a
        # broken file still raises.
        if DEFAULT_KEYMAP_FILE.exists():
            try:
                self._register_custom_keymap(DEFAULT_KEYMAP_FILE, DEFAULT_KEYMAP_FILE.name)
            except Exception as exc:
                self.load_error = f"Failed to load {DEFAULT_KEYMAP_FILE}: {exc}"

    def _resolve_keymap_path(self, keymap_name: str) -> Path:
        if keymap_name.startswith(("~", "/")) or Path(keymap_name).is_absolute():
            return Path(keymap_name).expanduser()

        name = Path(keymap_name).stem
        return CUSTOM_KEYMAP_DIR / f"{name}.json"

    def _register_custom_keymap(self, path: Path, keymap_name: str) -> None:
        path = path.expanduser()
        if not path.exists():
            raise ValueError(f"Keymap file not found: {path}")

        keymap = self._load_keymap_from_file(path, keymap_name)
        set_keymap(keymap)

    def _load_keymap_from_file(self, path: Path, keymap_name: str) -> FileBasedKeymapProvider:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to read keymap JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Keymap file must contain a JSON object.")

        keymap_data = payload.get("keymap", payload)
        if not isinstance(keymap_data, dict):
            raise ValueError('Keymap file "keymap" must be a JSON object.')

        defaults = DefaultKeymapProvider()
        base_action = defaults.get_action_keys()
        base_leader = defaults.get_leader_commands()

        user_action_overrides, action_unbinds = self._parse_action_overrides(
            keymap_data.get("action_keys", {}), base_action
        )
        user_leader_overrides, leader_unbinds = self._parse_leader_overrides(
            keymap_data.get("leader_commands", {}), base_leader
        )

        merged_action = self._merge_action_keys(
            base_action, user_action_overrides, action_unbinds
        )
        merged_leader = self._merge_leader_commands(
            base_leader, user_leader_overrides, leader_unbinds
        )

        self._detect_conflicts(
            merged_leader,
            merged_action,
            user_leader_overrides,
            user_action_overrides,
        )

        return FileBasedKeymapProvider(keymap_name, merged_leader, merged_action)

    # ------------------------------------------------------------------ parsing

    @staticmethod
    def _normalize_key_list(value: Any, where: str) -> list[str] | None:
        """Return the user's key list, or None to mean "unbind this action".

        Accepts `null`, `""`, and `[]` as unbind sentinels.
        """
        if value is None:
            return None
        if isinstance(value, str):
            if not value:
                return None
            return [value]
        if isinstance(value, list):
            if not value:
                return None
            for k in value:
                if not isinstance(k, str) or not k:
                    raise ValueError(f"{where}: every entry must be a non-empty string.")
            return list(value)
        raise ValueError(f"{where}: expected a string, list of strings, or null to unbind.")

    @staticmethod
    def _parse_action_overrides(
        data: Any, base: list[ActionKeyDef]
    ) -> tuple[list[ActionKeyDef], set[tuple[str, str | None]]]:
        if not isinstance(data, dict):
            raise ValueError('"action_keys" must be a JSON object keyed by state name.')

        # Catalog of defaults grouped by (action, context) — the primary entry
        # carries the canonical guard/show/priority that we inherit for the
        # user's rebound keys.
        defaults_by_pair: dict[tuple[str, str | None], ActionKeyDef] = {}
        for ak in base:
            existing = defaults_by_pair.get((ak.action, ak.context))
            if existing is None or (ak.primary and not existing.primary):
                defaults_by_pair[(ak.action, ak.context)] = ak

        actions_in_state: dict[str | None, set[str]] = defaultdict(set)
        for ak in base:
            actions_in_state[ak.context].add(ak.action)

        out: list[ActionKeyDef] = []
        unbinds: set[tuple[str, str | None]] = set()
        for state, mapping in data.items():
            if not isinstance(state, str) or not state:
                raise ValueError('action_keys keys must be non-empty state names.')
            if not isinstance(mapping, dict):
                raise ValueError(f'action_keys."{state}" must be an object of action → key.')

            for action, keys in mapping.items():
                if not isinstance(action, str) or not action:
                    raise ValueError(f'action_keys."{state}": action names must be non-empty strings.')

                template = defaults_by_pair.get((action, state))
                if template is None:
                    suggestions = sorted(actions_in_state.get(state, set()))
                    hint = (
                        f" Known actions in this state: {suggestions}" if suggestions
                        else f" State {state!r} has no actions in defaults."
                    )
                    raise ValueError(
                        f"Unknown action {action!r} in state {state!r}.{hint}"
                    )

                key_list = KeymapManager._normalize_key_list(
                    keys, where=f'action_keys."{state}"."{action}"'
                )
                if key_list is None:
                    unbinds.add((action, state))
                    continue
                for i, key in enumerate(key_list):
                    out.append(
                        ActionKeyDef(
                            key=key,
                            action=action,
                            context=state,
                            guard=template.guard,
                            primary=(i == 0),
                            show=template.show,
                            priority=template.priority,
                        )
                    )
        return out, unbinds

    @staticmethod
    def _parse_leader_overrides(
        data: Any, base: list[LeaderCommandDef]
    ) -> tuple[list[LeaderCommandDef], set[tuple[str, str]]]:
        if not isinstance(data, dict):
            raise ValueError('"leader_commands" must be a JSON object keyed by menu name.')

        defaults_by_pair: dict[tuple[str, str], LeaderCommandDef] = {
            (cmd.action, cmd.menu): cmd for cmd in base
        }
        actions_in_menu: dict[str, set[str]] = defaultdict(set)
        for cmd in base:
            actions_in_menu[cmd.menu].add(cmd.action)

        out: list[LeaderCommandDef] = []
        unbinds: set[tuple[str, str]] = set()
        for menu, mapping in data.items():
            if not isinstance(menu, str) or not menu:
                raise ValueError('leader_commands keys must be non-empty menu names.')
            if not isinstance(mapping, dict):
                raise ValueError(f'leader_commands."{menu}" must be an object of action → key.')

            for action, key in mapping.items():
                if not isinstance(action, str) or not action:
                    raise ValueError(f'leader_commands."{menu}": action names must be non-empty strings.')

                template = defaults_by_pair.get((action, menu))
                if template is None:
                    suggestions = sorted(actions_in_menu.get(menu, set()))
                    hint = (
                        f" Known actions in this menu: {suggestions}" if suggestions
                        else f" Menu {menu!r} has no actions in defaults."
                    )
                    raise ValueError(
                        f"Unknown leader action {action!r} in menu {menu!r}.{hint}"
                    )

                # null / "" unbinds the default for this (action, menu).
                if key is None or key == "":
                    unbinds.add((action, menu))
                    continue

                if not isinstance(key, str):
                    raise ValueError(
                        f'leader_commands."{menu}"."{action}": expected a key string or null.'
                    )

                out.append(
                    LeaderCommandDef(
                        key=key,
                        action=action,
                        label=template.label,
                        category=template.category,
                        guard=template.guard,
                        menu=menu,
                    )
                )
        return out, unbinds

    # ------------------------------------------------------------------- merge

    @staticmethod
    def _merge_action_keys(
        base: list[ActionKeyDef],
        user: list[ActionKeyDef],
        unbinds: set[tuple[str, str | None]],
    ) -> list[ActionKeyDef]:
        # User overrides specify the COMPLETE key list for each (action, state)
        # they touch — drop every default with that identity, then append.
        # Unbinds drop the defaults without adding anything.
        overridden = {(u.action, u.context) for u in user} | unbinds
        kept = [ak for ak in base if (ak.action, ak.context) not in overridden]
        return kept + user

    @staticmethod
    def _merge_leader_commands(
        base: list[LeaderCommandDef],
        user: list[LeaderCommandDef],
        unbinds: set[tuple[str, str]],
    ) -> list[LeaderCommandDef]:
        overridden = {(u.action, u.menu) for u in user} | unbinds
        kept = [cmd for cmd in base if (cmd.action, cmd.menu) not in overridden]
        return kept + user

    # --------------------------------------------------------------- conflicts

    @staticmethod
    def _detect_conflicts(
        merged_leader: list[LeaderCommandDef],
        merged_action: list[ActionKeyDef],
        user_leader: list[LeaderCommandDef],
        user_action: list[ActionKeyDef],
    ) -> None:
        """Raise ValueError on user-introduced bindings that collide.

        Defaults intentionally bind some keys to multiple actions in the
        same state (e.g. ``d`` in ``tree`` for both delete_connection and
        delete_connection_folder, disambiguated by tree-node state at
        runtime). We don't flag those. We *do* flag any conflict that a
        user override either created or contributed to.
        """
        conflicts: list[str] = []

        user_leader_slots = {(u.key, u.menu) for u in user_leader}
        leader_by_slot: dict[tuple[str, str], set[str]] = defaultdict(set)
        for cmd in merged_leader:
            leader_by_slot[(cmd.key, cmd.menu)].add(cmd.action)
        for (key, menu), actions in sorted(leader_by_slot.items()):
            if len(actions) > 1 and (key, menu) in user_leader_slots:
                conflicts.append(
                    f"leader key {key!r} in menu {menu!r} is bound to multiple actions: "
                    f"{sorted(actions)}"
                )

        user_action_slots = {(u.key, u.context) for u in user_action}
        action_by_slot: dict[tuple[str, str | None], set[str]] = defaultdict(set)
        for ak in merged_action:
            action_by_slot[(ak.key, ak.context)].add(ak.action)
        for (key, ctx), actions in sorted(
            action_by_slot.items(), key=lambda t: (t[0][0], t[0][1] or "")
        ):
            if len(actions) > 1 and (key, ctx) in user_action_slots:
                conflicts.append(
                    f"key {key!r} in state {ctx!r} is bound to multiple actions: "
                    f"{sorted(actions)}"
                )

        if conflicts:
            lines = "\n  - ".join(conflicts)
            raise ValueError(
                f"Conflicting keybindings detected ({len(conflicts)}):\n  - {lines}\n"
                f'Pick a different key, or unbind a colliding action by setting '
                f'its key to null (e.g. "undo": null).'
            )
