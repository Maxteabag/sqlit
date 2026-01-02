"""Protocols for explorer/tree mixins."""

from __future__ import annotations

from typing import Any, Protocol


class ExplorerStateProtocol(Protocol):
    _expanded_paths: set[str]
    _loading_nodes: set[str]
    _schema_service: Any | None
    _schema_service_session: Any | None
    _tree_filter_visible: bool
    _tree_filter_text: str
    _tree_filter_query: str
    _tree_filter_fuzzy: bool
    _tree_filter_typing: bool
    _tree_filter_matches: list[Any]
    _tree_filter_match_index: int
    _tree_original_labels: dict[int, str]


class ExplorerActionsProtocol(Protocol):
    def _get_schema_service(self) -> Any:
        ...

    def _get_object_cache(self) -> dict[str, dict[str, Any]]:
        ...

    def _db_type_badge(self, db_type: str) -> str:
        ...

    def _format_connection_label(self, conn: Any, status: str, spinner: str | None = None) -> str:
        ...

    def _connect_spinner_frame(self) -> str:
        ...

    def _get_node_kind(self, node: Any) -> str:
        ...

    def _activate_tree_node(self, node: Any) -> None:
        ...

    def action_tree_filter(self) -> None:
        ...

    def action_tree_filter_close(self) -> None:
        ...

    def action_tree_filter_accept(self) -> None:
        ...

    def action_tree_filter_next(self) -> None:
        ...

    def action_tree_filter_prev(self) -> None:
        ...

    def _update_tree_filter(self) -> None:
        ...

    def _jump_to_current_match(self) -> None:
        ...

    def _expand_ancestors(self, node: Any) -> None:
        ...

    def _restore_tree_labels(self) -> None:
        ...

    def _show_all_tree_nodes(self) -> None:
        ...

    def _count_all_nodes(self) -> int:
        ...

    def _find_matching_nodes(self, node: Any, matches: list[Any]) -> bool:
        ...

    def _get_node_label_text(self, node: Any) -> str:
        ...

    def _apply_filter_to_tree(self) -> None:
        ...

    def _set_node_visibility(self, node: Any, match_ids: set[Any], ancestor_ids: set[Any], visible: bool) -> None:
        ...

    def _rebuild_label_with_highlight(self, node: Any, highlighted_text: str) -> str:
        ...

    def _load_columns_async(self, node: Any, data: Any) -> None:
        ...

    def _load_folder_async(self, node: Any, data: Any) -> None:
        ...

    def refresh_tree(self) -> None:
        ...

    def _get_node_path_part(self, node: Any) -> str:
        ...


class ExplorerProtocol(ExplorerStateProtocol, ExplorerActionsProtocol, Protocol):
    """Composite protocol for explorer-related mixins."""

    pass
