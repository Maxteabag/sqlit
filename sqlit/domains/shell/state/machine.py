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
from sqlit.domains.shell.state.leader_pending import LeaderPendingState
from sqlit.domains.shell.state.main_screen import MainScreenState
from sqlit.domains.shell.state.modal_active import ModalActiveState
from sqlit.domains.shell.state.root import RootState


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

    def generate_help_text(self) -> str:
        """Generate structured help text with organized sections.

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

        def section(title: str) -> str:
            divider = "-" * 62
            return f"[bold $primary]{title}[/]\n[dim]{divider}[/]"

        def subsection(title: str) -> str:
            return f"  [bold $text-muted]{title}[/]"

        def binding(key: str, desc: str, indent: int = 4) -> str:
            pad = " " * indent
            return f"{pad}[bold $warning]{key:<14}[/] [dim]-[/] {desc}"

        lines: list[str] = []

        # ═══════════════════════════════════════════════════════════════════
        # GLOBAL
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("GLOBAL"))
        lines.append(binding(":q", "Quit"))
        lines.append(binding(f"{leader_key}{lk('change_theme', 'leader', 't')}", "Change theme"))
        lines.append(binding(f"{leader_key}{lk('toggle_fullscreen', 'leader', 'f')}", "Toggle fullscreen pane"))
        lines.append(binding(f"{leader_key}{lk('toggle_explorer', 'leader', 'e')}", "Toggle explorer visibility"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # NAVIGATION
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("NAVIGATION"))
        lines.append(binding(k("focus_explorer", "e"), "Focus Explorer pane"))
        lines.append(binding(k("focus_query", "q"), "Focus Query pane"))
        lines.append(binding(k("focus_results", "r"), "Focus Results pane"))
        lines.append(binding(leader_key, "Open command menu"))
        lines.append(binding(k("show_help", "?"), "Show this help"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # EXPLORER
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("EXPLORER"))
        lines.append(binding(ks([("tree_cursor_down", "j"), ("tree_cursor_up", "k")]), "Move cursor down/up"))
        lines.append(binding("<enter>", "Expand node / Connect"))
        lines.append(binding(k("select_table", "s"), "SELECT TOP 100 (on table/view)"))
        lines.append(binding(k("tree_filter", "/"), "Filter tree"))
        lines.append(binding(k("collapse_tree", "z"), "Collapse all nodes"))
        lines.append(binding(k("refresh_tree", "f"), "Refresh tree"))
        lines.append("")
        lines.append(subsection("On Connection Node:"))
        lines.append(binding(k("new_connection", "n"), "New connection"))
        lines.append(binding(k("edit_connection", "e"), "Edit connection"))
        lines.append(binding(k("delete_connection", "d"), "Delete connection"))
        lines.append(binding(k("duplicate_connection", "D"), "Duplicate connection"))
        lines.append(binding(k("disconnect", "x"), "Disconnect"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # QUERY EDITOR
        # ═══════════════════════════════════════════════════════════════════
        g_key = k("g_leader_key", "g")
        lines.append(section("QUERY EDITOR"))
        lines.append(subsection("Normal Mode:"))
        lines.append(binding(ks([("enter_insert_mode", "i"), ("prepend_insert_mode", "I")]), "Enter INSERT mode"))
        lines.append(binding(ks([("open_line_below", "o"), ("open_line_above", "O")]), "Open line below/above"))
        lines.append(binding(k("change_line_end_motion", "C"), "Change to line end"))
        lines.append(binding(k("delete_line_end", "D"), "Delete to line end"))
        lines.append(binding(f"{k('execute_query', '<enter>')}/{g_key}{lk('execute_query', 'g', 'r')}", "Execute query"))
        lines.append(binding(f"{g_key}{lk('execute_query_atomic', 'g', 't')}", "Execute as transaction"))
        lines.append(binding(k("show_history", "<backspace>"), "Query history"))
        lines.append(binding(k("new_query", "N"), "New query (clear)"))
        lines.append(binding(k("undo", "u"), "Undo"))
        lines.append(binding(k("redo", "^r"), "Redo"))
        lines.append("")
        lines.append(subsection("Insert Mode:"))
        lines.append(binding(k("exit_insert_mode", "<esc>"), "Exit to NORMAL mode"))
        lines.append(binding(k("execute_query_insert", "^enter"), "Execute (stay in INSERT)"))
        lines.append(binding(k("autocomplete_accept", "<tab>"), "Accept autocomplete"))
        lines.append(binding(k("select_all", "^a"), "Select all"))
        lines.append(binding(k("copy_selection", "^c"), "Copy selection"))
        lines.append(binding(k("paste", "^v"), "Paste"))
        lines.append("")
        lines.append(subsection(f"Visual Mode ({k('enter_visual_mode', 'v')}):"))
        lines.append(binding(f"{k('exit_visual_mode', '<esc>')}/{k('enter_visual_mode', 'v')}", "Exit visual mode"))
        lines.append(binding(k("switch_to_visual_line_mode", "V"), "Switch to visual line mode"))
        lines.append(binding("h/j/k/l", "Extend selection"))
        lines.append(binding("w/b/e/$", "Extend by word/line motions"))
        lines.append(binding(k("visual_yank", "y"), "Yank selection"))
        lines.append(binding(k("visual_delete", "d"), "Delete selection"))
        lines.append(binding(k("visual_change", "c"), "Change selection"))
        lines.append(binding(k("visual_execute", "<enter>"), "Execute selection"))
        lines.append("")
        lines.append(subsection(f"Visual Line Mode ({k('enter_visual_line_mode', 'V')}):"))
        lines.append(binding(f"{k('exit_visual_line_mode', '<esc>')}/{k('enter_visual_line_mode', 'V')}", "Exit visual line mode"))
        lines.append(binding(k("switch_to_visual_mode", "v"), "Switch to visual mode"))
        lines.append(binding("j/k", "Extend selection down/up"))
        lines.append(binding("gg/G", "Extend to first/last line"))
        lines.append(binding(k("visual_line_yank", "y"), "Yank selected lines"))
        lines.append(binding(k("visual_line_delete", "d"), "Delete selected lines"))
        lines.append(binding(k("visual_line_change", "c"), "Change selected lines"))
        lines.append(binding(k("visual_line_execute", "<enter>"), "Execute selected lines"))
        lines.append("")
        # Operator + motion sequences: resolve the operator key, keep "{motion}" literal.
        yank_op = k("yank_leader_key", "y")
        del_op = k("delete_leader_key", "d")
        chg_op = k("change_leader_key", "c")
        lines.append(subsection("Vim Operators (Normal Mode):"))
        lines.append(binding(f"{yank_op}{{motion}}", "Copy"))
        lines.append(binding(f"{del_op}{{motion}}", "Delete"))
        lines.append(binding(f"{chg_op}{{motion}}", "Change (delete + INSERT)"))
        lines.append(binding(k("paste", "p"), "Paste after cursor"))
        lines.append("")
        lines.append(subsection("Vim Motions:"))
        lines.append(binding(ks([("cursor_left", "h"), ("cursor_down", "j"), ("cursor_up", "k"), ("cursor_right", "l")]), "Cursor left/down/up/right"))
        lines.append(binding(ks([("cursor_word_forward", "w"), ("cursor_WORD_forward", "W")]), "Word forward"))
        lines.append(binding(ks([("cursor_word_back", "b"), ("cursor_WORD_back", "B")]), "Word backward"))
        # `^` (first non-blank) is not a separate keymap action — kept as a literal.
        lines.append(binding(f"{k('cursor_line_start', '0')}/^/{k('cursor_line_end', '$')}", "Line start/first char/end"))
        lines.append(binding(f"{g_key}{lk('first_line', 'g', 'g')}/{k('cursor_last_line', 'G')}", "File start/end"))
        lines.append(binding(f"{k('cursor_find_char', 'f')}{{c}}/{k('cursor_find_char_back', 'F')}{{c}}", "Find char forward/back"))
        lines.append(binding(f"{k('cursor_till_char', 't')}{{c}}/{k('cursor_till_char_back', 'T')}{{c}}", "Till char forward/back"))
        lines.append(binding(k("cursor_matching_bracket", "%"), "Matching bracket"))
        lines.append("")
        # Text objects: inner/around are leader_commands inside operator menus (yank/delete/change).
        # Resolve from the yank menu — by convention these stay aligned across menus.
        inner = lk("inner", "yank", "i")
        around = lk("around", "yank", "a")
        lines.append(subsection(f"Text Objects (with {inner}=inner, {around}=around):"))
        lines.append(binding(f"{inner}w/{around}w", "Word"))
        lines.append(binding(f'{inner}"/{around}"', "Double quotes"))
        lines.append(binding(f"{inner}'/{around}'", "Single quotes"))
        lines.append(binding(f"{inner})/{around})", "Parentheses"))
        lines.append(binding(f"{inner}}}/{around}}}", "Braces"))
        lines.append(binding(f"{inner}]/{around}]", "Brackets"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # RESULTS
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("RESULTS"))
        lines.append(binding(ks([("results_cursor_left", "h"), ("results_cursor_down", "j"), ("results_cursor_up", "k"), ("results_cursor_right", "l")]), "Navigate cells"))
        lines.append(binding(k("view_cell", "v"), "Preview cell (inline)"))
        lines.append(binding(k("view_cell_full", "V"), "View full cell value"))
        lines.append(binding(k("edit_cell", "u"), "Generate UPDATE statement"))
        lines.append(binding(k("delete_row", "d"), "Generate DELETE statement"))
        lines.append(binding(k("results_filter", "/"), "Filter rows"))
        lines.append(binding(k("clear_results", "x"), "Clear results"))
        lines.append(binding(k("next_result_section", "<tab>"), "Next result set"))
        lines.append(binding(k("prev_result_section", "<s-tab>"), "Previous result set"))
        lines.append(binding(k("toggle_result_section", "z"), "Collapse/expand result"))
        lines.append("")
        results_yank = k("results_yank_leader_key", "y")
        lines.append(subsection(f"Copy Menu ({results_yank}):"))
        lines.append(binding(f"{results_yank}{lk('cell', 'ry', 'c')}", "Copy cell"))
        lines.append(binding(f"{results_yank}{lk('row', 'ry', 'y')}", "Copy row"))
        lines.append(binding(f"{results_yank}{lk('all', 'ry', 'a')}", "Copy all"))
        lines.append(binding(f"{results_yank}{lk('export', 'ry', 'e')}", "Export menu..."))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # FILTERING
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("FILTERING"))
        lines.append(binding(k("results_filter", "/"), "Open filter (Explorer/Results)"))
        lines.append(binding(k("results_filter_accept", "<enter>"), "Apply filter"))
        lines.append(binding(k("results_filter_close", "<esc>"), "Close filter"))
        lines.append(binding("~prefix", "Fuzzy match mode"))
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
                    lines.append(binding(f"{leader_key}{format_key(key)}", label))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # CONNECTION PICKER
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("CONNECTION PICKER"))
        lines.append(binding("/", "Search connections"))
        lines.append(binding("j/k", "Navigate list"))
        lines.append(binding("<enter>", "Connect to selected"))
        lines.append(binding(k("new_connection", "n"), "New connection"))
        lines.append(binding(k("edit_connection", "e"), "Edit connection"))
        lines.append(binding(k("delete_connection", "d"), "Delete connection"))
        lines.append(binding(k("duplicate_connection", "D"), "Duplicate connection"))
        lines.append(binding("<esc>", "Close picker"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # COMMAND MODE
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("COMMAND MODE"))
        lines.append(binding(":", "Enter command mode"))
        lines.append(binding(":commands", "Show command list"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════════════
        # SETTINGS
        # ═══════════════════════════════════════════════════════════════════
        lines.append(section("SETTINGS"))
        lines.append(binding(":alert off|delete|write", "Confirm risky queries"))
        lines.append(binding(":set ln on|off|relative", "Line numbers"))

        return "\n".join(lines)
