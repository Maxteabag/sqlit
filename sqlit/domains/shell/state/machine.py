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
        """Generate structured help text with organized sections."""
        from sqlit.core.keymap import format_key

        leader_key = resolve_display_key("leader_key") or "<space>"

        def section(title: str) -> str:
            return f"[bold cyan]{title}[/]"

        def subsection(title: str) -> str:
            return f"  [dim]{title}[/]"

        def binding(key: str, desc: str, indent: int = 4) -> str:
            pad = " " * indent
            return f"{pad}[bold yellow]{key:<12}[/] {desc}"

        lines: list[str] = []

        # ═══════════════════════════════════════════════════════════════════
        # NAVIGATION
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("NAVIGATION"))
        lines.append(binding("e", "Focus Explorer pane"))
        lines.append(binding("q", "Focus Query pane"))
        lines.append(binding("r", "Focus Results pane"))
        lines.append(binding(leader_key, "Open command menu"))
        lines.append(binding("?", "Show this help"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # EXPLORER
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("EXPLORER"))
        lines.append(binding("j/k", "Move cursor down/up"))
        lines.append(binding("<enter>", "Expand node / Connect"))
        lines.append(binding("s", "SELECT TOP 100 (on table/view)"))
        lines.append(binding("/", "Filter tree (fuzzy search)"))
        lines.append(binding("z", "Collapse all nodes"))
        lines.append(binding("f", "Refresh tree"))
        lines.append("")
        lines.append(subsection("On Connection Node:"))
        lines.append(binding("n", "New connection"))
        lines.append(binding("e", "Edit connection"))
        lines.append(binding("d", "Delete connection"))
        lines.append(binding("D", "Duplicate connection"))
        lines.append(binding("x", "Disconnect"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # QUERY EDITOR
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("QUERY EDITOR"))
        lines.append(subsection("Normal Mode:"))
        lines.append(binding("i", "Enter INSERT mode"))
        lines.append(binding("o/O", "Open line below/above"))
        lines.append(binding("<enter>/gr", "Execute query"))
        lines.append(binding("gt", "Execute as transaction"))
        lines.append(binding("<backspace>", "Query history"))
        lines.append(binding("N", "New query (clear)"))
        lines.append(binding("u", "Undo"))
        lines.append(binding("^r", "Redo"))
        lines.append("")
        lines.append(subsection("Insert Mode:"))
        lines.append(binding("<esc>", "Exit to NORMAL mode"))
        lines.append(binding("^<enter>", "Execute (stay in INSERT)"))
        lines.append(binding("<tab>", "Accept autocomplete"))
        lines.append(binding("^a", "Select all"))
        lines.append(binding("^c", "Copy selection"))
        lines.append(binding("^v", "Paste"))
        lines.append("")
        lines.append(subsection("Vim Operators (Normal Mode):"))
        lines.append(binding("y{motion}", "Copy"))
        lines.append(binding("d{motion}", "Delete"))
        lines.append(binding("c{motion}", "Change (delete + INSERT)"))
        lines.append(binding("p", "Paste after cursor"))
        lines.append("")
        lines.append(subsection("Vim Motions:"))
        lines.append(binding("h/j/k/l", "Cursor left/down/up/right"))
        lines.append(binding("w/W", "Word forward"))
        lines.append(binding("b/B", "Word backward"))
        lines.append(binding("e/E", "End of word"))
        lines.append(binding("0/$", "Line start/end"))
        lines.append(binding("gg/G", "File start/end"))
        lines.append(binding("f{c}/F{c}", "Find char forward/back"))
        lines.append(binding("t{c}/T{c}", "Till char forward/back"))
        lines.append(binding("%", "Matching bracket"))
        lines.append("")
        lines.append(subsection("Text Objects (with i=inner, a=around):"))
        lines.append(binding("iw/aw", "Word"))
        lines.append(binding('i"/a"', "Double quotes"))
        lines.append(binding("i'/a'", "Single quotes"))
        lines.append(binding("i)/a)", "Parentheses"))
        lines.append(binding("i}/a}", "Braces"))
        lines.append(binding("i]/a]", "Brackets"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # RESULTS
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("RESULTS"))
        lines.append(binding("h/j/k/l", "Navigate cells"))
        lines.append(binding("v", "Preview cell (inline)"))
        lines.append(binding("V", "View full cell value"))
        lines.append(binding("u", "Generate UPDATE statement"))
        lines.append(binding("/", "Filter rows"))
        lines.append(binding("x", "Clear results"))
        lines.append(binding("<tab>", "Next result set"))
        lines.append(binding("<s-tab>", "Previous result set"))
        lines.append(binding("z", "Collapse/expand result"))
        lines.append("")
        lines.append(subsection("Copy Menu (y):"))
        lines.append(binding("yc", "Copy cell"))
        lines.append(binding("yy", "Copy row"))
        lines.append(binding("ya", "Copy all"))
        lines.append(binding("ye", "Export menu..."))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # FILTERING
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("FILTERING"))
        lines.append(binding("/", "Open filter (Explorer/Results)"))
        lines.append(binding("<enter>", "Apply filter"))
        lines.append(binding("<esc>", "Close filter"))
        lines.append(binding("~prefix", "Fuzzy match mode"))
        lines.append(binding("n/N", "Next/prev match (Results)"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # COMMAND MENU
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section(f"COMMAND MENU ({leader_key})"))
        leader_cmds = get_leader_commands("leader")
        by_cat: dict[str, list[tuple[str, str]]] = {}
        for cmd in leader_cmds:
            if cmd.category not in by_cat:
                by_cat[cmd.category] = []
            by_cat[cmd.category].append((cmd.key, cmd.label))

        for cat in ["View", "Connection", "Actions"]:
            if cat in by_cat:
                lines.append(subsection(f"{cat}:"))
                for key, label in by_cat[cat]:
                    lines.append(binding(f"{leader_key}{key}", label))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # CONNECTION PICKER
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("CONNECTION PICKER"))
        lines.append(binding("/", "Search connections"))
        lines.append(binding("j/k", "Navigate list"))
        lines.append(binding("<enter>", "Connect to selected"))
        lines.append(binding("n", "New connection"))
        lines.append(binding("e", "Edit connection"))
        lines.append(binding("d", "Delete connection"))
        lines.append(binding("D", "Duplicate connection"))
        lines.append(binding("<esc>", "Close picker"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # GLOBAL
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("GLOBAL"))
        lines.append(binding("^q", "Quit"))
        lines.append(binding(f"{leader_key}q", "Quit (from menu)"))
        lines.append(binding(f"{leader_key}t", "Change theme"))
        lines.append(binding(f"{leader_key}f", "Toggle fullscreen pane"))
        lines.append(binding(f"{leader_key}e", "Toggle explorer visibility"))

        return "\n".join(lines)
