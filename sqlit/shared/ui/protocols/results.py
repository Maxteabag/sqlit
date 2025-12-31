"""Protocols for results handling mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.timer import Timer

    from sqlit.shared.ui.widgets import SqlitDataTable


class ResultsStateProtocol(Protocol):
    _last_result_columns: list[str]
    _last_result_rows: list[tuple[Any, ...]]
    _last_result_row_count: int
    _internal_clipboard: str
    _last_query_table: dict[str, Any] | None
    _results_table_counter: int
    _results_filter_visible: bool
    _results_filter_text: str
    _results_filter_matches: list[int]
    _results_filter_match_index: int
    _results_filter_original_rows: list[tuple[Any, ...]]
    _results_filter_matching_rows: list[tuple[Any, ...]]
    _results_filter_fuzzy: bool
    _results_filter_debounce_timer: Timer | None
    _results_filter_pending_update: bool
    _tooltip_cell_coord: tuple[int, int] | None
    _tooltip_showing: bool
    _value_view_active: bool
    MAX_FILTER_MATCHES: int


class ResultsActionsProtocol(Protocol):
    def _copy_text(self, text: str) -> bool:
        ...

    def _flash_table_yank(self, table: SqlitDataTable, scope: str) -> None:
        ...

    def _format_tsv(self, columns: list[str], rows: list[tuple[Any, ...]]) -> str:
        ...

    def _replace_results_table(self, columns: list[str], rows: list[tuple[Any, ...]]) -> None:
        ...

    def _replace_results_table_raw(self, columns: list[str], rows: list[tuple[Any, ...]]) -> None:
        ...

    def _restore_results_table(self) -> None:
        ...

    def _get_debounce_ms(self, row_count: int) -> int:
        ...

    def action_results_filter(self) -> None:
        ...

    def action_results_filter_close(self) -> None:
        ...

    def action_results_filter_accept(self) -> None:
        ...

    def action_results_filter_next(self) -> None:
        ...

    def action_results_filter_prev(self) -> None:
        ...

    def _jump_to_current_results_match(self) -> None:
        ...

    def _schedule_filter_update(self) -> None:
        ...

    def _do_debounced_filter_update(self) -> None:
        ...

    def _update_results_filter(self) -> None:
        ...

    def _rebuild_results_with_matches(self, matching_rows: list[tuple[Any, ...]], search_text: str) -> None:
        ...

    def _highlight_substring(self, text: str, search_lower: str) -> str:
        ...

    def action_view_cell_full(self) -> None:
        ...


class ResultsProtocol(ResultsStateProtocol, ResultsActionsProtocol, Protocol):
    """Composite protocol for results-related mixins."""

    pass
