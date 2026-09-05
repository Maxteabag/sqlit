"""Loads the user's custom keymap and registers it with the core keymap.

There is exactly one keymap file: ``<CONFIG_DIR>/keymap.json``. It's
auto-created as an empty scaffold on first run and overwritten in place
by the in-app keybinding editor — no separate "named keymap" indirection.

``CONFIG_DIR`` resolves to ``$SQLIT_CONFIG_DIR`` if set, otherwise
``$XDG_CONFIG_HOME/sqlit`` (defaulting to ``~/.config/sqlit``). See
:mod:`sqlit.shared.core.store`.

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

# The only keymap file. Auto-scaffolded on first run; the in-app
# editor writes here.
DEFAULT_KEYMAP_FILE = CONFIG_DIR / "keymap.json"

_CONTEXT_ANCESTORS_CACHE: dict[str, tuple[str, ...]] | None = None


def _context_ancestors() -> dict[str, tuple[str, ...]]:
    """Walk :class:`UIStateMachine` once to build descendant→ancestors.

    Each ``State`` subclass that maps to a keymap context declares its
    own name via the ``keymap_context`` class attribute (see
    :class:`sqlit.core.state_base.State`). The state machine wires the
    parent chain, so the hierarchy used by the runtime resolver is the
    *only* source of truth — the conflict detector just walks it.

    Modal-only screens (error dialog, connection editor) carry their
    own bindings and don't appear in :class:`UIStateMachine`, so they
    sit outside any chain — their context names simply don't appear in
    the returned map.
    """
    global _CONTEXT_ANCESTORS_CACHE
    if _CONTEXT_ANCESTORS_CACHE is not None:
        return _CONTEXT_ANCESTORS_CACHE

    # Local import so importing this module at app startup doesn't drag
    # in every State subclass before it's actually needed (also avoids
    # the latent circular-import risk between shell and core modules).
    from sqlit.domains.shell.state.machine import UIStateMachine

    machine = UIStateMachine()
    ancestors: dict[str, tuple[str, ...]] = {}
    for state in machine._states:
        ctx = state.keymap_context
        if ctx is None:
            continue
        chain: list[str] = []
        cur = state.parent
        while cur is not None:
            anc_ctx = cur.keymap_context
            if anc_ctx is not None and anc_ctx != ctx:
                chain.append(anc_ctx)
            cur = cur.parent
        ancestors[ctx] = tuple(chain)
    # Root context itself: no ancestors, but it needs an entry so
    # downstream lookups don't ``KeyError``.
    if machine.root.keymap_context is not None:
        ancestors.setdefault(machine.root.keymap_context, ())

    _CONTEXT_ANCESTORS_CACHE = ancestors
    return ancestors

# Friendly literal characters → the canonical Textual key name(s) they
# expand to. Lets the user write `"?"` instead of `"question_mark"` and
# `":"` instead of spelling out the colon's three terminal variants.
# Multi-element values cover the platforms / terminals that emit
# different `event.key` strings for the same physical keypress.
_FRIENDLY_TO_CANONICAL: dict[str, list[str]] = {
    "?": ["question_mark"],
    "/": ["slash"],
    "$": ["dollar_sign"],
    "%": ["percent_sign"],
    "*": ["asterisk"],
    "^": ["circumflex_accent"],
    ":": ["colon", "shift+semicolon", ":"],
    ";": ["semicolon"],
    "@": ["at"],
    "#": ["number_sign"],
    "!": ["exclamation_mark"],
    "&": ["ampersand"],
    "~": ["tilde"],
    "`": ["grave_accent"],
    "(": ["left_parenthesis"],
    ")": ["right_parenthesis"],
    "[": ["left_square_bracket"],
    "]": ["right_square_bracket"],
    "{": ["left_curly_bracket"],
    "}": ["right_curly_bracket"],
    "<": ["less_than_sign"],
    ">": ["greater_than_sign"],
    "|": ["vertical_line"],
    "_": ["underscore"],
}

def _expand_user_key(key: str) -> list[str]:
    """Expand a single user-supplied key string to its canonical Textual form(s).

    Splits off modifier prefixes (``ctrl+``, ``shift+``, ``alt+``, ``cmd+``),
    looks up the base character in the friendly-name table, and re-attaches
    the modifiers to each canonical variant. Unknown bases pass through
    unchanged so Textual's own key names (e.g. ``escape``, ``f5``) keep
    working.

    When a canonical variant already carries one of the user's modifiers
    (e.g. ``":"`` expands to include ``"shift+semicolon"`` and the user
    wrote ``"shift+:"``), we deduplicate so we don't produce a malformed
    ``shift+shift+semicolon`` that Textual would silently ignore.
    """
    parts = key.split("+")
    base = parts[-1]
    modifiers = parts[:-1]

    # Trailing "+" in input (e.g. "ctrl++") means the literal plus key.
    # Splitting leaves an empty base — preserve the user's input verbatim
    # rather than trying to canonicalize.
    if base == "":
        return [key]

    canonicals = _FRIENDLY_TO_CANONICAL.get(base, [base])
    if not modifiers:
        return list(canonicals)

    user_mods = set(modifiers)
    expanded: list[str] = []
    seen: set[str] = set()
    for canonical in canonicals:
        canon_parts = canonical.split("+")
        canon_mods = set(canon_parts[:-1])
        canon_base = canon_parts[-1]
        # Union the user's modifiers with whatever the canonical already
        # has — keeps each modifier exactly once.
        merged_mods = sorted(user_mods | canon_mods)
        combined = "+".join(merged_mods + [canon_base]) if merged_mods else canon_base
        if combined not in seen:
            seen.add(combined)
            expanded.append(combined)
    return expanded


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
        # Path of the file we most recently loaded — the editor writes to
        # this so live edits actually round-trip through the same file the
        # loader will re-read.
        self.active_path: Path | None = None

    def initialize(self) -> dict:
        settings = self._settings_store.load_all()
        self.load_custom_keymap(settings)
        return settings

    def load_custom_keymap(self, settings: dict) -> None:  # noqa: ARG002
        """Load (or auto-scaffold) ``~/.config/sqlit/keymap.json``.

        The ``settings`` argument is kept for signature compatibility with
        the rest of startup — it used to drive a ``custom_keymap`` named
        path, but that indirection has been removed in favour of a single
        on-disk file the in-app editor owns.
        """
        self.load_error = None
        self._ensure_default_keymap_scaffold()
        self.active_path = DEFAULT_KEYMAP_FILE
        if DEFAULT_KEYMAP_FILE.exists():
            try:
                self._register_custom_keymap(DEFAULT_KEYMAP_FILE, DEFAULT_KEYMAP_FILE.name)
            except Exception as exc:
                self.load_error = f"Failed to load {DEFAULT_KEYMAP_FILE}: {exc}"

    def reload(self) -> None:
        """Reload the keymap from disk and re-publish it via set_keymap().

        Called by the in-app keybinding editor after it writes a change to
        the active keymap file. On parse/validation errors the error is
        surfaced via :attr:`load_error` and the previously-installed keymap
        stays active.
        """
        from sqlit.core.keymap import reset_keymap

        # Drop the cached provider so an error path leaves us on defaults
        # rather than stale user overrides.
        reset_keymap()
        settings = self._settings_store.load_all()
        self.load_custom_keymap(settings)
        if self.load_error:
            raise ValueError(self.load_error)

    # ---------------------------------------------------------------- editing

    def edit_action_key(
        self,
        state: str,
        action: str,
        keys: str | list[str] | None,
    ) -> None:
        """Set or unset a user override for ``action_keys[state][action]``.

        Passing ``None`` removes the override (default reapplies). Writes to
        :attr:`active_path` then triggers a reload.
        """
        payload = self._read_payload_for_edit()
        keymap_data = self._keymap_section(payload)
        action_keys = keymap_data.setdefault("action_keys", {})
        if not isinstance(action_keys, dict):
            action_keys = {}
            keymap_data["action_keys"] = action_keys
        state_map = action_keys.setdefault(state, {})
        if not isinstance(state_map, dict):
            state_map = {}
            action_keys[state] = state_map
        if keys is None:
            state_map.pop(action, None)
            if not state_map:
                action_keys.pop(state, None)
        else:
            state_map[action] = keys
        self._write_payload_and_reload(payload)

    def edit_leader_command(
        self,
        menu: str,
        action: str,
        key: str | None,
    ) -> None:
        """Set or unset a user override for ``leader_commands[menu][action]``."""
        payload = self._read_payload_for_edit()
        keymap_data = self._keymap_section(payload)
        leader = keymap_data.setdefault("leader_commands", {})
        if not isinstance(leader, dict):
            leader = {}
            keymap_data["leader_commands"] = leader
        menu_map = leader.setdefault(menu, {})
        if not isinstance(menu_map, dict):
            menu_map = {}
            leader[menu] = menu_map
        if key is None:
            menu_map.pop(action, None)
            if not menu_map:
                leader.pop(menu, None)
        else:
            menu_map[action] = key
        self._write_payload_and_reload(payload)

    def reset_all(self) -> None:
        """Wipe all user overrides — writes an empty scaffold and reloads."""
        payload = {"keymap": {"action_keys": {}, "leader_commands": {}}}
        self._write_payload_and_reload(payload)

    def _read_payload_for_edit(self) -> dict:
        path = self.active_path or DEFAULT_KEYMAP_FILE
        if not path.exists():
            return {"keymap": {"action_keys": {}, "leader_commands": {}}}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            # Corrupt file — overwrite with a fresh scaffold rather than
            # silently propagating the parse error to the user's edit.
            return {"keymap": {"action_keys": {}, "leader_commands": {}}}
        if not isinstance(raw, dict):
            return {"keymap": {"action_keys": {}, "leader_commands": {}}}
        return raw

    @staticmethod
    def _keymap_section(payload: dict) -> dict:
        section = payload.get("keymap")
        if not isinstance(section, dict):
            section = {}
            payload["keymap"] = section
        return section

    def _write_payload_and_reload(self, payload: dict) -> None:
        # Validate first — if the proposed edit collides with another
        # binding (or fails parse / reference checks), surface the error
        # without touching the on-disk keymap. The user's last good config
        # stays in effect.
        self.validate_payload(payload)
        path = self.active_path or DEFAULT_KEYMAP_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        self.reload()

    @staticmethod
    def _ensure_default_keymap_scaffold() -> None:
        """Create an empty keymap.json on first run so users can discover it."""
        if DEFAULT_KEYMAP_FILE.exists():
            return
        try:
            DEFAULT_KEYMAP_FILE.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_KEYMAP_FILE.write_text(
                json.dumps(
                    {"keymap": {"action_keys": {}, "leader_commands": {}}},
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
        except OSError:
            # Read-only config dir or similar — silently skip; the user
            # can still create the file themselves.
            pass

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
        return self._build_provider_from_payload(payload, keymap_name)

    def _build_provider_from_payload(
        self, payload: Any, keymap_name: str
    ) -> FileBasedKeymapProvider:
        """Parse + merge + validate a keymap payload.

        Used by the file loader and by :meth:`validate_payload` — anything
        the in-app editor would commit to disk must pass through this so
        we catch conflicts before writing, not after the next restart.
        """
        if not isinstance(payload, dict):
            raise ValueError("Keymap file must contain a JSON object.")

        keymap_data = payload.get("keymap", payload)
        if not isinstance(keymap_data, dict):
            raise ValueError('Keymap file "keymap" must be a JSON object.')

        defaults = DefaultKeymapProvider()
        base_action = defaults.get_action_keys()
        base_leader = defaults.get_leader_commands()

        user_action_overrides, action_unbinds = self._parse_action_overrides(
            keymap_data.get("action_keys", {}), base_action, base_leader
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
            base_leader,
            base_action,
        )

        return FileBasedKeymapProvider(keymap_name, merged_leader, merged_action)

    def validate_payload(self, payload: dict) -> None:
        """Raise ValueError if ``payload`` would fail the loader's checks.

        Called by the in-app editor before writing a proposed edit, so a
        user-introduced conflict is caught in the UI instead of surfacing
        as a startup error the next time sqlit launches.
        """
        self._build_provider_from_payload(payload, "validation")

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
        data: Any, base: list[ActionKeyDef], leader: list[LeaderCommandDef]
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

        # Only the main leader menu contains standalone app actions. Vim
        # submenus reuse motion names such as "word" and need their prefix.
        leader_by_action = {cmd.action: cmd for cmd in leader if cmd.menu == "leader"}
        app_contexts = _context_ancestors()

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
                if template is None and state in app_contexts:
                    command = leader_by_action.get(action)
                    if command is not None:
                        template = ActionKeyDef("", action, state, guard=command.guard)
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
                # Expand friendly chars (e.g. "?") to their canonical Textual
                # variants. The first entry in the original user list is the
                # primary; its expansion contributes all primary candidates;
                # subsequent user entries are aliases.
                first = True
                for user_key in key_list:
                    for canonical in _expand_user_key(user_key):
                        out.append(
                            ActionKeyDef(
                                key=canonical,
                                action=action,
                                context=state,
                                guard=template.guard,
                                primary=first,
                                show=template.show,
                                priority=template.priority,
                                leader_command=action in leader_by_action,
                            )
                        )
                    first = False
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

                # Expand friendly chars (`":"` → variant list, `"?"` → "question_mark", …).
                for canonical in _expand_user_key(key):
                    out.append(
                        LeaderCommandDef(
                            key=canonical,
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
        base_leader: list[LeaderCommandDef],
        base_action: list[ActionKeyDef],
    ) -> None:
        """Raise ValueError on user-introduced bindings that collide.

        Defaults intentionally bind some keys to multiple actions in the
        same state (e.g. ``d`` in ``tree`` for both delete_connection and
        delete_connection_folder, disambiguated by tree-node state at
        runtime). We never flag those — and if the user's config preserves
        that exact overlap (e.g. they copied the full template verbatim),
        we don't flag that either. We *do* flag any conflict the user
        actually introduced — a new action joining an existing slot.
        """
        conflicts: list[str] = []

        def _by_slot_leader(commands):
            out: dict[tuple[str, str], set[str]] = defaultdict(set)
            for cmd in commands:
                out[(cmd.key, cmd.menu)].add(cmd.action)
            return out

        def _by_slot_action(action_keys):
            out: dict[tuple[str, str | None], set[str]] = defaultdict(set)
            for ak in action_keys:
                out[(ak.key, ak.context)].add(ak.action)
            return out

        base_leader_slots = _by_slot_leader(base_leader)
        merged_leader_slots = _by_slot_leader(merged_leader)
        user_leader_slots = {(u.key, u.menu) for u in user_leader}
        for slot, actions in sorted(merged_leader_slots.items()):
            if len(actions) <= 1 or slot not in user_leader_slots:
                continue
            # If the actions for this slot match the defaults exactly, the
            # user just preserved a pre-existing (state-machine-disambiguated)
            # overlap rather than creating a new one.
            if actions == base_leader_slots.get(slot):
                continue
            key, menu = slot
            conflicts.append(
                f"leader key {key!r} in menu {menu!r} is bound to multiple actions: "
                f"{sorted(actions)}"
            )

        base_action_slots = _by_slot_action(base_action)
        merged_action_slots = _by_slot_action(merged_action)
        user_action_slots = {(u.key, u.context) for u in user_action}
        for slot, actions in sorted(
            merged_action_slots.items(), key=lambda t: (t[0][0], t[0][1] or "")
        ):
            if len(actions) <= 1 or slot not in user_action_slots:
                continue
            if actions == base_action_slots.get(slot):
                continue
            key, ctx = slot
            conflicts.append(
                f"key {key!r} in state {ctx!r} is bound to multiple actions: "
                f"{sorted(actions)}"
            )

        # Shadow conflicts: the same key bound to *different* actions in
        # two contexts that share an ancestor/descendant relationship. At
        # runtime only the most-specific context's binding fires, so the
        # ancestor binding silently dies in that state — a footgun the
        # user is rarely intending. Tolerate the case where the same
        # shadow already exists in defaults (it's an explicit design
        # choice, not a user mistake).
        ancestors = _context_ancestors()

        def _related(a: str | None, b: str | None) -> bool:
            if a is None or b is None or a == b:
                return False
            return b in ancestors.get(a, ()) or a in ancestors.get(b, ())

        def _is_default_shadow(ak1: ActionKeyDef, ak2: ActionKeyDef) -> bool:
            """True if both bindings exist in defaults (so the overlap is
            intentional and predates the user's edits)."""
            has1 = any(
                bk.key == ak1.key and bk.action == ak1.action and bk.context == ak1.context
                for bk in base_action
            )
            has2 = any(
                bk.key == ak2.key and bk.action == ak2.action and bk.context == ak2.context
                for bk in base_action
            )
            return has1 and has2

        by_key: dict[str, list[ActionKeyDef]] = defaultdict(list)
        for ak in merged_action:
            if ak.key:  # skip unbound entries (key="")
                by_key[ak.key].append(ak)

        user_identities = {(u.action, u.context) for u in user_action}
        shadow_seen: set[tuple[str, str, str | None, str, str | None]] = set()
        for key, aks in by_key.items():
            for i, ak1 in enumerate(aks):
                for ak2 in aks[i + 1:]:
                    if ak1.action == ak2.action:
                        continue
                    if ak1.context == ak2.context:
                        continue  # already handled by same-context check
                    if not _related(ak1.context, ak2.context):
                        continue
                    # Only flag if the user's edits introduced the shadow —
                    # i.e. at least one of the two bindings comes from the
                    # user, and the same overlap isn't already in defaults.
                    touched = (
                        (ak1.action, ak1.context) in user_identities
                        or (ak2.action, ak2.context) in user_identities
                    )
                    if not touched:
                        continue
                    if _is_default_shadow(ak1, ak2):
                        continue
                    # Dedupe so each conflict shows once.
                    a, b = sorted(
                        [(ak1.action, ak1.context), (ak2.action, ak2.context)]
                    )
                    sig = (key, a[0], a[1], b[0], b[1])
                    if sig in shadow_seen:
                        continue
                    shadow_seen.add(sig)
                    conflicts.append(
                        f"key {key!r} bound to {a[0]!r} in state {a[1]!r} also "
                        f"matches {b[0]!r} in state {b[1]!r} (ancestor/descendant) — "
                        f"one binding will silently shadow the other at runtime"
                    )

        if conflicts:
            lines = "\n  - ".join(conflicts)
            raise ValueError(
                f"Conflicting keybindings detected ({len(conflicts)}):\n  - {lines}\n"
                f'Pick a different key, or unbind a colliding action by setting '
                f'its key to null (e.g. "undo": null).'
            )
