"""Protocols for query execution mixins."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.timer import Timer
    from textual.worker import Worker
    from sqlit.domains.query.app.query_service import QueryService
    from sqlit.shared.ui.spinner import Spinner
    from sqlit.domains.query.editing.deletion import EditResult


class QueryStateProtocol(Protocol):
    _query_worker: Worker[Any] | None
    _query_executing: bool
    _query_start_time: float
    _spinner_index: int
    _spinner_timer: Timer | None
    _cancellable_query: Any | None
    _query_spinner: Spinner | None
    _query_cursor_cache: dict[str, tuple[int, int]] | None
    _undo_history: Any | None


class QueryActionsProtocol(Protocol):
    _query_service: QueryService | None
    _history_store: Any | None
    _query_service_db_type: str | None

    def action_execute_query(self) -> None:
        ...

    def _get_history_store(self) -> Any:
        ...

    def _get_query_service(self, provider: Any) -> QueryService:
        ...

    def _execute_query_common(self, keep_insert_mode: bool) -> None:
        ...

    def _start_query_spinner(self) -> None:
        ...

    def _run_query_async(self, query: str, keep_insert_mode: bool) -> Awaitable[None]:
        ...

    def _animate_spinner(self) -> None:
        ...

    def _display_query_error(self, error_message: str) -> None:
        ...

    def _stop_query_spinner(self) -> None:
        ...

    def _display_query_results(
        self, columns: list[str], rows: list[tuple[Any, ...]], row_count: int, truncated: bool, elapsed_ms: float
    ) -> None:
        ...

    def _display_non_query_result(self, affected: int, elapsed_ms: float) -> None:
        ...

    def _restore_insert_mode(self) -> None:
        ...

    def _handle_history_result(self, result: Any) -> None:
        ...

    def _delete_history_entry(self, timestamp: str) -> None:
        ...

    def action_show_history(self) -> None:
        ...

    def action_copy_query(self) -> None:
        ...

    def action_copy_cell(self) -> None:
        ...

    def _toggle_star(self, query: str) -> None:
        ...

    def _clear_query_target_database(self) -> None:
        ...

    def _clear_leader_pending(self) -> None:
        ...

    def _delete_with_motion(self, motion_key: str, char: str | None = None) -> None:
        ...

    def _delete_with_text_object(self, obj_char: str, around: bool) -> None:
        ...

    def _show_char_pending_menu(self, motion: str) -> None:
        ...

    def _show_text_object_menu(self, mode: str) -> None:
        ...

    def _get_clipboard_text(self) -> str:
        ...

    def _get_undo_history(self) -> Any:
        ...

    def _push_undo_state(self) -> None:
        ...

    def _apply_edit_result(self, result: "EditResult") -> None:
        ...


class QueryProtocol(QueryStateProtocol, QueryActionsProtocol, Protocol):
    """Composite protocol for query-related mixins."""

    pass
