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
    State,
    resolve_display_key,
)
from sqlit.domains.explorer.state import (
    TreeFilterActiveState,
    TreeFocusedState,
    TreeMultiSelectState,
    TreeOnConnectionState,
    TreeOnDatabaseState,
    TreeOnFolderState,
    TreeOnObjectState,
    TreeOnTableState,
    TreeVisualModeState,
)
from sqlit.domains.query.state import (
    AutocompleteActiveState,
    QueryFocusedState,
    QueryInsertModeState,
    QueryNormalModeState,
    QueryVisualModeState,
    QueryVisualLineModeState,
)
from sqlit.domains.results.state import (
    ResultsFilterActiveState,
    ResultsFocusedState,
    ValueViewActiveState,
    ValueViewSyntaxModeState,
    ValueViewTreeModeState,
)
from sqlit.domains.shell.state.help_doc import HelpSection
from sqlit.domains.shell.state.leader_pending import LeaderPendingState
from sqlit.domains.shell.state.main_screen import MainScreenState
from sqlit.domains.shell.state.modal_active import ModalActiveState
from sqlit.domains.shell.state.root import RootState


STATE_TO_HELP_SECTION: dict[str, str] = {
    "QueryInsertModeState": "query_insert",
    "AutocompleteActiveState": "query_insert",
    "QueryNormalModeState": "query_normal",
    "QueryFocusedState": "query_normal",
    "QueryVisualModeState": "query_visual",
    "QueryVisualLineModeState": "query_visual_line",
    "TreeFilterActiveState": "filtering",
    "TreeOnConnectionState": "explorer_connection",
    "TreeOnDatabaseState": "explorer",
    "TreeOnTableState": "explorer",
    "TreeOnFolderState": "explorer",
    "TreeOnObjectState": "explorer",
    "TreeVisualModeState": "explorer",
    "TreeMultiSelectState": "explorer",
    "TreeFocusedState": "explorer",
    "ResultsFilterActiveState": "filtering",
    "ResultsFocusedState": "results",
    "ValueViewActiveState": "results",
    "ValueViewTreeModeState": "results",
    "ValueViewSyntaxModeState": "results",
    "LeaderPendingState": "command_menu",
}


class UIStateMachine:
    """Hierarchical state machine for UI action validation and binding display."""

    def __init__(self) -> None:
        self.root = RootState()

        self.modal_active = ModalActiveState(parent=self.root)

        self.main_screen = MainScreenState(parent=self.root)

        self.leader_pending = LeaderPendingState(parent=self.main_screen)

        self.tree_focused = TreeFocusedState(parent=self.main_screen)
        self.tree_filter_active = TreeFilterActiveState(parent=self.main_screen)
        self.tree_visual_mode = TreeVisualModeState(parent=self.tree_focused)
        self.tree_multi_select = TreeMultiSelectState(parent=self.tree_focused)
        self.tree_on_connection = TreeOnConnectionState(parent=self.tree_focused)
        self.tree_on_database = TreeOnDatabaseState(parent=self.tree_focused)
        self.tree_on_table = TreeOnTableState(parent=self.tree_focused)
        self.tree_on_folder = TreeOnFolderState(parent=self.tree_focused)
        self.tree_on_object = TreeOnObjectState(parent=self.tree_focused)

        self.query_focused = QueryFocusedState(parent=self.main_screen)
        self.query_visual = QueryVisualModeState(parent=self.query_focused)
        self.query_visual_line = QueryVisualLineModeState(parent=self.query_focused)
        self.query_normal = QueryNormalModeState(parent=self.query_focused)
        self.query_insert = QueryInsertModeState(parent=self.query_focused)
        self.autocomplete_active = AutocompleteActiveState(parent=self.query_focused)

        self.results_focused = ResultsFocusedState(parent=self.main_screen)
        self.results_filter_active = ResultsFilterActiveState(parent=self.main_screen)
        self.value_view_active = ValueViewActiveState(parent=self.main_screen)
        self.value_view_tree_mode = ValueViewTreeModeState(parent=self.value_view_active)
        self.value_view_syntax_mode = ValueViewSyntaxModeState(parent=self.value_view_active)

        self._states = [
            self.modal_active,
            self.leader_pending,
            self.tree_filter_active,  # Before tree_focused (more specific when filter active)
            self.tree_visual_mode,  # Before multi-select (visual mode takes precedence)
            self.tree_multi_select,  # Before connection/table/etc when multi-select active
            self.tree_on_connection,
            self.tree_on_database,  # For database nodes (multi-database servers)
            self.tree_on_table,
            self.tree_on_folder,
            self.tree_on_object,  # For index/trigger/sequence nodes
            self.tree_focused,
            self.autocomplete_active,  # Before query_insert (more specific)
            self.query_visual,  # Before query_normal (more specific)
            self.query_visual_line,  # Before query_normal (more specific)
            self.query_insert,
            self.query_normal,
            self.query_focused,
            self.results_filter_active,  # Before results_focused (more specific when filter active)
            self.value_view_tree_mode,  # Before value_view_active (more specific in tree mode)
            self.value_view_syntax_mode,  # Before value_view_active (more specific in syntax mode)
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

    def get_active_help_section_id(self, app: InputContext) -> str | None:
        """Return the help section id that matches the active state, if any."""
        state = self.get_active_state(app)
        return STATE_TO_HELP_SECTION.get(state.__class__.__name__)

    def generate_help_sections(self) -> list[HelpSection]:
        """Generate structured help sections.

        Keys are resolved from the active keymap so custom keybindings show up
        here too. Literal fallbacks are kept for sequences that aren't bound to
        a single action (command-mode prefixes, composite vim sequences).
        """
        from sqlit.core.keymap import format_key, get_keymap

        keymap = get_keymap()
        leader_key = resolve_display_key("leader_key") or "<space>"

        def k(action: str, fallback: str) -> str:
            key = keymap.action(action)
            return format_key(key) if key else fallback

        def ks(actions_and_fallbacks: list[tuple[str, str]], sep: str = "/") -> str:
            return sep.join(k(a, f) for a, f in actions_and_fallbacks)

        def lk(action: str, menu: str, fallback: str) -> str:
            key = keymap.leader(action, menu)
            return format_key(key) if key else fallback

        sections: list[HelpSection] = []

        # GLOBAL
        s = HelpSection(id="global", title="GLOBAL")
        s.binding(":q", "Quit")
        s.binding(f"{leader_key}{lk('change_theme', 'leader', 't')}", "Change theme")
        s.binding(f"{leader_key}{lk('toggle_fullscreen', 'leader', 'f')}", "Toggle fullscreen pane")
        s.binding(f"{leader_key}{lk('toggle_explorer', 'leader', 'e')}", "Toggle explorer visibility")
        sections.append(s)

        # NAVIGATION
        s = HelpSection(id="navigation", title="NAVIGATION")
        s.binding(k("focus_explorer", "e"), "Focus Explorer pane")
        s.binding(k("focus_query", "q"), "Focus Query pane")
        s.binding(k("focus_results", "r"), "Focus Results pane")
        s.binding(f"{leader_key}{lk('grow_active_pane', 'leader', '=')}/{lk('shrink_active_pane', 'leader', '-')}", "Grow/shrink focused pane (or drag divider)")
        s.binding(leader_key, "Open command menu")
        s.binding(k("show_help", "?"), "Show this help")
        sections.append(s)

        # EXPLORER
        s = HelpSection(id="explorer", title="EXPLORER")
        s.binding(ks([("tree_cursor_down", "j"), ("tree_cursor_up", "k")]), "Move cursor down/up")
        s.binding("<enter>", "Expand node / Connect")
        s.binding(k("new_connection", "n"), "New connection")
        s.binding(k("select_table", "s"), "SELECT TOP 100 (on table/view)")
        s.binding(k("tree_filter", "/"), "Filter tree")
        s.binding(k("collapse_tree", "z"), "Collapse all nodes")
        s.binding(k("refresh_tree", "f"), "Refresh tree")
        sections.append(s)

        # EXPLORER · ON CONNECTION NODE
        s = HelpSection(id="explorer_connection", title="EXPLORER · ON CONNECTION NODE")
        s.binding(k("edit_connection", "e"), "Edit connection")
        s.binding(k("delete_connection", "d"), "Delete connection")
        s.binding(k("duplicate_connection", "D"), "Duplicate connection")
        s.binding(k("disconnect", "x"), "Disconnect")
        sections.append(s)

        # QUERY EDITOR · NORMAL MODE
        g_key = k("g_leader_key", "g")
        s = HelpSection(id="query_normal", title="QUERY EDITOR · NORMAL MODE")
        s.binding(ks([("enter_insert_mode", "i"), ("prepend_insert_mode", "I")]), "Enter INSERT mode")
        s.binding(ks([("open_line_below", "o"), ("open_line_above", "O")]), "Open line below/above")
        s.binding(k("change_line_end_motion", "C"), "Change to line end")
        s.binding(k("delete_line_end", "D"), "Delete to line end")
        s.binding(f"{k('execute_query', '<enter>')}/{g_key}{lk('execute_query', 'g', 'r')}", "Execute query")
        s.binding(f"{g_key}{lk('execute_query_atomic', 'g', 't')}", "Execute as transaction")
        s.binding(k("show_history", "<backspace>"), "Query history")
        s.binding(k("new_query", "N"), "New query (clear)")
        s.binding(k("undo", "u"), "Undo")
        s.binding(k("redo", "^r"), "Redo")
        sections.append(s)

        # QUERY EDITOR · INSERT MODE
        s = HelpSection(id="query_insert", title="QUERY EDITOR · INSERT MODE")
        s.binding(k("exit_insert_mode", "<esc>"), "Exit to NORMAL mode")
        s.binding(k("execute_query_insert", "^enter"), "Execute (stay in INSERT)")
        s.binding(k("autocomplete_accept", "<tab>"), "Accept autocomplete")
        s.binding(k("select_all", "^a"), "Select all")
        s.binding(k("copy_selection", "^c"), "Copy selection")
        s.binding(k("paste", "^v"), "Paste")
        sections.append(s)

        # QUERY EDITOR · VISUAL MODE
        s = HelpSection(
            id="query_visual",
            title=f"QUERY EDITOR · VISUAL MODE ({k('enter_visual_mode', 'v')})",
        )
        s.binding(f"{k('exit_visual_mode', '<esc>')}/{k('enter_visual_mode', 'v')}", "Exit visual mode")
        s.binding(k("switch_to_visual_line_mode", "V"), "Switch to visual line mode")
        s.binding("h/j/k/l", "Extend selection")
        s.binding("w/b/e/$", "Extend by word/line motions")
        s.binding(k("visual_yank", "y"), "Yank selection")
        s.binding(k("visual_delete", "d"), "Delete selection")
        s.binding(k("visual_change", "c"), "Change selection")
        s.binding(k("visual_execute", "<enter>"), "Execute selection")
        sections.append(s)

        # QUERY EDITOR · VISUAL LINE MODE
        s = HelpSection(
            id="query_visual_line",
            title=f"QUERY EDITOR · VISUAL LINE MODE ({k('enter_visual_line_mode', 'V')})",
        )
        s.binding(f"{k('exit_visual_line_mode', '<esc>')}/{k('enter_visual_line_mode', 'V')}", "Exit visual line mode")
        s.binding(k("switch_to_visual_mode", "v"), "Switch to visual mode")
        s.binding("j/k", "Extend selection down/up")
        s.binding("gg/G", "Extend to first/last line")
        s.binding(k("visual_line_yank", "y"), "Yank selected lines")
        s.binding(k("visual_line_delete", "d"), "Delete selected lines")
        s.binding(k("visual_line_change", "c"), "Change selected lines")
        s.binding(k("visual_line_execute", "<enter>"), "Execute selected lines")
        sections.append(s)

        # VIM OPERATORS + MOTIONS + TEXT OBJECTS
        yank_op = k("yank_leader_key", "y")
        del_op = k("delete_leader_key", "d")
        chg_op = k("change_leader_key", "c")
        s = HelpSection(id="vim_operators", title="VIM OPERATORS (NORMAL MODE)")
        s.binding(f"{yank_op}{{motion}}", "Copy")
        s.binding(f"{del_op}{{motion}}", "Delete")
        s.binding(f"{chg_op}{{motion}}", "Change (delete + INSERT)")
        s.binding(k("paste", "p"), "Paste after cursor")
        sections.append(s)

        s = HelpSection(id="vim_motions", title="VIM MOTIONS")
        s.binding(ks([("cursor_left", "h"), ("cursor_down", "j"), ("cursor_up", "k"), ("cursor_right", "l")]), "Cursor left/down/up/right")
        s.binding(ks([("cursor_word_forward", "w"), ("cursor_WORD_forward", "W")]), "Word forward")
        s.binding(ks([("cursor_word_back", "b"), ("cursor_WORD_back", "B")]), "Word backward")
        s.binding(f"{k('cursor_line_start', '0')}/^/{k('cursor_line_end', '$')}", "Line start/first char/end")
        s.binding(f"{g_key}{lk('first_line', 'g', 'g')}/{k('cursor_last_line', 'G')}", "File start/end")
        s.binding(f"{k('cursor_find_char', 'f')}{{c}}/{k('cursor_find_char_back', 'F')}{{c}}", "Find char forward/back")
        s.binding(f"{k('cursor_till_char', 't')}{{c}}/{k('cursor_till_char_back', 'T')}{{c}}", "Till char forward/back")
        s.binding(k("cursor_matching_bracket", "%"), "Matching bracket")
        sections.append(s)

        inner = lk("inner", "yank", "i")
        around = lk("around", "yank", "a")
        s = HelpSection(
            id="text_objects",
            title=f"TEXT OBJECTS (with {inner}=inner, {around}=around)",
        )
        s.binding(f"{inner}w/{around}w", "Word")
        s.binding(f'{inner}"/{around}"', "Double quotes")
        s.binding(f"{inner}'/{around}'", "Single quotes")
        s.binding(f"{inner})/{around})", "Parentheses")
        s.binding(f"{inner}}}/{around}}}", "Braces")
        s.binding(f"{inner}]/{around}]", "Brackets")
        sections.append(s)

        # RESULTS
        s = HelpSection(id="results", title="RESULTS")
        s.binding(ks([("results_cursor_left", "h"), ("results_cursor_down", "j"), ("results_cursor_up", "k"), ("results_cursor_right", "l")]), "Navigate cells")
        s.binding(k("view_cell", "v"), "Preview cell (inline)")
        s.binding(k("view_cell_full", "V"), "View full cell value")
        s.binding(k("edit_cell", "u"), "Generate UPDATE statement")
        s.binding(k("delete_row", "d"), "Generate DELETE statement")
        s.binding(k("results_filter", "/"), "Filter rows")
        s.binding(k("clear_results", "x"), "Clear results")
        s.binding(k("next_result_section", "<tab>"), "Next result set")
        s.binding(k("prev_result_section", "<s-tab>"), "Previous result set")
        s.binding(k("toggle_result_section", "z"), "Collapse/expand result")
        results_yank = k("results_yank_leader_key", "y")
        s.subsection(f"Copy Menu ({results_yank}):")
        s.binding(f"{results_yank}{lk('cell', 'ry', 'c')}", "Copy cell")
        s.binding(f"{results_yank}{lk('row', 'ry', 'y')}", "Copy row")
        s.binding(f"{results_yank}{lk('all', 'ry', 'a')}", "Copy all")
        s.binding(f"{results_yank}{lk('export', 'ry', 'e')}", "Export menu...")
        sections.append(s)

        # FILTERING
        s = HelpSection(id="filtering", title="FILTERING")
        s.binding(k("results_filter", "/"), "Open filter (Explorer/Results)")
        s.binding(k("results_filter_accept", "<enter>"), "Apply filter")
        s.binding(k("results_filter_close", "<esc>"), "Close filter")
        s.binding("~prefix", "Fuzzy match mode")
        sections.append(s)

        # COMMAND MENU
        s = HelpSection(id="command_menu", title=f"COMMAND MENU ({leader_key})")
        leader_cmds = get_leader_commands("leader")
        by_cat: dict[str, list[tuple[str, str]]] = {}
        for cmd in leader_cmds:
            by_cat.setdefault(cmd.category, []).append((cmd.key, cmd.label))
        for cat in ["View", "Connection", "Actions"]:
            if cat in by_cat:
                s.subsection(f"{cat}:")
                for key, label in by_cat[cat]:
                    s.binding(f"{leader_key}{format_key(key)}", label)
        sections.append(s)

        # CONNECTION PICKER
        s = HelpSection(id="connection_picker", title="CONNECTION PICKER")
        s.binding("/", "Search connections")
        s.binding("j/k", "Navigate list")
        s.binding("<enter>", "Connect to selected")
        s.binding(k("new_connection", "n"), "New connection")
        s.binding(k("edit_connection", "e"), "Edit connection")
        s.binding(k("delete_connection", "d"), "Delete connection")
        s.binding(k("duplicate_connection", "D"), "Duplicate connection")
        s.binding("<esc>", "Close picker")
        sections.append(s)

        # COMMAND MODE
        s = HelpSection(id="command_mode", title="COMMAND MODE")
        s.binding(":", "Enter command mode")
        s.binding(":commands", "Show command list")
        sections.append(s)

        # SETTINGS
        s = HelpSection(id="settings", title="SETTINGS")
        s.binding(":alert off|delete|write", "Confirm risky queries")
        s.binding(":set ln on|off|relative", "Line numbers")
        sections.append(s)

        return sections
