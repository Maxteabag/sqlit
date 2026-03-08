"""UI-agnostic input context used for key state evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from sqlit.core.vim import VimMode


@dataclass
class InputContext:
    """Snapshot of UI input state for key routing/state evaluation."""

    focus: str  # "explorer" | "query" | "results" | "none"
    vim_mode: VimMode
    leader_pending: bool
    leader_menu: str
    tree_filter_active: bool
    tree_multi_select_active: bool
    tree_visual_mode_active: bool
    autocomplete_visible: bool
    results_filter_active: bool
    value_view_active: bool
    value_view_tree_mode: bool
    value_view_is_json: bool
    query_executing: bool
    modal_open: bool
    has_connection: bool
    current_connection_name: str | None
    tree_node_kind: str | None
    tree_node_connection_name: str | None
    tree_node_connection_selected: bool
    last_result_is_error: bool
    has_results: bool
    stacked_result_count: int = 0
    count_buffer: str = ""
