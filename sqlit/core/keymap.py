"""Core keymap definitions (UI-agnostic)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlit.shared.core.debug_events import emit_debug_event

KEY_DISPLAY_OVERRIDES: dict[str, str] = {
    "question_mark": "?",
    "slash": "/",
    "asterisk": "*",
    "circumflex_accent": "^",
    "dollar_sign": "$",
    "percent_sign": "%",
    "space": "<space>",
    "escape": "<esc>",
    "enter": "<enter>",
    "delete": "<del>",
    "backspace": "<backspace>",
    "tab": "<tab>",
    "shift+tab": "<s-tab>",
    "left": "<left>",
    "right": "<right>",
    "up": "<up>",
    "down": "<down>",
    "home": "<home>",
    "end": "<end>",
    "pageup": "<pgup>",
    "pagedown": "<pgdn>",
}


def format_key(key: str) -> str:
    """Format a key name for display in UI hints."""
    if key in KEY_DISPLAY_OVERRIDES:
        return KEY_DISPLAY_OVERRIDES[key]
    if key.startswith("ctrl+"):
        return f"^{key.split('+', 1)[1]}"
    return key


@dataclass
class LeaderCommandDef:
    """Definition of a leader command."""

    key: str  # The key to press (e.g., "q", "e")
    action: str  # The target action (e.g., "quit", "toggle_explorer")
    label: str  # Display label
    category: str  # Category for grouping ("View", "Connection", "Actions")
    guard: str | None = None  # Guard name (resolved at runtime)
    menu: str = "leader"  # Menu ID (supports multiple leader menus)


@dataclass
class ActionKeyDef:
    """Definition of a regular action keybinding."""

    key: str  # The key to press
    action: str  # The action name
    context: str | None = None  # Optional context hint (for documentation)
    guard: str | None = None  # Guard name (resolved at runtime)
    primary: bool = True  # Primary key for display vs secondary aliases
    show: bool = False  # Whether to show in Textual's binding hints
    priority: bool = False  # Whether to give priority to this binding


class KeymapProvider(ABC):
    """Abstract base class for keymap providers."""

    @abstractmethod
    def get_leader_commands(self) -> list[LeaderCommandDef]:
        """Get all leader command definitions."""
        raise NotImplementedError

    @abstractmethod
    def get_action_keys(self) -> list[ActionKeyDef]:
        """Get all regular action key definitions."""
        raise NotImplementedError

    def leader(self, action: str, menu: str | None = "leader") -> str | None:
        """Get the key for a leader command action."""
        for cmd in self.get_leader_commands():
            if cmd.action == action and (menu is None or cmd.menu == menu):
                return cmd.key
        return None

    def action(self, action_name: str) -> str | None:
        """Get the key for a regular action."""
        primary = None
        fallback = None
        for ak in self.get_action_keys():
            if ak.action != action_name:
                continue
            if fallback is None:
                fallback = ak.key
            if ak.primary and primary is None:
                primary = ak.key
        return primary or fallback

    def keys_for_action(self, action_name: str, *, include_secondary: bool = True) -> list[str]:
        """Get all keys for an action, primary first."""
        primary_keys: list[str] = []
        secondary_keys: list[str] = []
        seen: set[str] = set()
        for ak in self.get_action_keys():
            if ak.action != action_name:
                continue
            if ak.key in seen:
                continue
            seen.add(ak.key)
            if ak.primary:
                primary_keys.append(ak.key)
            elif include_secondary:
                secondary_keys.append(ak.key)
        return primary_keys + secondary_keys

    def actions_for_key(self, key: str) -> list[str]:
        """Get all actions bound to a key."""
        return [ak.action for ak in self.get_action_keys() if ak.key == key]


class DefaultKeymapProvider(KeymapProvider):
    """Default keymap with hardcoded bindings."""

    def __init__(self) -> None:
        self._leader_commands_cache: list[LeaderCommandDef] | None = None
        self._action_keys_cache: list[ActionKeyDef] | None = None
        self._leader_emitted: bool = False
        self._action_emitted: bool = False

    def _emit_leader_keybindings(self, commands: list[LeaderCommandDef]) -> None:
        for cmd in commands:
            emit_debug_event(
                "keybinding.register",
                category="keybinding",
                kind="leader",
                provider=self.__class__.__name__,
                key=cmd.key,
                action=cmd.action,
                label=cmd.label,
                group=cmd.category,
                menu=cmd.menu,
                guard=cmd.guard,
            )

    def _emit_action_keybindings(self, bindings: list[ActionKeyDef]) -> None:
        for binding in bindings:
            emit_debug_event(
                "keybinding.register",
                category="keybinding",
                kind="action",
                provider=self.__class__.__name__,
                key=binding.key,
                action=binding.action,
                context=binding.context,
                guard=binding.guard,
                primary=binding.primary,
                show=binding.show,
                priority=binding.priority,
            )

    def _ensure_leader_commands(self) -> list[LeaderCommandDef]:
        if self._leader_commands_cache is None:
            self._leader_commands_cache = self._build_leader_commands()
        return self._leader_commands_cache

    def _ensure_action_keys(self) -> list[ActionKeyDef]:
        if self._action_keys_cache is None:
            self._action_keys_cache = self._build_action_keys()
        return self._action_keys_cache

    def get_leader_commands(self) -> list[LeaderCommandDef]:
        commands = self._ensure_leader_commands()
        if not self._leader_emitted:
            self._emit_leader_keybindings(commands)
            self._leader_emitted = True
        return list(commands)

    def get_action_keys(self) -> list[ActionKeyDef]:
        bindings = self._ensure_action_keys()
        if not self._action_emitted:
            self._emit_action_keybindings(bindings)
            self._action_emitted = True
        return list(bindings)

    def _build_leader_commands(self) -> list[LeaderCommandDef]:
        return [
            # View
            LeaderCommandDef("e", "toggle_explorer", "Toggle Explorer", "View"),
            LeaderCommandDef("f", "toggle_fullscreen", "Toggle Maximize", "View"),
            # Connection
            LeaderCommandDef("c", "show_connection_picker", "Connect", "Connection"),
            LeaderCommandDef("x", "disconnect", "Disconnect", "Connection", guard="has_connection"),
            # Actions
            LeaderCommandDef("z", "cancel_operation", "Cancel", "Actions", guard="query_executing"),
            LeaderCommandDef("t", "change_theme", "Change Theme", "Actions"),
            LeaderCommandDef("h", "show_help", "Help", "Actions"),
            LeaderCommandDef("space", "telescope", "Telescope", "Actions"),
            LeaderCommandDef("slash", "telescope_filter", "Telescope Search", "Actions"),
            LeaderCommandDef("q", "quit", "Quit", "Actions"),
            # Delete menu (vim-style)
            LeaderCommandDef("d", "line", "Delete line", "Delete", menu="delete"),
            LeaderCommandDef("w", "word", "Delete word", "Delete", menu="delete"),
            LeaderCommandDef("W", "WORD", "Delete WORD", "Delete", menu="delete"),
            LeaderCommandDef("b", "word_back", "Delete word back", "Delete", menu="delete"),
            LeaderCommandDef("B", "WORD_back", "Delete WORD back", "Delete", menu="delete"),
            LeaderCommandDef("e", "word_end", "Delete to word end", "Delete", menu="delete"),
            LeaderCommandDef("E", "WORD_end", "Delete to WORD end", "Delete", menu="delete"),
            LeaderCommandDef("0", "line_start", "Delete to line start", "Delete", menu="delete"),
            LeaderCommandDef("dollar_sign", "line_end_motion", "Delete to line end", "Delete", menu="delete"),
            LeaderCommandDef("D", "line_end", "Delete to line end", "Delete", menu="delete"),
            LeaderCommandDef("x", "char", "Delete char", "Delete", menu="delete"),
            LeaderCommandDef("X", "char_back", "Delete char back", "Delete", menu="delete"),
            LeaderCommandDef("h", "left", "Delete left", "Delete", menu="delete"),
            LeaderCommandDef("j", "down", "Delete line down", "Delete", menu="delete"),
            LeaderCommandDef("k", "up", "Delete line up", "Delete", menu="delete"),
            LeaderCommandDef("l", "right", "Delete right", "Delete", menu="delete"),
            LeaderCommandDef("G", "to_end", "Delete to end", "Delete", menu="delete"),
            LeaderCommandDef("f", "find_char", "Delete to char...", "Delete", menu="delete"),
            LeaderCommandDef("F", "find_char_back", "Delete back to char...", "Delete", menu="delete"),
            LeaderCommandDef("t", "till_char", "Delete till char...", "Delete", menu="delete"),
            LeaderCommandDef("T", "till_char_back", "Delete back till char...", "Delete", menu="delete"),
            LeaderCommandDef("percent_sign", "matching_bracket", "Delete to bracket", "Delete", menu="delete"),
            LeaderCommandDef("i", "inner", "Delete inside...", "Delete", menu="delete"),
            LeaderCommandDef("a", "around", "Delete around...", "Delete", menu="delete"),
            # Copy menu (vim-style, y for yank)
            LeaderCommandDef("y", "line", "Copy line", "Copy", menu="yank"),
            LeaderCommandDef("w", "word", "Copy word", "Copy", menu="yank"),
            LeaderCommandDef("W", "WORD", "Copy WORD", "Copy", menu="yank"),
            LeaderCommandDef("b", "word_back", "Copy word back", "Copy", menu="yank"),
            LeaderCommandDef("B", "WORD_back", "Copy WORD back", "Copy", menu="yank"),
            LeaderCommandDef("e", "word_end", "Copy to word end", "Copy", menu="yank"),
            LeaderCommandDef("E", "WORD_end", "Copy to WORD end", "Copy", menu="yank"),
            LeaderCommandDef("0", "line_start", "Copy to line start", "Copy", menu="yank"),
            LeaderCommandDef("dollar_sign", "line_end_motion", "Copy to line end", "Copy", menu="yank"),
            LeaderCommandDef("h", "left", "Copy left", "Copy", menu="yank"),
            LeaderCommandDef("j", "down", "Copy line down", "Copy", menu="yank"),
            LeaderCommandDef("k", "up", "Copy line up", "Copy", menu="yank"),
            LeaderCommandDef("l", "right", "Copy right", "Copy", menu="yank"),
            LeaderCommandDef("G", "to_end", "Copy to end", "Copy", menu="yank"),
            LeaderCommandDef("f", "find_char", "Copy to char...", "Copy", menu="yank"),
            LeaderCommandDef("F", "find_char_back", "Copy back to char...", "Copy", menu="yank"),
            LeaderCommandDef("t", "till_char", "Copy till char...", "Copy", menu="yank"),
            LeaderCommandDef("T", "till_char_back", "Copy back till char...", "Copy", menu="yank"),
            LeaderCommandDef("percent_sign", "matching_bracket", "Copy to bracket", "Copy", menu="yank"),
            LeaderCommandDef("i", "inner", "Copy inside...", "Copy", menu="yank"),
            LeaderCommandDef("a", "around", "Copy around...", "Copy", menu="yank"),
            # Change menu (vim-style)
            LeaderCommandDef("c", "line", "Change line", "Change", menu="change"),
            LeaderCommandDef("w", "word", "Change word", "Change", menu="change"),
            LeaderCommandDef("W", "WORD", "Change WORD", "Change", menu="change"),
            LeaderCommandDef("b", "word_back", "Change word back", "Change", menu="change"),
            LeaderCommandDef("B", "WORD_back", "Change WORD back", "Change", menu="change"),
            LeaderCommandDef("e", "word_end", "Change to word end", "Change", menu="change"),
            LeaderCommandDef("E", "WORD_end", "Change to WORD end", "Change", menu="change"),
            LeaderCommandDef("0", "line_start", "Change to line start", "Change", menu="change"),
            LeaderCommandDef("dollar_sign", "line_end_motion", "Change to line end", "Change", menu="change"),
            LeaderCommandDef("h", "left", "Change left", "Change", menu="change"),
            LeaderCommandDef("j", "down", "Change line down", "Change", menu="change"),
            LeaderCommandDef("k", "up", "Change line up", "Change", menu="change"),
            LeaderCommandDef("l", "right", "Change right", "Change", menu="change"),
            LeaderCommandDef("G", "to_end", "Change to end", "Change", menu="change"),
            LeaderCommandDef("f", "find_char", "Change to char...", "Change", menu="change"),
            LeaderCommandDef("F", "find_char_back", "Change back to char...", "Change", menu="change"),
            LeaderCommandDef("t", "till_char", "Change till char...", "Change", menu="change"),
            LeaderCommandDef("T", "till_char_back", "Change back till char...", "Change", menu="change"),
            LeaderCommandDef("percent_sign", "matching_bracket", "Change to bracket", "Change", menu="change"),
            LeaderCommandDef("i", "inner", "Change inside...", "Change", menu="change"),
            LeaderCommandDef("a", "around", "Change around...", "Change", menu="change"),
            # g motion menu (vim-style)
            LeaderCommandDef("g", "first_line", "Go to first line", "Go to", menu="g"),
            LeaderCommandDef("e", "word_end_back", "End of prev word", "Go to", menu="g"),
            LeaderCommandDef("E", "WORD_end_back", "End of prev WORD", "Go to", menu="g"),
            LeaderCommandDef("c", "comment", "Toggle comment...", "Toggle", menu="g"),
            LeaderCommandDef("r", "execute_query", "Run query", "Execute", menu="g"),
            LeaderCommandDef("s", "execute_single_statement", "Run statement at cursor", "Execute", menu="g"),
            LeaderCommandDef("t", "execute_query_atomic", "Run as transaction", "Execute", menu="g"),
            # gc comment menu (vim-style)
            LeaderCommandDef("c", "line", "Toggle line comment", "Comment", menu="gc"),
            LeaderCommandDef("j", "down", "Comment line down", "Comment", menu="gc"),
            LeaderCommandDef("k", "up", "Comment line up", "Comment", menu="gc"),
            LeaderCommandDef("G", "to_end", "Comment to end", "Comment", menu="gc"),
            LeaderCommandDef("s", "selection", "Toggle selection", "Comment", menu="gc"),
            LeaderCommandDef("S", "statement", "Toggle statement", "Comment", menu="gc"),
            # ry results yank menu
            LeaderCommandDef("c", "cell", "Copy cell", "Copy", menu="ry"),
            LeaderCommandDef("y", "row", "Copy row", "Copy", menu="ry"),
            LeaderCommandDef("a", "all", "Copy all", "Copy", menu="ry"),
            LeaderCommandDef("e", "export", "Export...", "Export", menu="ry"),
            # rye results export menu
            LeaderCommandDef("c", "csv", "Export as CSV", "Export", menu="rye"),
            LeaderCommandDef("j", "json", "Export as JSON", "Export", menu="rye"),
            # vy value view yank menu (tree mode)
            LeaderCommandDef("y", "value", "Copy value", "Copy", menu="vy"),
            LeaderCommandDef("f", "field", "Copy field", "Copy", menu="vy"),
            LeaderCommandDef("a", "all", "Copy all", "Copy", menu="vy"),
        ]

    def _build_action_keys(self) -> list[ActionKeyDef]:
        return [
            # Tree actions
            ActionKeyDef("n", "new_connection", "tree"),
            ActionKeyDef("v", "enter_tree_visual_mode", "tree"),
            ActionKeyDef("escape", "exit_tree_visual_mode", "tree_visual"),
            ActionKeyDef("v", "exit_tree_visual_mode", "tree_visual", primary=False),
            ActionKeyDef("escape", "clear_connection_selection", "tree"),
            ActionKeyDef("s", "select_table", "tree"),
            ActionKeyDef("f", "refresh_tree", "tree"),
            ActionKeyDef("R", "refresh_tree", "tree", primary=False),
            ActionKeyDef("e", "edit_connection", "tree"),
            ActionKeyDef("M", "rename_connection_folder", "tree"),
            ActionKeyDef("d", "delete_connection_folder", "tree"),
            ActionKeyDef("delete", "delete_connection_folder", "tree", primary=False),
            ActionKeyDef("d", "delete_connection", "tree"),
            ActionKeyDef("delete", "delete_connection", "tree", primary=False),
            ActionKeyDef("D", "duplicate_connection", "tree"),
            ActionKeyDef("m", "move_connection_to_folder", "tree"),
            ActionKeyDef("x", "disconnect", "tree"),
            ActionKeyDef("z", "collapse_tree", "tree"),
            ActionKeyDef("j", "tree_cursor_down", "tree"),
            ActionKeyDef("down", "tree_cursor_down", "tree", primary=False),
            ActionKeyDef("k", "tree_cursor_up", "tree"),
            ActionKeyDef("up", "tree_cursor_up", "tree", primary=False),
            ActionKeyDef("slash", "tree_filter", "tree"),
            ActionKeyDef("escape", "tree_filter_close", "tree_filter"),
            ActionKeyDef("enter", "tree_filter_accept", "tree_filter"),
            # Global
            ActionKeyDef("space", "leader_key", "global", priority=True),
            ActionKeyDef("ctrl+q", "quit", "global"),
            ActionKeyDef("escape", "cancel_operation", "global"),
            ActionKeyDef("question_mark", "show_help", "global"),
            # Query (normal mode)
            ActionKeyDef("i", "enter_insert_mode", "query_normal"),
            ActionKeyDef("I", "prepend_insert_mode", "query_normal"),
            ActionKeyDef("o", "open_line_below", "query_normal"),
            ActionKeyDef("O", "open_line_above", "query_normal"),
            ActionKeyDef("enter", "execute_query", "query_normal"),
            ActionKeyDef("p", "paste", "query_normal"),
            ActionKeyDef("y", "yank_leader_key", "query_normal"),
            ActionKeyDef("c", "change_leader_key", "query_normal"),
            ActionKeyDef("g", "g_leader_key", "query_normal"),
            ActionKeyDef("backspace", "show_history", "query_normal"),
            ActionKeyDef("N", "new_query", "query_normal"),
            ActionKeyDef("d", "delete_leader_key", "query_normal"),
            ActionKeyDef("C", "change_line_end_motion", "query_normal"),
            ActionKeyDef("D", "delete_line_end", "query_normal"),
            ActionKeyDef("u", "undo", "query_normal"),
            ActionKeyDef("ctrl+r", "redo", "query_normal"),
            # Vim cursor movement (normal mode)
            ActionKeyDef("h", "cursor_left", "query_normal"),
            ActionKeyDef("j", "cursor_down", "query_normal"),
            ActionKeyDef("k", "cursor_up", "query_normal"),
            ActionKeyDef("l", "cursor_right", "query_normal"),
            ActionKeyDef("w", "cursor_word_forward", "query_normal"),
            ActionKeyDef("W", "cursor_WORD_forward", "query_normal"),
            ActionKeyDef("b", "cursor_word_back", "query_normal"),
            ActionKeyDef("B", "cursor_WORD_back", "query_normal"),
            ActionKeyDef("0", "cursor_line_start", "query_normal"),
            ActionKeyDef("circumflex_accent", "cursor_first_non_blank", "query_normal"),
            ActionKeyDef("dollar_sign", "cursor_line_end", "query_normal"),
            ActionKeyDef("G", "cursor_last_line", "query_normal"),
            ActionKeyDef("percent_sign", "cursor_matching_bracket", "query_normal"),
            ActionKeyDef("f", "cursor_find_char", "query_normal"),
            ActionKeyDef("F", "cursor_find_char_back", "query_normal"),
            ActionKeyDef("t", "cursor_till_char", "query_normal"),
            ActionKeyDef("T", "cursor_till_char_back", "query_normal"),
            ActionKeyDef("x", "delete_char", "query_normal"),
            ActionKeyDef("a", "append_insert_mode", "query_normal"),
            ActionKeyDef("A", "append_line_end", "query_normal"),
            # Query (insert mode)
            ActionKeyDef("escape", "exit_insert_mode", "query_insert"),
            ActionKeyDef("ctrl+enter", "execute_query_insert", "query_insert"),
            ActionKeyDef("tab", "autocomplete_accept", "query_insert"),
            # Navigation
            ActionKeyDef("e", "focus_explorer", "navigation"),
            ActionKeyDef("q", "focus_query", "navigation"),
            ActionKeyDef("r", "focus_results", "navigation"),
            # Query (autocomplete)
            ActionKeyDef("ctrl+j", "autocomplete_next", "autocomplete"),
            ActionKeyDef("ctrl+k", "autocomplete_prev", "autocomplete"),
            ActionKeyDef("escape", "autocomplete_close", "autocomplete"),
            # Clipboard (only in insert mode for vim consistency)
            ActionKeyDef("ctrl+a", "select_all", "query_insert"),
            ActionKeyDef("ctrl+c", "copy_selection", "query_insert"),
            ActionKeyDef("ctrl+v", "paste", "query_insert"),
            ActionKeyDef("ctrl+z", "undo", "global"),
            ActionKeyDef("ctrl+y", "redo", "global"),
            # Results
            ActionKeyDef("v", "view_cell", "results"),
            ActionKeyDef("V", "view_cell_full", "results"),
            ActionKeyDef("u", "edit_cell", "results"),
            ActionKeyDef("d", "delete_row", "results"),
            ActionKeyDef("y", "results_yank_leader_key", "results"),
            ActionKeyDef("x", "clear_results", "results"),
            ActionKeyDef("slash", "results_filter", "results"),
            ActionKeyDef("h", "results_cursor_left", "results"),
            ActionKeyDef("j", "results_cursor_down", "results"),
            ActionKeyDef("k", "results_cursor_up", "results"),
            ActionKeyDef("l", "results_cursor_right", "results"),
            ActionKeyDef("tab", "next_result_section", "results"),
            ActionKeyDef("shift+tab", "prev_result_section", "results"),
            ActionKeyDef("z", "toggle_result_section", "results"),
            ActionKeyDef("escape", "results_filter_close", "results_filter"),
            ActionKeyDef("enter", "results_filter_accept", "results_filter"),
            # Value view
            ActionKeyDef("q", "close_value_view", "value_view"),
            ActionKeyDef("escape", "close_value_view", "value_view"),
            ActionKeyDef("y", "copy_value_view", "value_view"),
            ActionKeyDef("t", "toggle_value_view_mode", "value_view"),
            ActionKeyDef("z", "collapse_all_json_nodes", "value_view"),
            ActionKeyDef("Z", "expand_all_json_nodes", "value_view"),
        ]


# Global keymap instance
_keymap_provider: KeymapProvider | None = None


def get_keymap() -> KeymapProvider:
    """Get the current keymap provider."""
    global _keymap_provider
    if _keymap_provider is None:
        _keymap_provider = DefaultKeymapProvider()
    return _keymap_provider


def set_keymap(provider: KeymapProvider) -> None:
    """Set the keymap provider (for testing or custom keymaps)."""
    global _keymap_provider
    _keymap_provider = provider
    emit_keybinding_snapshot(provider)


def reset_keymap() -> None:
    """Reset to default keymap provider."""
    global _keymap_provider
    _keymap_provider = None


def emit_keybinding_snapshot(provider: KeymapProvider | None = None) -> None:
    """Emit debug events for the current keymap bindings."""
    keymap = provider or get_keymap()
    if hasattr(keymap, "_ensure_leader_commands"):
        commands = keymap._ensure_leader_commands()  # type: ignore[attr-defined]
    else:
        commands = keymap.get_leader_commands()
    for cmd in commands:
        emit_debug_event(
            "keybinding.register",
            category="keybinding",
            source="snapshot",
            kind="leader",
            provider=keymap.__class__.__name__,
            key=cmd.key,
            action=cmd.action,
            label=cmd.label,
            group=cmd.category,
            menu=cmd.menu,
            guard=cmd.guard,
        )
    if hasattr(keymap, "_leader_emitted"):
        try:
            keymap._leader_emitted = True  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(keymap, "_ensure_action_keys"):
        bindings = keymap._ensure_action_keys()  # type: ignore[attr-defined]
    else:
        bindings = keymap.get_action_keys()
    for binding in bindings:
        emit_debug_event(
            "keybinding.register",
            category="keybinding",
            source="snapshot",
            kind="action",
            provider=keymap.__class__.__name__,
            key=binding.key,
            action=binding.action,
            context=binding.context,
            guard=binding.guard,
            primary=binding.primary,
            show=binding.show,
            priority=binding.priority,
        )
    if hasattr(keymap, "_action_emitted"):
        try:
            keymap._action_emitted = True  # type: ignore[attr-defined]
        except Exception:
            pass
