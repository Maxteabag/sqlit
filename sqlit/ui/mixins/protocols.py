"""Protocol definitions for mixin classes.

These protocols define the attributes and methods that mixins expect
to be available on the host App class.

Note: mixins must not inherit from Protocol at runtime (can cause metaclass
conflicts with Textual's App metaclass on newer Python versions).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.widgets import TextArea, Tree
    from ...widgets import SqlitDataTable

    from ...config import ConnectionConfig
    from ...services import ConnectionSession


class AppProtocol(Protocol):
    """Protocol defining what mixins expect from the main App class."""

    # Widget attributes (from Textual App)
    object_tree: Tree
    query_input: TextArea
    results_table: SqlitDataTable
    autocomplete_dropdown: Any  # AutocompleteDropdown widget

    # Connection state
    connections: list[ConnectionConfig]
    current_connection: Any  # database connection object
    current_config: ConnectionConfig | None
    current_adapter: Any  # DatabaseAdapter instance
    _session: ConnectionSession | None

    # UI state
    _expanded_paths: set[str]
    _loading_nodes: set[str]
    _leader_pending: bool
    screen_stack: list[Any]
    editor_mode: Any  # VimMode enum (INSERT=editing, NORMAL=read-only)

    # Result state
    _last_result_columns: list[str]
    _last_result_rows: list[tuple]
    _last_result_row_count: int
    _internal_clipboard: str

    # Textual App methods
    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float = 2.0,
    ) -> None: ...

    def call_later(self, callback: Any, *args: Any, **kwargs: Any) -> Any: ...

    def call_from_thread(self, callback: Any, *args: Any, **kwargs: Any) -> Any: ...

    def run_worker(
        self,
        work: Any,
        *,
        name: str = "",
        group: str = "default",
        description: str = "",
        exit_on_error: bool = True,
        exclusive: bool = False,
    ) -> Any: ...

    def push_screen(self, screen: Any) -> Any: ...

    def pop_screen(self) -> Any: ...

    def action_quit(self) -> None: ...

    def copy_to_clipboard(self, text: str) -> None: ...

    def set_interval(self, interval: float, callback: Any, *args: Any, **kwargs: Any) -> Any: ...

    # App-specific methods
    def _disconnect_silent(self) -> None: ...

    def connect_to_server(self, config: Any) -> Any: ...

    def _update_footer_bindings(self) -> None: ...

    def action_execute_query(self) -> None: ...

    def _update_status_bar(self) -> None: ...
