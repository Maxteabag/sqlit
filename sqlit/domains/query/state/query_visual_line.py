"""Query editor visual line mode state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key
from sqlit.core.vim import VimMode


class QueryVisualLineModeState(State):
    """Query editor in VISUAL LINE mode (V)."""

    help_category = "Query Editor (Visual Line)"

    def _setup_actions(self) -> None:
        self.allows(
            "exit_visual_line_mode",
            label="Exit Visual",
            help="Exit visual line mode",
        )
        # Block entering visual line mode when already in it
        self.forbids("enter_visual_line_mode")
        # Switch to charwise visual
        self.allows("switch_to_visual_mode", help="Switch to visual mode")
        # Block normal mode operators (visual mode uses direct operators)
        self.forbids("enter_insert_mode")
        self.forbids("delete_leader_key")
        self.forbids("yank_leader_key")
        self.forbids("change_leader_key")
        # Visual line operators
        self.allows(
            "visual_line_yank",
            label="Yank",
            help="Yank selected lines",
        )
        self.allows(
            "visual_line_delete",
            label="Delete",
            help="Delete selected lines",
        )
        self.allows(
            "visual_line_change",
            label="Change",
            help="Change selected lines",
        )
        # Execute selected lines
        self.allows(
            "visual_line_execute",
            label="Execute",
            help="Execute selected lines",
        )
        # Vertical cursor movement
        self.allows("cursor_up", help="Extend selection up")
        self.allows("cursor_down", help="Extend selection down")
        self.allows("cursor_last_line", help="Extend selection to last line")
        self.allows("g_leader_key", help="Go motions (menu)")
        self.allows("g_first_line", help="Extend selection to first line")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("exit_visual_line_mode") or "<esc>",
                label="Exit Visual",
                action="exit_visual_line_mode",
            )
        )
        seen.add("exit_visual_line_mode")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_line_yank") or "y",
                label="Yank",
                action="visual_line_yank",
            )
        )
        seen.add("visual_line_yank")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_line_delete") or "d",
                label="Delete",
                action="visual_line_delete",
            )
        )
        seen.add("visual_line_delete")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_line_change") or "c",
                label="Change",
                action="visual_line_change",
            )
        )
        seen.add("visual_line_change")
        left.append(
            DisplayBinding(
                key=resolve_display_key("visual_line_execute") or "<enter>",
                label="Execute",
                action="visual_line_execute",
            )
        )
        seen.add("visual_line_execute")

        if self.parent:
            parent_left, _ = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "query" and app.vim_mode == VimMode.VISUAL_LINE
