"""Query editor visual (charwise) mode state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key
from sqlit.core.vim import VimMode


class QueryVisualModeState(State):
    """Query editor in VISUAL mode (v)."""

    help_category = "Query Editor (Visual)"

    def _setup_actions(self) -> None:
        self.allows(
            "exit_visual_mode",
            label="Exit Visual",
            help="Exit visual mode",
        )
        self.forbids("enter_visual_mode")
        self.forbids("enter_insert_mode")
        self.forbids("delete_leader_key")
        self.forbids("yank_leader_key")
        self.forbids("change_leader_key")
        # Switch to visual line
        self.allows("switch_to_visual_line_mode", help="Switch to visual line mode")
        # Visual operators
        self.allows("visual_yank", label="Yank", help="Yank selection")
        self.allows("visual_delete", label="Delete", help="Delete selection")
        self.allows("visual_change", label="Change", help="Change selection")
        self.allows("visual_execute", label="Execute", help="Execute selection")
        # All cursor motions
        self.allows("cursor_left", help="Move cursor left")
        self.allows("cursor_right", help="Move cursor right")
        self.allows("cursor_up", help="Move cursor up")
        self.allows("cursor_down", help="Move cursor down")
        self.allows("cursor_word_forward", help="Move to next word")
        self.allows("cursor_WORD_forward", help="Move to next WORD")
        self.allows("cursor_word_back", help="Move to previous word")
        self.allows("cursor_WORD_back", help="Move to previous WORD")
        self.allows("cursor_first_non_blank", help="Move to first non-blank")
        self.allows("cursor_line_start", help="Move to line start")
        self.allows("cursor_line_end", help="Move to line end")
        self.allows("cursor_last_line", help="Move to last line")
        self.allows("cursor_matching_bracket", help="Move to matching bracket")
        self.allows("cursor_find_char", help="Find char forward")
        self.allows("cursor_find_char_back", help="Find char backward")
        self.allows("cursor_till_char", help="Move till char forward")
        self.allows("cursor_till_char_back", help="Move till char backward")
        self.allows("g_leader_key", help="Go motions (menu)")
        self.allows("g_first_line", help="Go to first line")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("exit_visual_mode") or "<esc>",
                label="Exit Visual",
                action="exit_visual_mode",
            )
        )
        seen.add("exit_visual_mode")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_yank") or "y",
                label="Yank",
                action="visual_yank",
            )
        )
        seen.add("visual_yank")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_delete") or "d",
                label="Delete",
                action="visual_delete",
            )
        )
        seen.add("visual_delete")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_change") or "c",
                label="Change",
                action="visual_change",
            )
        )
        seen.add("visual_change")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_execute") or "<enter>",
                label="Execute",
                action="visual_execute",
            )
        )
        seen.add("visual_execute")

        if self.parent:
            parent_left, _ = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "query" and app.vim_mode == VimMode.VISUAL
