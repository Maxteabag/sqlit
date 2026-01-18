"""Query editor normal mode state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key
from sqlit.core.vim import VimMode


class QueryNormalModeState(State):
    """Query editor in NORMAL mode."""

    help_category = "Query Editor (Normal)"

    def _setup_actions(self) -> None:
        self.allows("enter_insert_mode", label="Insert Mode", help="Enter INSERT mode")
        self.allows("execute_query", label="Execute", help="Execute query")
        self.allows("execute_single_statement", label="Run Statement", help="Execute statement at cursor")
        self.allows("delete_leader_key", label="Delete", help="Delete (menu)")
        self.allows("yank_leader_key", label="Copy", help="Copy (menu)")
        self.allows("change_leader_key", label="Change", help="Change (menu)")
        self.allows("g_leader_key", label="Go", help="Go motions (menu)")
        self.allows("new_query", label="New", help="New query (clear all)")
        self.allows("show_history", label="History", help="Query history")
        # Vim cursor movement
        self.allows("cursor_left", help="Move cursor left")
        self.allows("cursor_right", help="Move cursor right")
        self.allows("cursor_up", help="Move cursor up")
        self.allows("cursor_down", help="Move cursor down")
        self.allows("cursor_word_forward", help="Move to next word")
        self.allows("cursor_WORD_forward", help="Move to next WORD")
        self.allows("cursor_word_back", help="Move to previous word")
        self.allows("cursor_WORD_back", help="Move to previous WORD")
        self.allows("cursor_line_start", help="Move to line start")
        self.allows("cursor_line_end", help="Move to line end")
        self.allows("cursor_last_line", help="Move to last line")
        self.allows("cursor_matching_bracket", help="Move to matching bracket")
        self.allows("cursor_find_char", help="Find char forward")
        self.allows("cursor_find_char_back", help="Find char backward")
        self.allows("cursor_till_char", help="Move till char forward")
        self.allows("cursor_till_char_back", help="Move till char backward")
        self.allows("append_insert_mode", help="Append after cursor")
        self.allows("append_line_end", help="Append at line end")
        # Vim open line
        self.allows("open_line_below", help="Open line below")
        self.allows("open_line_above", help="Open line above")
        # Clipboard actions
        self.allows("select_all", help="Select all text")
        self.allows("copy_selection", help="Copy selection")
        self.allows("paste", help="Paste")
        # Selection actions
        self.allows("select_left", help="Select left")
        self.allows("select_right", help="Select right")
        self.allows("select_up", help="Select up")
        self.allows("select_down", help="Select down")
        self.allows("select_word_left", help="Select word left")
        self.allows("select_word_right", help="Select word right")
        self.allows("select_line_start", help="Select to line start")
        self.allows("select_line_end", help="Select to line end")
        self.allows("select_to_start", help="Select to start")
        self.allows("select_to_end", help="Select to end")
        # Undo/redo
        self.allows("undo", help="Undo")
        self.allows("redo", help="Redo")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("enter_insert_mode") or "i",
                label="Insert Mode",
                action="enter_insert_mode",
            )
        )
        seen.add("enter_insert_mode")
        left.append(
            DisplayBinding(
                key=resolve_display_key("execute_query") or "enter",
                label="Execute",
                action="execute_query",
            )
        )
        seen.add("execute_query")

        left.append(
            DisplayBinding(
                key=resolve_display_key("yank_leader_key") or "y",
                label="Copy",
                action="yank_leader_key",
            )
        )
        seen.add("yank_leader_key")

        left.append(
            DisplayBinding(
                key=resolve_display_key("delete_leader_key") or "d",
                label="Delete",
                action="delete_leader_key",
            )
        )
        seen.add("delete_leader_key")

        # Keep change and go actions available but not shown in footer
        seen.add("change_leader_key")
        seen.add("g_leader_key")

        left.append(
            DisplayBinding(
                key=resolve_display_key("show_history") or "H",
                label="History",
                action="show_history",
            )
        )
        seen.add("show_history")
        left.append(
            DisplayBinding(
                key=resolve_display_key("new_query") or "N",
                label="New",
                action="new_query",
            )
        )
        seen.add("new_query")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "query" and app.vim_mode == VimMode.NORMAL
