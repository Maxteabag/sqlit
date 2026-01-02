"""Protocols for schema caching and autocomplete mixins."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.timer import Timer
    from textual.worker import Worker

    from sqlit.shared.ui.spinner import Spinner


class SchemaCacheStateProtocol(Protocol):
    _schema_cache: dict[str, Any]
    _schema_indexing: bool
    _schema_worker: Worker[Any] | None
    _schema_spinner_index: int
    _schema_spinner_timer: Timer | None
    _table_metadata: dict[str, tuple[str, str, str | None]]
    _columns_loading: set[str]
    _schema_spinner: Spinner | None
    _schema_pending_dbs: list[str | None]
    _schema_total_jobs: int
    _schema_completed_jobs: int
    _schema_scheduler: Any
    _db_object_cache: dict[str, dict[str, list[Any]]]


class AutocompleteStateProtocol(Protocol):
    _autocomplete_filter: str
    _autocomplete_just_applied: bool
    _autocomplete_visible: bool
    _suppress_autocomplete_on_newline: bool
    _autocomplete_debounce_timer: Timer | None
    _text_just_changed: bool


class AutocompleteActionsProtocol(Protocol):
    def _hide_autocomplete(self) -> None:
        ...

    def _load_schema_cache(self) -> None:
        ...

    def _load_schema_directly(self) -> None:
        ...

    def _stop_schema_spinner(self) -> None:
        ...

    def _load_columns_for_table(self, table_name: str) -> None:
        ...

    def _on_autocomplete_columns_loaded(
        self, table_name: str, actual_table_name: str, column_names: list[str]
    ) -> None:
        ...

    def _location_to_offset(self, text: str, location: tuple[int, int]) -> int:
        ...

    def _offset_to_location(self, text: str, offset: int) -> tuple[int, int]:
        ...

    def _get_word_before_cursor(self, text: str, cursor_pos: int) -> tuple[str, str]:
        ...

    def _run_db_call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        ...

    def _get_current_word(self, text: str, cursor_pos: int) -> str:
        ...

    def _build_alias_map(self, text: str) -> dict[str, str]:
        ...

    def _get_autocomplete_suggestions(self, text: str, cursor_pos: int) -> list[str]:
        ...

    def _trigger_autocomplete(self, text_area: Any) -> None:
        ...

    def _has_tables_needing_columns(self, text: str) -> bool:
        ...

    def _preload_columns_for_query(self) -> None:
        ...

    def action_exit_insert_mode(self) -> None:
        ...

    def _show_autocomplete(self, suggestions: list[str], filter_text: str) -> None:
        ...

    def _apply_autocomplete(self) -> None:
        ...

    def _start_schema_spinner(self) -> None:
        ...

    def _load_schema_cache_async(self) -> Awaitable[None]:
        ...

    def _animate_schema_spinner(self) -> None:
        ...

    def _update_schema_cache(
        self, schema_cache: dict[str, Any], table_metadata: dict[str, tuple[str, str, str | None]] | None = None
    ) -> None:
        ...

    def _on_databases_loaded(self, databases: list[Any]) -> None:
        ...

    def _on_databases_error(self, error: Exception) -> None:
        ...

    def _load_tables_job(self, database: str | None) -> None:
        ...

    def _load_views_job(self, database: str | None) -> None:
        ...

    def _load_procedures_job(self, database: str | None) -> None:
        ...

    def _on_tables_loaded(self, tables: list[Any], database: str | None, cache_key: str) -> None:
        ...

    def _on_tables_error(self, error: Exception, database: str | None) -> None:
        ...

    def _process_tables_result(self, tables: list[Any], database: str | None, cache_key: str) -> None:
        ...

    def _on_views_loaded(self, views: list[Any], database: str | None, cache_key: str) -> None:
        ...

    def _on_views_error(self, error: Exception, database: str | None) -> None:
        ...

    def _process_views_result(self, views: list[Any], database: str | None, cache_key: str) -> None:
        ...

    def _on_procedures_loaded(self, procedures: list[Any], database: str | None, cache_key: str) -> None:
        ...

    def _on_procedures_error(self, error: Exception, database: str | None) -> None:
        ...

    def _process_procedures_result(self, procedures: list[Any], cache_key: str) -> None:
        ...

    def _schema_job_complete(self) -> None:
        ...


class AutocompleteProtocol(SchemaCacheStateProtocol, AutocompleteStateProtocol, AutocompleteActionsProtocol, Protocol):
    """Composite protocol for autocomplete and schema cache mixins."""

    pass
