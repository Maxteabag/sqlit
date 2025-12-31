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

    def refresh_tree(self) -> None:
        ...

    def populate_connected_tree(self) -> None:
        ...

    def _db_type_badge(self, db_type: str) -> str:
        ...

    def _format_connection_label(self, conn: Any, status: str, spinner: str | None = None) -> str:
        ...

    def _connect_spinner_frame(self) -> str:
        ...

    def _get_node_kind(self, node: Any) -> str:
        ...

    def _add_database_object_nodes(self, node: Any, database: str | None) -> None:
        ...

    def _ensure_database_connection(self, target_db: str) -> bool:
        ...

    def _fallback_reconnect_and_retry(self, node: Any, action: Any) -> None:
        ...

    def _reconnect_to_database(self, db_name: str) -> None:
        ...

    def _update_database_labels(self) -> None:
        ...

    def set_default_database(self, db_name: str | None) -> None:
        ...

    def _show_index_info(self, data: Any) -> None:
        ...

    def _show_trigger_info(self, data: Any) -> None:
        ...

    def _show_sequence_info(self, data: Any) -> None:
        ...

    def _display_object_info(self, header: str, body: dict[str, Any]) -> None:
        ...

    def _restore_subtree_expansion(self, node: Any) -> None:
        ...

    def _get_node_path(self, node: Any) -> str:
        ...

    def _save_expanded_state(self) -> None:
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

    def _on_columns_loaded(
        self, node: Any, db_name: str | None, schema_name: str, obj_name: str, columns: list[Any]
    ) -> None:
        ...

    def _on_tree_load_error(self, node: Any, error_message: str) -> None:
        ...

    def _on_folder_loaded(self, node: Any, db_name: str | None, folder_type: str, items: list[Any]) -> None:
        ...

    def _add_schema_grouped_items(
        self, node: Any, db_name: str | None, folder_type: str, items: list[Any], default_schema: str
    ) -> None:
        ...


class ExplorerProtocol(ExplorerStateProtocol, ExplorerActionsProtocol, Protocol):
    """Composite protocol for explorer-related mixins."""

    pass
