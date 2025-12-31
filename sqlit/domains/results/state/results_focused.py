"""Results table focused state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class ResultsFocusedState(State):
    """Results table has focus."""

    help_category = "Results"

    def _setup_actions(self) -> None:
        self.allows("view_cell", key="v", label="View cell", help="Preview cell (tooltip)")
        self.allows("view_cell_full", key="V", label="View full", help="View full cell value")
        self.allows("edit_cell", key="u", label="Update cell", help="Update cell (generate UPDATE)")
        self.allows("results_yank_leader_key", key="y", label="Copy", help="Copy menu (cell/row/all)")
        self.allows("clear_results", key="x", label="Clear", help="Clear results")
        self.allows("results_filter", key="slash", label="Filter", help="Filter rows")
        self.allows("results_cursor_left")  # vim h
        self.allows("results_cursor_down")  # vim j
        self.allows("results_cursor_up")  # vim k
        self.allows("results_cursor_right")  # vim l

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        is_error = app.last_result_is_error

        if is_error:
            left.append(
                DisplayBinding(
                    key=resolve_display_key("view_cell") or "v",
                    label="View error",
                    action="view_cell",
                )
            )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("results_yank_leader_key") or "y",
                    label="Copy",
                    action="results_yank_leader_key",
                )
            )
        else:
            left.append(
                DisplayBinding(
                    key=resolve_display_key("view_cell") or "v",
                    label="Preview",
                    action="view_cell",
                )
            )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("view_cell_full") or "V",
                    label="View",
                    action="view_cell_full",
                )
            )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("edit_cell") or "u",
                    label="Update",
                    action="edit_cell",
                )
            )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("results_yank_leader_key") or "y",
                    label="Copy",
                    action="results_yank_leader_key",
                )
            )
        left.append(
            DisplayBinding(
                key=resolve_display_key("clear_results") or "x",
                label="Clear",
                action="clear_results",
            )
        )
        left.append(
            DisplayBinding(
                key=resolve_display_key("results_filter") or "/",
                label="Filter",
                action="results_filter",
            )
        )

        seen.update(["view_cell", "view_cell_full", "results_yank_leader_key", "clear_results", "results_filter"])

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "results"
