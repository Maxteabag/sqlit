"""Keymap provider for keybinding configuration.

This module provides a centralized, injectable keymap system that:
1. Defines all key -> action mappings in one place
2. Can be mocked in tests
3. Can eventually be loaded from JSON/config files

Usage:
    from sqlit.keymap import get_keymap

    keymap = get_keymap()
    key = keymap.leader("quit")  # Returns "q"
    key = keymap.action("new_connection")  # Returns "n"
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    pass


@dataclass
class LeaderCommandDef:
    """Definition of a leader command."""

    key: str  # The key to press (e.g., "q", "e")
    action: str  # The target action (e.g., "quit", "toggle_explorer")
    label: str  # Display label
    category: str  # Category for grouping ("View", "Connection", "Actions")
    guard: str | None = None  # Guard name (resolved at runtime)


@dataclass
class ActionKeyDef:
    """Definition of a regular action keybinding."""

    key: str  # The key to press
    action: str  # The action name
    context: str | None = None  # Optional context hint (for documentation)


class KeymapProvider(ABC):
    """Abstract base class for keymap providers."""

    @abstractmethod
    def get_leader_commands(self) -> list[LeaderCommandDef]:
        """Get all leader command definitions."""
        pass

    @abstractmethod
    def get_action_keys(self) -> list[ActionKeyDef]:
        """Get all regular action key definitions."""
        pass

    def leader(self, action: str) -> str | None:
        """Get the key for a leader command action."""
        for cmd in self.get_leader_commands():
            if cmd.action == action:
                return cmd.key
        return None

    def action(self, action_name: str) -> str | None:
        """Get the key for a regular action."""
        for ak in self.get_action_keys():
            if ak.action == action_name:
                return ak.key
        return None

    def actions_for_key(self, key: str) -> list[str]:
        """Get all actions bound to a key."""
        return [ak.action for ak in self.get_action_keys() if ak.key == key]


class DefaultKeymapProvider(KeymapProvider):
    """Default keymap with hardcoded bindings."""

    def get_leader_commands(self) -> list[LeaderCommandDef]:
        return [
            # View
            LeaderCommandDef("e", "toggle_explorer", "Toggle Explorer", "View"),
            LeaderCommandDef("f", "toggle_fullscreen", "Toggle Maximize", "View"),
            # Connection
            LeaderCommandDef("c", "show_connection_picker", "Connect", "Connection"),
            LeaderCommandDef(
                "x", "disconnect", "Disconnect", "Connection", guard="has_connection"
            ),
            # Actions
            LeaderCommandDef(
                "z", "cancel_operation", "Cancel", "Actions", guard="query_executing"
            ),
            LeaderCommandDef("t", "change_theme", "Change Theme", "Actions"),
            LeaderCommandDef("h", "show_help", "Help", "Actions"),
            LeaderCommandDef("q", "quit", "Quit", "Actions"),
        ]

    def get_action_keys(self) -> list[ActionKeyDef]:
        return [
            # Tree actions
            ActionKeyDef("n", "new_connection", "tree"),
            ActionKeyDef("s", "select_table", "tree"),
            ActionKeyDef("R", "refresh_tree", "tree"),
            ActionKeyDef("f", "refresh_tree", "tree"),
            ActionKeyDef("e", "edit_connection", "tree"),
            ActionKeyDef("d", "delete_connection", "tree"),
            ActionKeyDef("D", "duplicate_connection", "tree"),
            ActionKeyDef("delete", "delete_connection", "tree"),
            ActionKeyDef("x", "disconnect", "tree"),
            ActionKeyDef("z", "collapse_tree", "tree"),
            # Global
            ActionKeyDef("space", "leader_key", "global"),
            ActionKeyDef("ctrl+q", "quit", "global"),
            ActionKeyDef("question_mark", "show_help", "global"),
            # Navigation
            ActionKeyDef("e", "focus_explorer", "navigation"),
            ActionKeyDef("q", "focus_query", "navigation"),
            ActionKeyDef("r", "focus_results", "navigation"),
            # Query (normal mode)
            ActionKeyDef("i", "enter_insert_mode", "query_normal"),
            ActionKeyDef("escape", "exit_insert_mode", "query"),
            ActionKeyDef("enter", "execute_query", "query_normal"),
            ActionKeyDef("f5", "execute_query_insert", "query_insert"),
            ActionKeyDef("d", "clear_query", "query_normal"),
            ActionKeyDef("n", "new_query", "query_normal"),
            ActionKeyDef("h", "show_history", "query_normal"),
            # Results
            ActionKeyDef("v", "view_cell", "results"),
            ActionKeyDef("y", "copy_cell", "results"),
            ActionKeyDef("Y", "copy_row", "results"),
            ActionKeyDef("a", "copy_results", "results"),
            # Cancel
            ActionKeyDef("ctrl+c", "cancel_operation", "global"),
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


def reset_keymap() -> None:
    """Reset to default keymap provider."""
    global _keymap_provider
    _keymap_provider = None
