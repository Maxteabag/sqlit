"""Hierarchical State Machine for UI action validation and binding display.

This module provides a clean architecture for determining:
1. Which actions are valid in the current UI context
2. Which key bindings to display in the footer

The hierarchy allows child states to inherit actions from parents while
adding or overriding specific behaviors.
"""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.leader_commands import get_leader_commands
from sqlit.core.state_base import (
    ActionResult,
    DisplayBinding,
    HelpEntry,
    State,
    resolve_display_key,
)
from sqlit.domains.explorer.state import (
    TreeFilterActiveState,
    TreeFocusedState,
    TreeOnConnectionState,
    TreeOnDatabaseState,
    TreeOnFolderState,
    TreeOnObjectState,
    TreeOnTableState,
)
from sqlit.domains.query.state import (
    AutocompleteActiveState,
    QueryFocusedState,
    QueryInsertModeState,
    QueryNormalModeState,
)
from sqlit.domains.results.state import (
    ResultsFilterActiveState,
    ResultsFocusedState,
    ValueViewActiveState,
)
from sqlit.domains.shell.state.leader_pending import LeaderPendingState
from sqlit.domains.shell.state.main_screen import MainScreenState
from sqlit.domains.shell.state.modal_active import ModalActiveState
from sqlit.domains.shell.state.query_executing import QueryExecutingState
from sqlit.domains.shell.state.root import RootState


class UIStateMachine:
    """Hierarchical state machine for UI action validation and binding display."""

    def __init__(self) -> None:
        self.root = RootState()

        self.modal_active = ModalActiveState(parent=self.root)

        self.query_executing = QueryExecutingState(parent=self.root)

        self.main_screen = MainScreenState(parent=self.root)

        self.leader_pending = LeaderPendingState(parent=self.main_screen)

        self.tree_focused = TreeFocusedState(parent=self.main_screen)
        self.tree_filter_active = TreeFilterActiveState(parent=self.main_screen)
        self.tree_on_connection = TreeOnConnectionState(parent=self.tree_focused)
        self.tree_on_database = TreeOnDatabaseState(parent=self.tree_focused)
        self.tree_on_table = TreeOnTableState(parent=self.tree_focused)
        self.tree_on_folder = TreeOnFolderState(parent=self.tree_focused)
        self.tree_on_object = TreeOnObjectState(parent=self.tree_focused)

        self.query_focused = QueryFocusedState(parent=self.main_screen)
        self.query_normal = QueryNormalModeState(parent=self.query_focused)
        self.query_insert = QueryInsertModeState(parent=self.query_focused)
        self.autocomplete_active = AutocompleteActiveState(parent=self.query_focused)

        self.results_focused = ResultsFocusedState(parent=self.main_screen)
        self.results_filter_active = ResultsFilterActiveState(parent=self.main_screen)
        self.value_view_active = ValueViewActiveState(parent=self.main_screen)

        self._states = [
            self.modal_active,
            self.query_executing,  # Before main_screen (more specific when query running)
            self.leader_pending,
            self.tree_filter_active,  # Before tree_focused (more specific when filter active)
            self.tree_on_connection,
            self.tree_on_database,  # For database nodes (multi-database servers)
            self.tree_on_table,
            self.tree_on_folder,
            self.tree_on_object,  # For index/trigger/sequence nodes
            self.tree_focused,
            self.autocomplete_active,  # Before query_insert (more specific)
            self.query_insert,
            self.query_normal,
            self.query_focused,
            self.results_filter_active,  # Before results_focused (more specific when filter active)
            self.value_view_active,  # Before results_focused (more specific when viewing cell)
            self.results_focused,
            self.main_screen,
            self.root,
        ]

    def get_active_state(self, app: InputContext) -> State:
        """Find the most specific active state."""
        for state in self._states:
            if state.is_active(app):
                return state
        return self.root

    def check_action(self, app: InputContext, action_name: str) -> bool:
        """Check if action is allowed in current state."""
        state = self.get_active_state(app)
        result = state.check_action(app, action_name)
        return result == ActionResult.ALLOWED

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        """Get bindings to display in footer for current state."""
        state = self.get_active_state(app)
        return state.get_display_bindings(app)

    def get_active_state_name(self, app: InputContext) -> str:
        """Get the name of the active state (for debugging)."""
        state = self.get_active_state(app)
        return state.__class__.__name__

    def generate_help_text(self) -> str:
        """Generate help text from all states' help entries."""
        entries_by_category: dict[str, list[HelpEntry]] = {}

        for state in self._states:
            for entry in state.get_help_entries():
                if entry.category not in entries_by_category:
                    entries_by_category[entry.category] = []
                existing_keys = {e.key for e in entries_by_category[entry.category]}
                if entry.key not in existing_keys:
                    entries_by_category[entry.category].append(entry)

        from sqlit.core.keymap import format_key

        leader_key = resolve_display_key("leader_key") or "<space>"
        delete_key = resolve_display_key("delete_leader_key") or "d"

        commands_category = f"Commands ({leader_key})"
        entries_by_category[commands_category] = [
            HelpEntry(f"{leader_key}+{format_key(cmd.key)}", cmd.label, commands_category)
            for cmd in get_leader_commands()
        ]

        delete_category = f"Delete ({delete_key})"
        entries_by_category[delete_category] = [
            HelpEntry(f"{delete_key}+{format_key(cmd.key)}", cmd.label, delete_category)
            for cmd in get_leader_commands("delete")
        ]

        # Add Connection picker section (modal dialog, not state-based)
        entries_by_category["Connection Picker"] = [
            HelpEntry("/", "Search connections", "Connection Picker"),
            HelpEntry("n", "New connection", "Connection Picker"),
            HelpEntry("e", "Edit connection", "Connection Picker"),
            HelpEntry("d", "Delete connection", "Connection Picker"),
            HelpEntry("s", "Save to config", "Connection Picker"),
            HelpEntry("<enter>", "Connect", "Connection Picker"),
            HelpEntry("<esc>", "Close", "Connection Picker"),
        ]

        category_order = [
            "Explorer",
            "Query Editor (Normal)",
            "Query Editor (Insert)",
            "Results",
            "Connection Picker",
            commands_category,
            delete_category,
            "General",
            "Navigation",
            "Query",
            "Value View",
        ]

        output = []
        for category in category_order:
            if category not in entries_by_category:
                continue
            output.append(f"\n{category}:")
            for entry in sorted(entries_by_category[category], key=lambda e: e.key):
                output.append(f"  {entry.key:<10} {entry.description}")

        return "\n".join(output)
