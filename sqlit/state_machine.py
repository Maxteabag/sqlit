"""Hierarchical State Machine for UI action validation and binding display.

This module provides a clean architecture for determining:
1. Which actions are valid in the current UI context
2. Which key bindings to display in the footer

The hierarchy allows child states to inherit actions from parents while
adding or overriding specific behaviors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from .ui.tree_nodes import (
    ConnectionNode,
    DatabaseNode,
    FolderNode,
    SchemaNode,
    TableNode,
    ViewNode,
)

if TYPE_CHECKING:
    from .app import SSMSTUI

# Guards are referenced by name from the keymap.
LEADER_GUARDS: dict[str, Callable[[SSMSTUI], bool]] = {
    "has_connection": lambda app: app.current_connection is not None,
    "query_executing": lambda app: getattr(app, "_query_executing", False),
}


@dataclass
class LeaderCommand:
    """Definition of a leader command accessible via space+key."""

    key: str  # The key to press (e.g., "q", "e")
    action: str  # The underlying action to execute (e.g., "quit", "toggle_explorer")
    label: str  # Display label (e.g., "Quit", "Toggle Explorer")
    category: str  # For grouping in the menu ("View", "Connection", "Actions")
    guard: Callable[[SSMSTUI], bool] | None = None  # Optional guard function

    @property
    def binding_action(self) -> str:
        """The action name used in Textual bindings (leader_prefixed)."""
        return f"leader_{self.action}"

    def is_allowed(self, app: SSMSTUI) -> bool:
        """Check if this command is currently allowed."""
        if self.guard is None:
            return True
        return self.guard(app)


def _build_leader_commands() -> list[LeaderCommand]:
    """Build leader commands from the keymap provider."""
    from .keymap import get_keymap

    keymap = get_keymap()
    commands = []

    for cmd_def in keymap.get_leader_commands():
        guard = LEADER_GUARDS.get(cmd_def.guard) if cmd_def.guard else None
        commands.append(
            LeaderCommand(
                key=cmd_def.key,
                action=cmd_def.action,
                label=cmd_def.label,
                category=cmd_def.category,
                guard=guard,
            )
        )

    return commands


def get_leader_commands() -> list[LeaderCommand]:
    """Get leader commands (rebuilt from keymap each time for testability)."""
    return _build_leader_commands()


def get_leader_binding_actions() -> set[str]:
    """Get set of leader binding action names."""
    return {cmd.binding_action for cmd in get_leader_commands()}


def get_leader_bindings() -> tuple:
    """Generate Textual Bindings from leader commands."""
    from textual.binding import Binding

    return tuple(Binding(cmd.key, cmd.binding_action, show=False) for cmd in get_leader_commands())


class ActionResult(Enum):
    """Result of checking an action in a state."""

    ALLOWED = auto()  # Action is allowed
    FORBIDDEN = auto()  # Action is explicitly forbidden
    UNHANDLED = auto()  # State doesn't handle this action (delegate to parent)


@dataclass
class DisplayBinding:
    """A binding to display in the footer."""

    key: str  # Display key (e.g., "enter", "y", "<space>")
    label: str  # Human-readable label (e.g., "Connect", "Yes")
    action: str  # Action name for reference


@dataclass
class HelpEntry:
    """An entry for the help text."""

    key: str  # Display key (e.g., "enter", "s")
    description: str  # Help description (e.g., "Select TOP 100")
    category: str  # Category name (e.g., "Explorer")


@dataclass
class ActionSpec:
    """Specification for an action."""

    guard: Callable[[SSMSTUI], bool] | None = None
    display_key: str | None = None
    display_label: str | None = None
    help_key: str | None = None
    help_description: str | None = None

    def is_allowed(self, app: SSMSTUI) -> bool:
        if self.guard is None:
            return True
        return self.guard(app)

    def get_display_binding(self, action_name: str) -> DisplayBinding | None:
        if self.display_key and self.display_label:
            return DisplayBinding(
                key=self.display_key,
                label=self.display_label,
                action=action_name,
            )
        return None

    def get_help_entry(self, category: str) -> HelpEntry | None:
        """Get help entry if help info is defined."""
        if self.help_key and self.help_description:
            return HelpEntry(
                key=self.help_key,
                description=self.help_description,
                category=category,
            )
        return None


class State(ABC):
    """Base class for hierarchical states."""

    help_category: str | None = None

    def __init__(self, parent: State | None = None):
        self.parent = parent
        self._actions: dict[str, ActionSpec] = {}
        self._forbidden: set[str] = set()
        self._display_order: list[str] = []
        self._right_bindings: list[str] = []
        self._setup_actions()

    @abstractmethod
    def _setup_actions(self) -> None:
        """Override to define actions handled by this state."""
        pass

    def allows(
        self,
        action_name: str,
        guard: Callable[[SSMSTUI], bool] | None = None,
        *,
        key: str | None = None,
        label: str | None = None,
        right: bool = False,
        help: str | None = None,
        help_key: str | None = None,
    ) -> None:
        """Register an action as allowed in this state.

        Args:
            action_name: The action identifier
            guard: Optional predicate that must return True for action to be allowed
            key: Display key for footer (if showing in footer)
            label: Display label for footer (if showing in footer)
            right: If True, show on right side of footer
            help: Help description for help screen (uses key param if help_key not set)
            help_key: Override key displayed in help (defaults to key param)
        """
        self._actions[action_name] = ActionSpec(
            guard=guard,
            display_key=key,
            display_label=label,
            help_key=help_key or key,
            help_description=help,
        )
        if key and label:
            if right:
                self._right_bindings.append(action_name)
            else:
                self._display_order.append(action_name)

    def get_help_entries(self) -> list[HelpEntry]:
        """Get all help entries from this state."""
        entries = []
        if self.help_category:
            for action_name, spec in self._actions.items():
                entry = spec.get_help_entry(self.help_category)
                if entry:
                    entries.append(entry)
        return entries

    def forbids(self, *action_names: str) -> None:
        """Explicitly forbid actions (blocks parent allowance)."""
        self._forbidden.update(action_names)

    def check_action(self, app: SSMSTUI, action_name: str) -> ActionResult:
        """Check if action is allowed in this state or ancestors."""
        if action_name in self._forbidden:
            return ActionResult.FORBIDDEN

        if action_name in self._actions:
            spec = self._actions[action_name]
            if spec.is_allowed(app):
                return ActionResult.ALLOWED
            return ActionResult.FORBIDDEN

        if self.parent:
            return self.parent.check_action(app, action_name)

        return ActionResult.UNHANDLED

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        """Get bindings to display in footer (left, right).

        Returns bindings from this state and ancestors, with this state's
        bindings taking precedence in display order.
        """
        left: list[DisplayBinding] = []
        right: list[DisplayBinding] = []
        seen: set[str] = set()

        for action_name in self._display_order:
            if action_name in seen:
                continue
            spec = self._actions.get(action_name)
            if spec and spec.is_allowed(app):
                binding = spec.get_display_binding(action_name)
                if binding:
                    left.append(binding)
                    seen.add(action_name)

        for action_name in self._right_bindings:
            if action_name in seen:
                continue
            spec = self._actions.get(action_name)
            if spec and spec.is_allowed(app):
                binding = spec.get_display_binding(action_name)
                if binding:
                    right.append(binding)
                    seen.add(action_name)

        if self.parent:
            parent_left, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    @abstractmethod
    def is_active(self, app: SSMSTUI) -> bool:
        """Return True if this state is currently active."""
        pass


class RootState(State):
    """Root state - minimal actions available everywhere."""

    help_category = "General"

    def _setup_actions(self) -> None:
        self.allows("quit", help="Quit", help_key="^q")
        self.allows("show_help", help="Show this help", help_key="?")
        self.allows("leader_key", help="Commands menu", help_key="<space>")

    def is_active(self, app: SSMSTUI) -> bool:
        return True


class ModalActiveState(State):
    """State when a modal screen is active.

    This state blocks all main app actions - the modal screen
    handles its own bindings via Textual's binding chain.
    We return empty bindings since the modal provides its own UI.
    """

    def _setup_actions(self) -> None:
        pass

    def check_action(self, app: SSMSTUI, action_name: str) -> ActionResult:
        if action_name in ("quit",):
            return ActionResult.ALLOWED
        return ActionResult.FORBIDDEN

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        return [], []

    def is_active(self, app: SSMSTUI) -> bool:
        from textual.screen import ModalScreen

        return any(isinstance(screen, ModalScreen) for screen in app.screen_stack[1:])


class MainScreenState(State):
    """Base state for main screen (no modal active)."""

    help_category = "Navigation"

    def _setup_actions(self) -> None:
        self.allows("focus_explorer", help="Focus Explorer", help_key="e")
        self.allows("focus_query", help="Focus Query", help_key="q")
        self.allows("focus_results", help="Focus Results", help_key="r")
        self.allows("toggle_fullscreen", help="Toggle fullscreen", help_key="f")
        self.allows("show_help")
        self.allows("change_theme")
        self.allows("leader_key", key="<space>", label="Commands", right=True)

    def is_active(self, app: SSMSTUI) -> bool:
        from textual.screen import ModalScreen

        if any(isinstance(screen, ModalScreen) for screen in app.screen_stack[1:]):
            return False
        # Defer to QueryExecutingState if a query is running
        return not getattr(app, "_query_executing", False)


class QueryExecutingState(State):
    """State when a query is being executed."""

    help_category = "Query"

    def _setup_actions(self) -> None:
        self.allows("cancel_operation", key="^z", label="Cancel", help="Cancel query")
        self.allows("quit")

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = [
            DisplayBinding(key="^z", label="Cancel", action="cancel_operation"),
        ]
        return left, []

    def is_active(self, app: SSMSTUI) -> bool:
        from textual.screen import ModalScreen

        if any(isinstance(screen, ModalScreen) for screen in app.screen_stack[1:]):
            return False
        return getattr(app, "_query_executing", False)


class LeaderPendingState(State):
    """State when waiting for leader combo key.

    Uses get_leader_commands() to determine which actions are valid leader targets.
    """

    def _setup_actions(self) -> None:
        pass

    def check_action(self, app: SSMSTUI, action_name: str) -> ActionResult:
        leader_binding_actions = get_leader_binding_actions()
        if action_name in leader_binding_actions:
            leader_commands = get_leader_commands()
            cmd = next((c for c in leader_commands if c.binding_action == action_name), None)
            if cmd and cmd.is_allowed(app):
                return ActionResult.ALLOWED
            return ActionResult.FORBIDDEN

        if action_name == "leader_key":
            return ActionResult.ALLOWED

        return ActionResult.FORBIDDEN

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        return [], [DisplayBinding(key="...", label="Waiting", action="leader_pending")]

    def is_active(self, app: SSMSTUI) -> bool:
        return getattr(app, "_leader_pending", False)


class TreeFilterActiveState(State):
    """State when tree filter is active."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows("tree_filter_close", help="Close filter", help_key="esc")
        self.allows("tree_filter_accept", help="Select item", help_key="enter")
        self.allows("tree_filter_next", help="Next match", help_key="n/j")
        self.allows("tree_filter_prev", help="Previous match", help_key="N/k")
        self.allows("quit")
        self.forbids(
            "focus_explorer",
            "focus_query",
            "focus_results",
            "leader_key",
            "new_connection",
            "tree_filter",
        )

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = [
            DisplayBinding(key="esc", label="Close", action="tree_filter_close"),
            DisplayBinding(key="enter", label="Select", action="tree_filter_accept"),
            DisplayBinding(key="n/N", label="Next/Prev", action="tree_filter_next"),
        ]
        return left, []

    def is_active(self, app: SSMSTUI) -> bool:
        return (
            app.object_tree.has_focus
            and getattr(app, "_tree_filter_visible", False)
        )


class TreeFocusedState(State):
    """Base state when tree has focus."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows("new_connection", key="n", label="New", help="New connection")
        self.allows("refresh_tree", key="f", label="Refresh", help="Refresh tree", help_key="R/f")
        self.allows("collapse_tree", help="Collapse all", help_key="z")
        self.allows("tree_cursor_down")  # vim j
        self.allows("tree_cursor_up")  # vim k
        self.allows("tree_filter", help="Filter tree", help_key="/")

    def is_active(self, app: SSMSTUI) -> bool:
        if not app.object_tree.has_focus:
            return False
        # Defer to TreeFilterActiveState if filter is visible
        return not getattr(app, "_tree_filter_visible", False)


class TreeOnConnectionState(State):
    """Tree focused on a connection node."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        def can_connect(app: SSMSTUI) -> bool:
            node = app.object_tree.cursor_node
            if not node or not isinstance(node.data, ConnectionNode):
                return False
            config = node.data.config
            if not app.current_connection:
                return True
            return bool(config and app.current_config and config.name != app.current_config.name)

        def is_connected_to_this(app: SSMSTUI) -> bool:
            node = app.object_tree.cursor_node
            if not node or not isinstance(node.data, ConnectionNode):
                return False
            config = node.data.config
            return bool(
                app.current_connection is not None
                and config
                and app.current_config
                and config.name == app.current_config.name
            )

        self.allows("connect_selected", can_connect, key="enter", label="Connect", help="Connect/Expand/Columns")
        self.allows("disconnect", is_connected_to_this, key="x", label="Disconnect", help="Disconnect")
        self.allows("edit_connection", key="e", label="Edit", help="Edit connection")
        self.allows("delete_connection", key="d", label="Delete", help="Delete connection")
        self.allows("duplicate_connection", key="D", label="Duplicate", help="Duplicate connection")

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        """Custom display logic for connection node."""
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        node = app.object_tree.cursor_node
        config = node.data.config if node and isinstance(node.data, ConnectionNode) else None
        is_connected = (
            app.current_connection is not None
            and config
            and app.current_config
            and config.name == app.current_config.name
        )

        if is_connected:
            left.append(DisplayBinding(key="x", label="Disconnect", action="disconnect"))
            seen.add("disconnect")
            seen.add("connect_selected")
        else:
            left.append(DisplayBinding(key="enter", label="Connect", action="connect_selected"))
            seen.add("connect_selected")
            seen.add("disconnect")

        left.append(DisplayBinding(key="n", label="New", action="new_connection"))
        seen.add("new_connection")
        left.append(DisplayBinding(key="e", label="Edit", action="edit_connection"))
        seen.add("edit_connection")
        left.append(DisplayBinding(key="D", label="Duplicate", action="duplicate_connection"))
        seen.add("duplicate_connection")
        left.append(DisplayBinding(key="d", label="Delete", action="delete_connection"))
        seen.add("delete_connection")
        left.append(DisplayBinding(key="f", label="Refresh", action="refresh_tree"))
        seen.add("refresh_tree")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: SSMSTUI) -> bool:
        if not app.object_tree.has_focus:
            return False
        node = app.object_tree.cursor_node
        return node is not None and isinstance(node.data, ConnectionNode)


class TreeOnTableState(State):
    """Tree focused on table or view node."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows("select_table", key="s", label="Select TOP 100", help="Select TOP 100 (table/view)")

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(DisplayBinding(key="enter", label="Columns", action="toggle_node"))
        seen.add("toggle_node")
        left.append(DisplayBinding(key="s", label="Select TOP 100", action="select_table"))
        seen.add("select_table")
        left.append(DisplayBinding(key="f", label="Refresh", action="refresh_tree"))
        seen.add("refresh_tree")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: SSMSTUI) -> bool:
        if not app.object_tree.has_focus:
            return False
        node = app.object_tree.cursor_node
        return node is not None and isinstance(node.data, TableNode | ViewNode)


class TreeOnFolderState(State):
    """Tree focused on a folder, database, or schema node."""

    def _setup_actions(self) -> None:
        pass  # Just inherits from parent

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(DisplayBinding(key="enter", label="Expand", action="toggle_node"))
        seen.add("toggle_node")
        left.append(DisplayBinding(key="f", label="Refresh", action="refresh_tree"))
        seen.add("refresh_tree")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: SSMSTUI) -> bool:
        if not app.object_tree.has_focus:
            return False
        node = app.object_tree.cursor_node
        return node is not None and isinstance(node.data, FolderNode | DatabaseNode | SchemaNode)


class QueryFocusedState(State):
    """Base state when query editor has focus."""

    def _setup_actions(self) -> None:
        pass

    def is_active(self, app: SSMSTUI) -> bool:
        return app.query_input.has_focus


class QueryNormalModeState(State):
    """Query editor in NORMAL mode."""

    help_category = "Query Editor (Normal)"

    def _setup_actions(self) -> None:
        self.allows("enter_insert_mode", key="i", label="Insert Mode", help="Enter INSERT mode")
        self.allows("execute_query", key="enter", label="Execute", help="Execute query")
        self.allows("clear_query", key="d", label="Clear", help="Clear query")
        self.allows("new_query", key="n", label="New", help="New query (clear all)")
        self.allows("copy_context", key="y", label="Copy query", help="Copy current query")
        self.allows(
            "show_history",
            lambda app: app.current_config is not None,
            key="h",
            label="History",
            help="Query history",
        )

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(DisplayBinding(key="i", label="Insert Mode", action="enter_insert_mode"))
        seen.add("enter_insert_mode")
        left.append(DisplayBinding(key="enter", label="Execute", action="execute_query"))
        seen.add("execute_query")

        left.append(DisplayBinding(key="y", label="Copy query", action="copy_context"))
        seen.add("copy_context")

        if app.current_config is not None:
            left.append(DisplayBinding(key="h", label="History", action="show_history"))
        seen.add("show_history")

        left.append(DisplayBinding(key="d", label="Clear", action="clear_query"))
        seen.add("clear_query")
        left.append(DisplayBinding(key="n", label="New", action="new_query"))
        seen.add("new_query")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: SSMSTUI) -> bool:
        from .widgets import VimMode

        return app.query_input.has_focus and app.vim_mode == VimMode.NORMAL


class QueryInsertModeState(State):
    """Query editor in INSERT mode."""

    help_category = "Query Editor (Insert)"

    def _setup_actions(self) -> None:
        self.allows("exit_insert_mode", key="esc", label="Normal Mode", help="Exit to NORMAL mode")
        self.allows("execute_query_insert", key="f5", label="Execute", help="Execute query (stay INSERT)")
        self.allows("autocomplete_accept", help="Accept autocomplete", help_key="tab")
        self.allows("quit")
        self.forbids(
            "focus_explorer",
            "focus_results",
            "leader_key",
            "new_connection",
            "show_help",
        )

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = [
            DisplayBinding(key="esc", label="Normal Mode", action="exit_insert_mode"),
            DisplayBinding(key="f5", label="Execute", action="execute_query_insert"),
            DisplayBinding(key="tab", label="Autocomplete", action="autocomplete_accept"),
        ]
        return left, []

    def is_active(self, app: SSMSTUI) -> bool:
        from .widgets import VimMode

        if not app.query_input.has_focus or app.vim_mode != VimMode.INSERT:
            return False
        # Defer to AutocompleteActiveState if autocomplete is visible
        return not getattr(app, "_autocomplete_visible", False)


class AutocompleteActiveState(State):
    """Query editor with autocomplete dropdown visible."""

    help_category = "Query Editor (Insert)"

    def _setup_actions(self) -> None:
        self.allows("autocomplete_next", help="Next suggestion", help_key="^j")
        self.allows("autocomplete_prev", help="Previous suggestion", help_key="^k")
        self.allows("autocomplete_accept", help="Accept autocomplete", help_key="tab")
        self.allows("autocomplete_close", help="Close autocomplete", help_key="esc")
        self.allows("execute_query_insert")
        self.allows("quit")
        self.forbids(
            "exit_insert_mode",  # Escape closes autocomplete, not exits insert mode
            "focus_explorer",
            "focus_results",
            "leader_key",
            "new_connection",
            "show_help",
        )

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = [
            DisplayBinding(key="tab", label="Accept", action="autocomplete_accept"),
            DisplayBinding(key="^j/^k", label="Next/Prev", action="autocomplete_next"),
            DisplayBinding(key="esc", label="Close", action="autocomplete_close"),
        ]
        return left, []

    def is_active(self, app: SSMSTUI) -> bool:
        from .widgets import VimMode

        return (
            app.query_input.has_focus
            and app.vim_mode == VimMode.INSERT
            and getattr(app, "_autocomplete_visible", False)
        )


class ResultsFocusedState(State):
    """Results table has focus."""

    help_category = "Results"

    def _setup_actions(self) -> None:
        self.allows("view_cell", key="v", label="View cell", help="View selected cell")
        self.allows("edit_cell", key="u", label="Update cell", help="Update cell (generate UPDATE)")
        self.allows("copy_context", key="y", label="Copy cell", help="Copy selected cell")
        self.allows("copy_row", key="Y", label="Copy row", help="Copy selected row")
        self.allows("copy_results", key="a", label="Copy all", help="Copy all results")
        self.allows("results_cursor_left")  # vim h
        self.allows("results_cursor_down")  # vim j
        self.allows("results_cursor_up")  # vim k
        self.allows("results_cursor_right")  # vim l

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        is_error = getattr(app, "_last_result_columns", []) == ["Error"]

        if is_error:
            left.append(DisplayBinding(key="v", label="View error", action="view_cell"))
            left.append(DisplayBinding(key="y", label="Copy error", action="copy_context"))
        else:
            left.append(DisplayBinding(key="v", label="View cell", action="view_cell"))
            left.append(DisplayBinding(key="u", label="Update", action="edit_cell"))
            left.append(DisplayBinding(key="y", label="Copy cell", action="copy_context"))
            left.append(DisplayBinding(key="Y", label="Copy row", action="copy_row"))
            left.append(DisplayBinding(key="a", label="Copy all", action="copy_results"))

        seen.update(["view_cell", "copy_context", "copy_row", "copy_results"])

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: SSMSTUI) -> bool:
        try:
            return app.results_table.has_focus
        except Exception:
            # Results table may not exist yet (Lazy loading)
            return False


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
        self.tree_on_table = TreeOnTableState(parent=self.tree_focused)
        self.tree_on_folder = TreeOnFolderState(parent=self.tree_focused)

        self.query_focused = QueryFocusedState(parent=self.main_screen)
        self.query_normal = QueryNormalModeState(parent=self.query_focused)
        self.query_insert = QueryInsertModeState(parent=self.query_focused)
        self.autocomplete_active = AutocompleteActiveState(parent=self.query_focused)

        self.results_focused = ResultsFocusedState(parent=self.main_screen)

        self._states = [
            self.modal_active,
            self.query_executing,  # Before main_screen (more specific when query running)
            self.leader_pending,
            self.tree_filter_active,  # Before tree_focused (more specific when filter active)
            self.tree_on_connection,
            self.tree_on_table,
            self.tree_on_folder,
            self.tree_focused,
            self.autocomplete_active,  # Before query_insert (more specific)
            self.query_insert,
            self.query_normal,
            self.query_focused,
            self.results_focused,
            self.main_screen,
            self.root,
        ]

    def get_active_state(self, app: SSMSTUI) -> State:
        """Find the most specific active state."""
        for state in self._states:
            if state.is_active(app):
                return state
        return self.root

    def check_action(self, app: SSMSTUI, action_name: str) -> bool:
        """Check if action is allowed in current state."""
        state = self.get_active_state(app)
        result = state.check_action(app, action_name)
        return result == ActionResult.ALLOWED

    def get_display_bindings(self, app: SSMSTUI) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        """Get bindings to display in footer for current state."""
        state = self.get_active_state(app)
        return state.get_display_bindings(app)

    def get_active_state_name(self, app: SSMSTUI) -> str:
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

        entries_by_category["Commands (<space>)"] = [
            HelpEntry(f"<space>+{cmd.key}", cmd.label, "Commands (<space>)") for cmd in get_leader_commands()
        ]

        category_order = [
            "Explorer",
            "Query Editor (Normal)",
            "Query Editor (Insert)",
            "Results",
            "Navigation",
            "Commands (<space>)",
            "General",
        ]

        lines = []
        for category in category_order:
            if category not in entries_by_category:
                continue
            entries = entries_by_category[category]
            if not entries:
                continue

            lines.append(f"[bold]{category}:[/]")
            for entry in entries:
                key_display = self._format_key_for_help(entry.key).ljust(10)
                lines.append(f"  {key_display} {entry.description}")
            lines.append("")

        return "\n".join(lines).rstrip()

    @staticmethod
    def _format_key_for_help(key: str) -> str:
        """Format a key for help display, wrapping special keys in angle brackets."""
        special_keys = {
            "enter",
            "space",
            "esc",
            "escape",
            "tab",
            "delete",
            "backspace",
            "up",
            "down",
            "left",
            "right",
            "home",
            "end",
            "pageup",
            "pagedown",
            "f1",
            "f2",
            "f3",
            "f4",
            "f5",
            "f6",
            "f7",
            "f8",
            "f9",
            "f10",
            "f11",
            "f12",
        }

        if key.lower() in special_keys:
            return f"<{key}>"
        if key.startswith("^") or key.startswith("<"):
            return key
        return key
