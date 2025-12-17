"""Protocol definitions for mixin type safety."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, overload

if TYPE_CHECKING:
    from textual.screen import Screen
    from textual.timer import Timer
    from textual.widget import Widget
    from textual.widgets import DataTable, Static, TextArea, Tree
    from textual.worker import Worker

    from ..config import ConnectionConfig
    from ..db import DatabaseAdapter
    from ..services import ConnectionSession, QueryService
    from ..widgets import VimMode

QueryType = TypeVar("QueryType", bound="Widget")


class AppProtocol(Protocol):
    """Protocol defining what mixins expect from the App class.

    This protocol captures the interface that mixin classes depend on,
    allowing proper type checking without creating inheritance conflicts.
    Mixins should use `self: AppProtocol` in method signatures.
    """

    # === Textual App methods ===

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        """Show notification."""
        ...

    def push_screen(
        self,
        screen: Screen[Any] | str,
        callback: Callable[[Any], None] | Callable[[Any], Awaitable[None]] | None = None,
        wait_for_dismiss: bool = False,
    ) -> Any:
        """Push a screen onto the screen stack."""
        ...

    def pop_screen(self) -> Any:
        """Pop the current screen from the screen stack."""
        ...

    def run_worker(
        self,
        work: Any,
        name: str | None = "",
        group: str = "default",
        description: str = "",
        exit_on_error: bool = True,
        start: bool = True,
        exclusive: bool = False,
        thread: bool = False,
    ) -> Worker[Any]:
        """Run work in a worker thread/task."""
        ...

    def call_later(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Schedule a callback to run later on the main thread."""
        ...

    def call_from_thread(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call a function from a worker thread on the main thread."""
        ...

    def set_timer(
        self,
        delay: float,
        callback: Callable[[], None] | None = None,
        *,
        name: str | None = None,
        pause: bool = False,
    ) -> Timer:
        """Set a timer to call a function after a delay."""
        ...

    def set_interval(
        self,
        interval: float,
        callback: Callable[[], None] | None = None,
        *,
        name: str | None = None,
        repeat: int = 0,
        pause: bool = False,
    ) -> Timer:
        """Set an interval timer."""
        ...

    @overload
    def query_one(self, selector: str) -> Widget: ...

    @overload
    def query_one(self, selector: type[QueryType]) -> QueryType: ...

    @overload
    def query_one(self, selector: str, expect_type: type[QueryType]) -> QueryType: ...

    def query_one(self, selector: Any, expect_type: Any = None) -> Any:
        """Query for a single widget."""
        ...

    def copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard."""
        ...

    def exit(self, result: Any = None, return_code: int = 0, message: Any | None = None) -> None:
        """Exit the application."""
        ...

    # === Screen-related attributes ===

    @property
    def screen(self) -> Screen[Any]:
        """The current screen."""
        ...

    @property
    def screen_stack(self) -> list[Screen[Any]]:
        """The screen stack."""
        ...

    @property
    def focused(self) -> Any:
        """The currently focused widget."""
        ...

    @property
    def size(self) -> Any:
        """The size of the terminal."""
        ...

    @property
    def theme(self) -> str:
        """The current theme name."""
        ...

    @theme.setter
    def theme(self, value: str) -> None:
        """Set the theme."""
        ...

    # === SSMSTUI widget properties ===

    @property
    def object_tree(self) -> Tree[Any]:
        """The explorer tree widget."""
        ...

    @property
    def query_input(self) -> TextArea:
        """The query input text area."""
        ...

    @property
    def results_table(self) -> DataTable:
        """The results table widget."""
        ...

    @property
    def status_bar(self) -> Static:
        """The status bar widget."""
        ...

    @property
    def autocomplete_dropdown(self) -> Any:
        """The autocomplete dropdown widget."""
        ...

    # === Connection state ===

    connections: list[ConnectionConfig]
    current_connection: Any
    current_config: ConnectionConfig | None
    current_adapter: DatabaseAdapter | None
    current_ssh_tunnel: Any

    # === Session state ===

    _session: ConnectionSession | None
    _session_factory: Callable[[ConnectionConfig], ConnectionSession] | None
    _connection_failed: bool

    # === Vim mode state ===

    vim_mode: VimMode

    # === Tree state ===

    _expanded_paths: set[str]
    _loading_nodes: set[str]

    # === Query execution state ===

    _query_worker: Worker[Any] | None
    _query_executing: bool
    _query_start_time: float
    _spinner_index: int
    _spinner_timer: Timer | None
    _cancellable_query: Any

    # === Schema cache state ===

    _schema_cache: dict[str, Any]
    _schema_indexing: bool
    _schema_worker: Worker[Any] | None
    _schema_spinner_index: int
    _schema_spinner_timer: Timer | None
    _table_metadata: dict[str, tuple[str, str, str | None]]
    _columns_loading: set[str]

    # === Autocomplete state ===

    _autocomplete_filter: str
    _autocomplete_just_applied: bool
    _autocomplete_visible: bool

    # === Results state ===

    _last_result_columns: list[str]
    _last_result_rows: list[tuple[Any, ...]]
    _last_result_row_count: int
    _internal_clipboard: str
    _last_query_table: dict[str, Any] | None

    # === UI state ===

    _fullscreen_mode: str
    _last_notification: str
    _last_notification_severity: str
    _last_notification_time: str
    _notification_timer: Timer | None
    _notification_history: list[tuple[str, str, str]]
    _leader_timer: Timer | None
    _leader_pending: bool
    _state_machine: Any
    _mock_profile: Any

    # === SSMSTUI methods that mixins call on each other ===

    def refresh_tree(self) -> None:
        """Refresh the explorer tree."""
        ...

    def populate_connected_tree(self) -> None:
        """Populate tree with database objects when connected."""
        ...

    def _update_status_bar(self) -> None:
        """Update status bar with connection and vim mode info."""
        ...

    def _update_footer_bindings(self) -> None:
        """Update footer with context-appropriate bindings."""
        ...

    def _hide_autocomplete(self) -> None:
        """Hide the autocomplete dropdown."""
        ...

    def _load_schema_cache(self) -> None:
        """Load database schema for autocomplete asynchronously."""
        ...

    def _stop_schema_spinner(self) -> None:
        """Stop the schema indexing spinner animation."""
        ...

    def _disconnect_silent(self) -> None:
        """Disconnect from current database without notification."""
        ...

    def connect_to_server(self, config: ConnectionConfig) -> None:
        """Connect to a database (async, non-blocking)."""
        ...

    def action_execute_query(self) -> None:
        """Execute the current query."""
        ...

    # === Tree Mixin methods ===

    def _db_type_badge(self, db_type: str) -> str:
        """Get short badge for database type."""
        ...

    def _add_database_object_nodes(self, node: Any, database: str | None) -> None:
        """Add database object nodes (tables, views, etc.) to a folder."""
        ...

    def _restore_subtree_expansion(self, node: Any) -> None:
        """Restore expansion state for a subtree."""
        ...

    def _get_node_path(self, node: Any) -> str:
        """Get unique path for a node."""
        ...

    def _save_expanded_state(self) -> None:
        """Save currently expanded nodes."""
        ...

    def _load_columns_async(self, node: Any, data: Any) -> None:
        """Load columns for a table or view asynchronously."""
        ...

    def _load_folder_async(self, node: Any, data: Any) -> None:
        """Load folder content asynchronously."""
        ...

    def _on_columns_loaded(
        self, node: Any, db_name: str | None, schema_name: str, obj_name: str, columns: list[Any]
    ) -> None:
        """Handle columns loaded event."""
        ...

    def _on_tree_load_error(self, node: Any, error_message: str) -> None:
        """Handle tree loading error."""
        ...

    def _on_folder_loaded(self, node: Any, db_name: str | None, folder_type: str, items: list[Any]) -> None:
        """Handle folder content loaded event."""
        ...

    def _add_schema_grouped_items(
        self, node: Any, db_name: str | None, folder_type: str, items: list[Any], default_schema: str
    ) -> None:
        """Add items grouped by schema."""
        ...

    # === Autocomplete Mixin methods ===

    def _load_columns_for_table(self, table_name: str) -> None:
        """Load columns for a table for autocomplete."""
        ...

    def _on_autocomplete_columns_loaded(self, table_name: str, actual_table_name: str, column_names: list[str]) -> None:
        """Handle columns loaded for autocomplete."""
        ...

    def _location_to_offset(self, text: str, location: tuple[int, int]) -> int:
        """Convert row/col location to string offset."""
        ...

    def _offset_to_location(self, text: str, offset: int) -> tuple[int, int]:
        """Convert string offset to row/col location."""
        ...

    def _get_word_before_cursor(self, text: str, cursor_pos: int) -> tuple[str, str]:
        """Get the word before the cursor."""
        ...

    def _get_autocomplete_suggestions(self, word: str, context: str) -> list[str]:
        """Get autocomplete suggestions."""
        ...

    def _show_autocomplete(self, suggestions: list[str], filter_text: str) -> None:
        """Show the autocomplete dropdown."""
        ...

    def _apply_autocomplete(self) -> None:
        """Apply the selected autocomplete suggestion."""
        ...

    def _start_schema_spinner(self) -> None:
        """Start the schema indexing spinner."""
        ...

    def _load_schema_cache_async(self) -> Awaitable[None]:
        """Load schema cache asynchronously."""
        ...

    def _animate_schema_spinner(self) -> None:
        """Animate the schema spinner."""
        ...

    def _update_schema_cache(
        self, schema_cache: dict[str, Any], table_metadata: dict[str, tuple[str, str, str | None]] | None = None
    ) -> None:
        """Update the schema cache."""
        ...

    # === Results Mixin methods ===

    def _copy_text(self, text: str) -> bool:
        """Copy text to clipboard."""
        ...

    def _flash_table_yank(self, table: DataTable, scope: str) -> None:
        """Flash the table to indicate copy."""
        ...

    def _format_tsv(self, columns: list[str], rows: list[tuple[Any, ...]]) -> str:
        """Format results as TSV."""
        ...

    # === Query Mixin methods ===

    @property
    def _query_service(self) -> QueryService | None:
        """The query execution service."""
        ...

    def _execute_query_common(self, keep_insert_mode: bool) -> None:
        """Common logic for executing queries."""
        ...

    def _start_query_spinner(self) -> None:
        """Start the query execution spinner."""
        ...

    def _run_query_async(self, query: str, keep_insert_mode: bool) -> Awaitable[None]:
        """Run a query asynchronously."""
        ...

    def _animate_spinner(self) -> None:
        """Animate the query spinner."""
        ...

    def _display_query_error(self, error_message: str) -> None:
        """Display a query error."""
        ...

    def _stop_query_spinner(self) -> None:
        """Stop the query spinner."""
        ...

    def _display_query_results(
        self, columns: list[str], rows: list[tuple[Any, ...]], row_count: int, truncated: bool, elapsed_ms: float
    ) -> None:
        """Display query results in the table."""
        ...

    def _display_non_query_result(self, affected: int, elapsed_ms: float) -> None:
        """Display non-query result (rows affected)."""
        ...

    def _restore_insert_mode(self) -> None:
        """Restore insert mode if it was active."""
        ...

    def _handle_history_result(self, result: Any) -> None:
        """Handle result from history screen."""
        ...

    def _delete_history_entry(self, timestamp: str) -> None:
        """Delete a history entry."""
        ...

    def action_show_history(self) -> None:
        """Show query history."""
        ...

    # === Connection Mixin methods ===

    def _handle_install_confirmation(self, confirmed: bool, error: Any) -> None:
        """Handle driver installation confirmation."""
        ...

    def _set_connection_screen_footer(self) -> None:
        """Set footer for connection screen."""
        ...

    def _wrap_connection_result(self, result: tuple[Any, ...] | None) -> None:
        """Wrap connection result."""
        ...

    def call_next(self, *args: Any, **kwargs: Any) -> None:
        """Call next handler (Installer pattern)."""
        ...

    def handle_connection_result(self, result: tuple[Any, ...] | None) -> None:
        """Handle connection result."""
        ...

    def _do_delete_connection(self, config: ConnectionConfig) -> None:
        """Delete connection."""
        ...

    def _handle_connection_picker_result(self, result: str | None) -> None:
        """Handle connection picker result."""
        ...

    # === UI Navigation Mixin methods ===

    def _set_fullscreen_mode(self, mode: str) -> None:
        """Set fullscreen mode."""
        ...

    def _update_section_labels(self) -> None:
        """Update section labels."""
        ...

    def _show_error_in_results(self, message: str, timestamp: str) -> None:
        """Show error in results table."""
        ...

    def _show_leader_menu(self) -> None:
        """Show leader menu."""
        ...

    def _cancel_leader_pending(self) -> None:
        """Cancel leader pending state."""
        ...

    def _handle_leader_result(self, result: str | None) -> None:
        """Handle leader menu result."""
        ...

    def _execute_leader_command(self, action: str) -> None:
        """Execute leader command."""
        ...
