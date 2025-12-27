"""Autocomplete mixin for SSMSTUI."""

from __future__ import annotations

import re
from typing import Any

from textual.timer import Timer
from textual.widgets import TextArea
from textual.worker import Worker

from ..protocols import AppProtocol
from ...sql_completion import (
    SQL_OPERATORS,
    SuggestionType,
    extract_table_refs,
    fuzzy_match,
    get_all_functions,
    get_all_keywords,
    get_completions,
    get_context,
)

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AutocompleteMixin:
    """Mixin providing SQL autocomplete functionality."""

    _schema_worker: Worker[Any] | None = None
    _schema_spinner_timer: Timer | None = None
    _schema_cache: dict[str, Any] = {}
    _table_metadata: dict[str, tuple[str, str, str | None]] = {}
    _autocomplete_debounce_timer: Timer | None = None
    # Shared cache for raw DB objects - used by both tree and autocomplete
    # Structure: {db_name: {"tables": [(schema, name), ...], "views": [...], "procedures": [...]}}
    _db_object_cache: dict[str, dict[str, list[Any]]] = {}

    def _run_db_call(self: AppProtocol, fn: Any, *args: Any, **kwargs: Any) -> Any:
        session = getattr(self, "_session", None)
        if session is not None:
            return session.executor.submit(fn, *args, **kwargs).result()
        return fn(*args, **kwargs)

    def _get_current_word(self, text: str, cursor_pos: int) -> str:
        """Get the word currently being typed at cursor position."""
        before_cursor = text[:cursor_pos]

        # Handle table.column case - get just the part after dot
        if "." in before_cursor:
            dot_match = re.search(r"\.(\w*)$", before_cursor)
            if dot_match:
                return dot_match.group(1)

        # Get word before cursor
        match = re.search(r"(\w*)$", before_cursor)
        if match:
            return match.group(1)
        return ""

    def _build_alias_map(self: AppProtocol, text: str) -> dict[str, str]:
        """Build a map of alias -> table name from the SQL text."""
        table_refs = extract_table_refs(text)
        known_tables = set(t.lower() for t in self._schema_cache.get("tables", []))
        known_tables.update(t.lower() for t in self._schema_cache.get("views", []))

        alias_map: dict[str, str] = {}
        for ref in table_refs:
            if ref.alias and ref.name.lower() in known_tables:
                alias_map[ref.alias.lower()] = ref.name
        return alias_map

    def _get_autocomplete_suggestions(self: AppProtocol, text: str, cursor_pos: int) -> list[str]:
        """Get autocomplete suggestions using the SQL completion engine."""
        # Build schema data for get_completions
        tables = self._schema_cache.get("tables", []) + self._schema_cache.get("views", [])
        columns = self._schema_cache.get("columns", {})
        procedures = self._schema_cache.get("procedures", [])

        # First check if we need to lazy-load columns before calling get_completions
        suggestions = get_context(text, cursor_pos)
        if suggestions:
            alias_map = self._build_alias_map(text)
            table_refs = extract_table_refs(text)
            loading = getattr(self, "_columns_loading", set())

            for suggestion in suggestions:
                if suggestion.type == SuggestionType.COLUMN:
                    # Check if any tables need column loading
                    for ref in table_refs:
                        table_key = ref.name.lower()
                        if table_key not in columns and table_key not in loading:
                            self._load_columns_for_table(table_key)
                            return ["Loading..."]
                        elif table_key in loading:
                            return ["Loading..."]

                elif suggestion.type == SuggestionType.ALIAS_COLUMN:
                    scope = suggestion.table_scope
                    if scope:
                        scope_lower = scope.lower()
                        table_key = alias_map.get(scope_lower, scope_lower)

                        if table_key not in columns and table_key not in loading:
                            self._load_columns_for_table(table_key)
                            return ["Loading..."]
                        elif table_key in loading:
                            return ["Loading..."]

        # Now call get_completions with all available data
        results = get_completions(
            text,
            cursor_pos,
            tables,
            columns,
            procedures,
            include_keywords=True,
            include_functions=True,
        )

        return results

    def _load_columns_for_table(self: AppProtocol, table_name: str) -> None:
        """Lazy load columns for a specific table (async via worker)."""
        if not self.current_connection or not self.current_adapter:
            return

        if not hasattr(self, "_columns_loading") or self._columns_loading is None:
            self._columns_loading = set()

        if table_name in self._columns_loading:
            return

        metadata = self._table_metadata.get(table_name)
        if not metadata:
            return

        schema_name, actual_table_name, database = metadata
        self._columns_loading.add(table_name)

        def work() -> None:
            adapter = self.current_adapter
            connection = self.current_connection
            if not adapter or not connection:
                column_names = []
            else:
                try:
                    db_arg = database
                    if hasattr(self, "_get_metadata_db_arg"):
                        db_arg = self._get_metadata_db_arg(database)
                    columns = self._run_db_call(
                        adapter.get_columns, connection, actual_table_name, db_arg, schema_name
                    )
                    column_names = [c.name for c in columns]
                except Exception:
                    column_names = []

            self.call_from_thread(
                self._on_autocomplete_columns_loaded,
                table_name,
                actual_table_name,
                column_names,
            )

        self.run_worker(work, name=f"load-columns-{table_name}", thread=True, exclusive=False)

    def _on_autocomplete_columns_loaded(
        self: AppProtocol, table_name: str, actual_table_name: str, column_names: list[str]
    ) -> None:
        """Handle column load completion for autocomplete on main thread."""
        self._columns_loading.discard(table_name)
        self._schema_cache["columns"][table_name] = column_names
        self._schema_cache["columns"][actual_table_name.lower()] = column_names

        # Refresh autocomplete if visible (replaces "Loading..." with actual columns)
        if self._autocomplete_visible:
            text = self.query_input.text
            cursor_loc = self.query_input.cursor_location
            cursor_pos = self._location_to_offset(text, cursor_loc)
            current_word = self._get_current_word(text, cursor_pos)
            suggestions = self._get_autocomplete_suggestions(text, cursor_pos)
            if suggestions:
                self._show_autocomplete(suggestions, current_word)
            else:
                self._hide_autocomplete()

    def _has_tables_needing_columns(self: AppProtocol, text: str) -> bool:
        """Check if there are tables in the query that need column loading."""
        if not text.strip():
            return False

        table_refs = extract_table_refs(text)
        columns_cache = self._schema_cache.get("columns", {})
        loading = getattr(self, "_columns_loading", set())

        for ref in table_refs:
            table_key = ref.name.lower()
            if table_key in columns_cache or table_key in loading:
                continue
            if table_key in self._table_metadata:
                return True
        return False

    def _preload_columns_for_query(self: AppProtocol) -> None:
        """Preload columns for all tables found in the current query (runs during idle)."""
        if not self.current_connection or not self.current_adapter:
            return

        text = self.query_input.text
        if not text.strip():
            return

        # Extract table references from the query
        table_refs = extract_table_refs(text)
        columns_cache = self._schema_cache.get("columns", {})
        loading = getattr(self, "_columns_loading", set())

        for ref in table_refs:
            table_key = ref.name.lower()
            # Skip if already loaded or currently loading
            if table_key in columns_cache or table_key in loading:
                continue
            # Skip if not a known table
            if table_key not in self._table_metadata:
                continue
            # Queue column loading
            self._load_columns_for_table(table_key)

    def _show_autocomplete(self: AppProtocol, suggestions: list[str], filter_text: str) -> None:
        """Show the autocomplete dropdown with suggestions."""

        if not suggestions:
            self._hide_autocomplete()
            return

        dropdown = self.autocomplete_dropdown
        dropdown.set_items(suggestions, filter_text)

        cursor_loc = self.query_input.cursor_location
        dropdown.styles.offset = (cursor_loc[1] + 2, cursor_loc[0] + 1)

        dropdown.show()
        self._autocomplete_visible = True

    def _hide_autocomplete(self: AppProtocol) -> None:
        """Hide the autocomplete dropdown."""
        try:
            self.autocomplete_dropdown.hide()
        except Exception:
            pass  # Widget not mounted yet
        self._autocomplete_visible = False

    def _apply_autocomplete(self: AppProtocol) -> None:
        """Apply the selected autocomplete suggestion."""
        selected = self.autocomplete_dropdown.get_selected()

        if not selected:
            self._hide_autocomplete()
            return

        self._autocomplete_just_applied = True

        text = self.query_input.text
        cursor_loc = self.query_input.cursor_location
        cursor_pos = self._location_to_offset(text, cursor_loc)

        word_start = cursor_pos
        while word_start > 0 and text[word_start - 1] not in " \t\n,()[].":
            word_start -= 1

        if word_start > 0 and text[word_start - 1] == ".":
            new_text = text[:cursor_pos] + selected[len(text[word_start:cursor_pos]) :] + text[cursor_pos:]
        else:
            new_text = text[:word_start] + selected + text[cursor_pos:]

        self.query_input.text = new_text

        new_cursor_pos = word_start + len(selected)
        new_loc = self._offset_to_location(new_text, new_cursor_pos)
        self.query_input.cursor_location = new_loc

        self._hide_autocomplete()

    def _location_to_offset(self, text: str, location: tuple[int, int]) -> int:
        """Convert (row, col) location to text offset."""
        row, col = location
        lines = text.split("\n")
        offset = sum(len(lines[i]) + 1 for i in range(row))
        offset += col
        return min(offset, len(text))

    def _offset_to_location(self, text: str, offset: int) -> tuple[int, int]:
        """Convert text offset to (row, col) location."""
        lines = text.split("\n")
        current_offset = 0
        for row, line in enumerate(lines):
            if current_offset + len(line) >= offset:
                return (row, offset - current_offset)
            current_offset += len(line) + 1
        return (len(lines) - 1, len(lines[-1]) if lines else 0)

    def on_text_area_changed(self: AppProtocol, event: TextArea.Changed) -> None:
        """Handle text changes in the query editor for autocomplete."""
        from ...widgets import VimMode
        from ...idle_scheduler import on_user_activity

        # Track user activity for idle scheduler
        on_user_activity()

        if event.text_area.id != "query-input":
            return

        # Mark that text just changed so selection_changed knows to ignore cursor movement
        self._text_just_changed = True

        if self._autocomplete_just_applied:
            self._autocomplete_just_applied = False
            self._hide_autocomplete()
            return

        # Suppress autocomplete after Enter dismisses dropdown (newline shouldn't re-trigger)
        if getattr(self, "_suppress_autocomplete_on_newline", False):
            self._suppress_autocomplete_on_newline = False
            return

        if self.vim_mode != VimMode.INSERT:
            self._hide_autocomplete()
            return

        if not self.current_connection:
            return

        # Cancel any pending debounce timer
        if self._autocomplete_debounce_timer is not None:
            self._autocomplete_debounce_timer.stop()
            self._autocomplete_debounce_timer = None

        # Debounce: wait 100ms before triggering autocomplete
        self._autocomplete_debounce_timer = self.set_timer(
            0.1, lambda: self._trigger_autocomplete(event.text_area)
        )

    def _trigger_autocomplete(self: AppProtocol, text_area: TextArea) -> None:
        """Actually trigger autocomplete after debounce delay."""
        from ...idle_scheduler import get_idle_scheduler, Priority

        self._autocomplete_debounce_timer = None

        text = text_area.text
        cursor_loc = text_area.cursor_location
        cursor_pos = self._location_to_offset(text, cursor_loc)

        # Get current word for display purposes
        current_word = self._get_current_word(text, cursor_pos)

        # Get suggestions using the SQL completion engine
        suggestions = self._get_autocomplete_suggestions(text, cursor_pos)

        if suggestions:
            self._show_autocomplete(suggestions, current_word)
        else:
            self._hide_autocomplete()

        # Queue column preloading for tables in the query (runs during idle)
        # Only queue if there are actually tables that need column loading
        scheduler = get_idle_scheduler()
        if scheduler and self._has_tables_needing_columns(text):
            # Cancel any previous preload job - we'll queue a fresh one
            scheduler.cancel_all(name="preload-columns")
            scheduler.request_idle_callback(
                self._preload_columns_for_query,
                priority=Priority.LOW,
                name="preload-columns",
            )

    def on_descendant_blur(self: AppProtocol, event: Any) -> None:
        """Handle blur events - don't hide autocomplete on window focus loss."""
        # Only hide if focus moves to another widget within the app (not window blur)
        # We want autocomplete to stay visible when user moves mouse to another window
        pass

    def action_autocomplete_next(self: AppProtocol) -> None:
        """Move to next autocomplete suggestion."""
        if self._autocomplete_visible:
            self.autocomplete_dropdown.move_selection(1)

    def action_autocomplete_prev(self: AppProtocol) -> None:
        """Move to previous autocomplete suggestion."""
        if self._autocomplete_visible:
            self.autocomplete_dropdown.move_selection(-1)

    def action_autocomplete_close(self: AppProtocol) -> None:
        """Close autocomplete dropdown without exiting insert mode."""
        self._hide_autocomplete()

    def on_text_area_selection_changed(self: AppProtocol, event: Any) -> None:
        """Hide autocomplete when cursor moves without text change."""
        if not self._autocomplete_visible:
            return

        if getattr(event, "text_area", None) and getattr(event.text_area, "id", None) != "query-input":
            return

        # If text just changed, this cursor movement is from typing - ignore it
        if getattr(self, "_text_just_changed", False):
            self._text_just_changed = False
            return

        # Cursor moved without text change (arrow keys, click, etc.) - hide autocomplete
        self._hide_autocomplete()

    def on_key(self: AppProtocol, event: Any) -> None:
        """Handle key events for autocomplete navigation."""
        from ...widgets import VimMode
        from ...idle_scheduler import on_user_activity

        # Track user activity for idle scheduler
        on_user_activity()

        # Handle autocomplete navigation
        if not self._autocomplete_visible:
            return

        dropdown = self.autocomplete_dropdown

        if event.key == "down":
            dropdown.move_selection(1)
            event.prevent_default()
            event.stop()
        elif event.key == "up":
            dropdown.move_selection(-1)
            event.prevent_default()
            event.stop()
        elif event.key in ("tab", "enter"):
            if self.vim_mode == VimMode.INSERT and dropdown.filtered_items:
                self._apply_autocomplete()
                event.prevent_default()
                event.stop()
        elif event.key == "escape":
            # Hide autocomplete AND exit insert mode (go to normal mode)
            self.action_exit_insert_mode()
            event.prevent_default()
            event.stop()

    def _load_schema_cache(self: AppProtocol) -> None:
        """Load database schema for autocomplete using threaded workers."""
        if not self.current_connection or not self.current_config or not self.current_adapter:
            return

        # Cancel any existing schema worker
        if hasattr(self, "_schema_worker") and self._schema_worker is not None:
            self._schema_worker.cancel()

        # Initialize empty cache immediately
        self._schema_cache = {
            "tables": [],
            "views": [],
            "columns": {},
            "procedures": [],
        }
        self._table_metadata = {}
        self._columns_loading = set()  # Clear any in-progress column loads
        self._db_object_cache = {}  # Clear shared object cache

        # Start schema indexing spinner
        self._start_schema_spinner()

        # Load schema directly using threaded workers (no idle scheduler needed)
        self._load_schema_directly()

    def _load_schema_directly(self: AppProtocol) -> None:
        """Load schema using threaded workers - runs immediately without idle scheduler."""
        adapter = self.current_adapter
        connection = self.current_connection
        config = self.current_config

        if not adapter or not connection or not config:
            self._stop_schema_spinner()
            return

        # Track pending database loads
        self._schema_pending_dbs: list[str | None] = []
        self._schema_total_jobs = 0
        self._schema_completed_jobs = 0

        if adapter.supports_multiple_databases:
            db = None
            if hasattr(self, "_get_effective_database"):
                db = self._get_effective_database()
            if db:
                # Single database specified - load immediately
                self._on_databases_loaded([db])
            elif adapter.supports_cross_database_queries:
                # Need to fetch database list - offload to thread
                def work() -> None:
                    try:
                        all_dbs = adapter.get_databases(connection)
                        system_dbs = {s.lower() for s in adapter.system_databases}
                        databases = [d for d in all_dbs if d.lower() not in system_dbs]
                        self.call_from_thread(self._on_databases_loaded, databases)
                    except Exception as e:
                        self.call_from_thread(self._on_databases_error, e)

                self.run_worker(work, thread=True, name="get-databases")
            else:
                self._stop_schema_spinner()
        else:
            # No multiple databases - just proceed with None
            self._on_databases_loaded([None])

    def _load_schema_via_idle_scheduler(self: AppProtocol, scheduler: Any) -> None:
        """Load schema using idle scheduler for smoother UI."""
        from ...idle_scheduler import Priority

        adapter = self.current_adapter
        connection = self.current_connection
        config = self.current_config

        if not adapter or not connection or not config:
            self._stop_schema_spinner()
            return

        # Track pending database loads
        self._schema_pending_dbs: list[str | None] = []
        self._schema_total_jobs = 0
        self._schema_completed_jobs = 0
        # Store scheduler reference for use in callbacks
        self._schema_scheduler = scheduler

        def get_databases_job() -> None:
            """First job: dispatch thread to get list of databases."""
            if adapter.supports_multiple_databases:
                db = None
                if hasattr(self, "_get_effective_database"):
                    db = self._get_effective_database()
                if db:
                    # Single database specified - no need for DB call
                    self._on_databases_loaded([db])
                elif adapter.supports_cross_database_queries:
                    # Need to fetch database list - offload to thread
                    def work() -> None:
                        try:
                            all_dbs = adapter.get_databases(connection)
                            system_dbs = {s.lower() for s in adapter.system_databases}
                            databases = [d for d in all_dbs if d.lower() not in system_dbs]
                            self.call_from_thread(self._on_databases_loaded, databases)
                        except Exception as e:
                            self.call_from_thread(self._on_databases_error, e)

                    self.run_worker(work, thread=True, name="get-databases")
                else:
                    self._stop_schema_spinner()
            else:
                # No multiple databases - just proceed with None
                self._on_databases_loaded([None])

        # Queue the first job with high priority
        scheduler.request_idle_callback(
            get_databases_job,
            priority=Priority.HIGH,
            name="schema-load",
        )

    def _on_databases_loaded(self: AppProtocol, databases: list) -> None:
        """Handle databases list loaded - spawn threaded workers for each database."""
        adapter = self.current_adapter

        if not adapter:
            self._stop_schema_spinner()
            return

        self._schema_pending_dbs = databases
        self._schema_total_jobs = len(databases) * 3  # tables, views, procedures per db

        # Spawn workers directly - they're threaded so won't block
        for database in databases:
            self._load_tables_job(database)
            self._load_views_job(database)
            if adapter.supports_stored_procedures:
                self._load_procedures_job(database)
            else:
                self._schema_completed_jobs += 1  # Skip procedures

    def _on_databases_error(self: AppProtocol, error: Exception) -> None:
        """Handle error getting databases list."""
        self.log.error(f"Error getting databases: {error}")
        self._stop_schema_spinner()

    def _load_tables_job(self: AppProtocol, database: str | None) -> None:
        """Idle job: load tables for a single database (dispatches to thread)."""
        adapter = self.current_adapter
        connection = self.current_connection

        if not adapter or not connection:
            self._schema_job_complete()
            return

        cache_key = database or "__default__"

        # Check shared cache first (may have been populated by tree expansion)
        if cache_key in self._db_object_cache and "tables" in self._db_object_cache[cache_key]:
            self._process_tables_result(self._db_object_cache[cache_key]["tables"], database, cache_key)
            return

        # Offload DB call to thread
        def work() -> None:
            try:
                db_arg = database
                if hasattr(self, "_get_metadata_db_arg"):
                    db_arg = self._get_metadata_db_arg(database)
                tables = adapter.get_tables(connection, db_arg)
                # Store in shared cache and process on main thread
                self.call_from_thread(self._on_tables_loaded, tables, database, cache_key)
            except Exception as e:
                self.call_from_thread(self._on_tables_error, e, database)

        self.run_worker(work, thread=True, name=f"load-tables-{cache_key}")

    def _on_tables_loaded(self: AppProtocol, tables: list, database: str | None, cache_key: str) -> None:
        """Handle tables loaded from thread."""
        if cache_key not in self._db_object_cache:
            self._db_object_cache[cache_key] = {}
        self._db_object_cache[cache_key]["tables"] = tables
        self._process_tables_result(tables, database, cache_key)

    def _on_tables_error(self: AppProtocol, error: Exception, database: str | None) -> None:
        """Handle tables load error from thread."""
        self.log.error(f"Error loading tables for {database}: {error}")
        self._schema_job_complete()

    def _process_tables_result(self: AppProtocol, tables: list, database: str | None, cache_key: str) -> None:
        """Process tables result on main thread."""
        adapter = self.current_adapter
        if not adapter:
            self._schema_job_complete()
            return

        try:
            single_db = len(getattr(self, "_schema_pending_dbs", [None])) == 1

            for schema_name, table_name in tables:
                if single_db:
                    self._schema_cache["tables"].append(table_name)
                else:
                    quoted_db = adapter.quote_identifier(database) if database else ""
                    quoted_schema = adapter.quote_identifier(schema_name)
                    quoted_table = adapter.quote_identifier(table_name)
                    if database:
                        full_name = f"{quoted_db}.{quoted_schema}.{quoted_table}"
                    else:
                        full_name = f"{quoted_schema}.{quoted_table}"
                    self._schema_cache["tables"].append(full_name)

                # Store metadata for column loading
                display_name = adapter.format_table_name(schema_name, table_name)
                self._table_metadata[display_name.lower()] = (schema_name, table_name, database)
                self._table_metadata[table_name.lower()] = (schema_name, table_name, database)
                if database:
                    self._table_metadata[f"{database}.{table_name}".lower()] = (schema_name, table_name, database)
                    if not single_db:
                        self._table_metadata[full_name.lower()] = (schema_name, table_name, database)

        except Exception as e:
            self.log.error(f"Error processing tables for {database}: {e}")

        self._schema_job_complete()

    def _load_views_job(self: AppProtocol, database: str | None) -> None:
        """Idle job: load views for a single database (dispatches to thread)."""
        adapter = self.current_adapter
        connection = self.current_connection

        if not adapter or not connection:
            self._schema_job_complete()
            return

        cache_key = database or "__default__"

        # Check shared cache first (may have been populated by tree expansion)
        if cache_key in self._db_object_cache and "views" in self._db_object_cache[cache_key]:
            self._process_views_result(self._db_object_cache[cache_key]["views"], database, cache_key)
            return

        # Offload DB call to thread
        def work() -> None:
            try:
                db_arg = database
                if hasattr(self, "_get_metadata_db_arg"):
                    db_arg = self._get_metadata_db_arg(database)
                views = adapter.get_views(connection, db_arg)
                self.call_from_thread(self._on_views_loaded, views, database, cache_key)
            except Exception as e:
                self.call_from_thread(self._on_views_error, e, database)

        self.run_worker(work, thread=True, name=f"load-views-{cache_key}")

    def _on_views_loaded(self: AppProtocol, views: list, database: str | None, cache_key: str) -> None:
        """Handle views loaded from thread."""
        if cache_key not in self._db_object_cache:
            self._db_object_cache[cache_key] = {}
        self._db_object_cache[cache_key]["views"] = views
        self._process_views_result(views, database, cache_key)

    def _on_views_error(self: AppProtocol, error: Exception, database: str | None) -> None:
        """Handle views load error from thread."""
        self.log.error(f"Error loading views for {database}: {error}")
        self._schema_job_complete()

    def _process_views_result(self: AppProtocol, views: list, database: str | None, cache_key: str) -> None:
        """Process views result on main thread."""
        adapter = self.current_adapter
        if not adapter:
            self._schema_job_complete()
            return

        try:
            single_db = len(getattr(self, "_schema_pending_dbs", [None])) == 1

            for schema_name, view_name in views:
                if single_db:
                    self._schema_cache["views"].append(view_name)
                else:
                    quoted_db = adapter.quote_identifier(database) if database else ""
                    quoted_schema = adapter.quote_identifier(schema_name)
                    quoted_view = adapter.quote_identifier(view_name)
                    if database:
                        full_name = f"{quoted_db}.{quoted_schema}.{quoted_view}"
                    else:
                        full_name = f"{quoted_schema}.{quoted_view}"
                    self._schema_cache["views"].append(full_name)

                # Store metadata for column loading
                display_name = adapter.format_table_name(schema_name, view_name)
                self._table_metadata[display_name.lower()] = (schema_name, view_name, database)
                self._table_metadata[view_name.lower()] = (schema_name, view_name, database)
                if database:
                    self._table_metadata[f"{database}.{view_name}".lower()] = (schema_name, view_name, database)
                    if not single_db:
                        self._table_metadata[full_name.lower()] = (schema_name, view_name, database)

        except Exception as e:
            self.log.error(f"Error processing views for {database}: {e}")

        self._schema_job_complete()

    def _load_procedures_job(self: AppProtocol, database: str | None) -> None:
        """Idle job: load procedures for a single database (dispatches to thread)."""
        adapter = self.current_adapter
        connection = self.current_connection

        if not adapter or not connection:
            self._schema_job_complete()
            return

        cache_key = database or "__default__"

        # Check shared cache first (may have been populated by tree expansion)
        if cache_key in self._db_object_cache and "procedures" in self._db_object_cache[cache_key]:
            self._process_procedures_result(self._db_object_cache[cache_key]["procedures"], cache_key)
            return

        # Offload DB call to thread
        def work() -> None:
            try:
                db_arg = database
                if hasattr(self, "_get_metadata_db_arg"):
                    db_arg = self._get_metadata_db_arg(database)
                procedures = adapter.get_procedures(connection, db_arg)
                self.call_from_thread(self._on_procedures_loaded, procedures, database, cache_key)
            except Exception as e:
                self.call_from_thread(self._on_procedures_error, e, database)

        self.run_worker(work, thread=True, name=f"load-procedures-{cache_key}")

    def _on_procedures_loaded(self: AppProtocol, procedures: list, database: str | None, cache_key: str) -> None:
        """Handle procedures loaded from thread."""
        if cache_key not in self._db_object_cache:
            self._db_object_cache[cache_key] = {}
        self._db_object_cache[cache_key]["procedures"] = procedures
        self._process_procedures_result(procedures, cache_key)

    def _on_procedures_error(self: AppProtocol, error: Exception, database: str | None) -> None:
        """Handle procedures load error from thread."""
        self.log.error(f"Error loading procedures for {database}: {error}")
        self._schema_job_complete()

    def _process_procedures_result(self: AppProtocol, procedures: list, cache_key: str) -> None:
        """Process procedures result on main thread."""
        try:
            self._schema_cache["procedures"].extend(procedures)
        except Exception as e:
            self.log.error(f"Error processing procedures: {e}")

        self._schema_job_complete()

    def _schema_job_complete(self: AppProtocol) -> None:
        """Called when a schema loading job completes."""
        self._schema_completed_jobs = getattr(self, "_schema_completed_jobs", 0) + 1
        total = getattr(self, "_schema_total_jobs", 1)

        if self._schema_completed_jobs >= total:
            # All jobs done - deduplicate and finalize
            self._schema_cache["tables"] = list(dict.fromkeys(self._schema_cache["tables"]))
            self._schema_cache["views"] = list(dict.fromkeys(self._schema_cache["views"]))
            self._schema_cache["procedures"] = list(dict.fromkeys(self._schema_cache["procedures"]))
            self._stop_schema_spinner()

    def _start_schema_spinner(self: AppProtocol) -> None:
        """Start the schema indexing spinner animation."""
        self._schema_indexing = True
        self._schema_spinner_index = 0
        self._update_status_bar()
        # Start timer to animate spinner
        if hasattr(self, "_schema_spinner_timer") and self._schema_spinner_timer is not None:
            self._schema_spinner_timer.stop()
        self._schema_spinner_timer = self.set_interval(0.1, self._animate_schema_spinner)

    def _stop_schema_spinner(self: AppProtocol) -> None:
        """Stop the schema indexing spinner animation."""
        self._schema_indexing = False
        if hasattr(self, "_schema_spinner_timer") and self._schema_spinner_timer is not None:
            self._schema_spinner_timer.stop()
            self._schema_spinner_timer = None
        self._update_status_bar()

    def _animate_schema_spinner(self: AppProtocol) -> None:
        """Update schema spinner animation frame."""
        if not self._schema_indexing:
            return
        self._schema_spinner_index = (self._schema_spinner_index + 1) % len(SPINNER_FRAMES)
        self._update_status_bar()

    def action_cancel_schema_indexing(self: AppProtocol) -> None:
        """Cancel ongoing schema indexing."""
        if hasattr(self, "_schema_worker") and self._schema_worker is not None:
            self._schema_worker.cancel()
            self._schema_worker = None
        self._stop_schema_spinner()
        self.notify("Schema indexing cancelled")

    async def _load_schema_cache_async(self: AppProtocol) -> None:
        """Load database schema asynchronously.

        Only loads tables, views, and procedures.
        Columns are lazy-loaded on demand when user types `table.`
        """
        import asyncio

        adapter = self.current_adapter
        connection = self.current_connection
        config = self.current_config

        if not adapter or not connection or not config:
            self._stop_schema_spinner()
            return

        schema_cache: dict = {
            "tables": [],
            "views": [],
            "columns": {},
            "procedures": [],
        }
        table_metadata: dict[str, tuple[str, str, str | None]] = {}

        async def run_db_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
            session = getattr(self, "_session", None)
            if session is not None:
                return await session.executor.run_async(fn, *args, **kwargs)
            return await asyncio.to_thread(fn, *args, **kwargs)

        try:
            databases: list[str | None]
            if adapter.supports_multiple_databases:
                db = None
                if hasattr(self, "_get_effective_database"):
                    db = self._get_effective_database()
                if db:
                    # Active/default database is set - only load that one
                    databases = [db]
                elif adapter.supports_cross_database_queries:
                    # No default database - load all non-system databases
                    all_dbs = await run_db_call(adapter.get_databases, connection)
                    system_dbs = {s.lower() for s in adapter.system_databases}
                    databases = [d for d in all_dbs if d.lower() not in system_dbs]
                else:
                    databases = []
            else:
                databases = [None]

            for database in databases:
                try:
                    # Get tables
                    db_arg = database
                    if hasattr(self, "_get_metadata_db_arg"):
                        db_arg = self._get_metadata_db_arg(database)
                    tables = await run_db_call(adapter.get_tables, connection, db_arg)
                    for schema_name, table_name in tables:
                        # Use simple name if we have a default database, full qualifier otherwise
                        if len(databases) == 1:
                            # Single database - use simple table name
                            schema_cache["tables"].append(table_name)
                        else:
                            # Multiple databases - use full qualifier [db].[schema].[table]
                            quoted_db = adapter.quote_identifier(database) if database else ""
                            quoted_schema = adapter.quote_identifier(schema_name)
                            quoted_table = adapter.quote_identifier(table_name)
                            if database:
                                full_name = f"{quoted_db}.{quoted_schema}.{quoted_table}"
                            else:
                                full_name = f"{quoted_schema}.{quoted_table}"
                            schema_cache["tables"].append(full_name)
                        # Keep metadata for column loading (multiple keys for flexible lookup)
                        display_name = adapter.format_table_name(schema_name, table_name)
                        table_metadata[display_name.lower()] = (schema_name, table_name, database)
                        table_metadata[table_name.lower()] = (schema_name, table_name, database)
                        if database:
                            table_metadata[f"{database}.{table_name}".lower()] = (schema_name, table_name, database)
                            # Also store with full quoted name for [db].[schema].[table] lookups
                            if len(databases) > 1:
                                table_metadata[full_name.lower()] = (schema_name, table_name, database)

                    # Get views
                    views = await run_db_call(adapter.get_views, connection, db_arg)
                    for schema_name, view_name in views:
                        # Use simple name if we have a default database, full qualifier otherwise
                        if len(databases) == 1:
                            # Single database - use simple view name
                            schema_cache["views"].append(view_name)
                        else:
                            # Multiple databases - use full qualifier [db].[schema].[view]
                            quoted_db = adapter.quote_identifier(database) if database else ""
                            quoted_schema = adapter.quote_identifier(schema_name)
                            quoted_view = adapter.quote_identifier(view_name)
                            if database:
                                full_name = f"{quoted_db}.{quoted_schema}.{quoted_view}"
                            else:
                                full_name = f"{quoted_schema}.{quoted_view}"
                            schema_cache["views"].append(full_name)
                        # Keep metadata for column loading (multiple keys for flexible lookup)
                        display_name = adapter.format_table_name(schema_name, view_name)
                        table_metadata[display_name.lower()] = (schema_name, view_name, database)
                        table_metadata[view_name.lower()] = (schema_name, view_name, database)
                        if database:
                            table_metadata[f"{database}.{view_name}".lower()] = (schema_name, view_name, database)
                            # Also store with full quoted name for [db].[schema].[view] lookups
                            if len(databases) > 1:
                                table_metadata[full_name.lower()] = (schema_name, view_name, database)

                    # Get procedures
                    if adapter.supports_stored_procedures:
                        procedures = await run_db_call(adapter.get_procedures, connection, db_arg)
                        schema_cache["procedures"].extend(procedures)

                except Exception:
                    pass

            # Deduplicate
            schema_cache["tables"] = list(dict.fromkeys(schema_cache["tables"]))
            schema_cache["views"] = list(dict.fromkeys(schema_cache["views"]))
            schema_cache["procedures"] = list(dict.fromkeys(schema_cache["procedures"]))

            # Update cache - columns will be lazy-loaded when needed
            self._update_schema_cache(schema_cache, table_metadata)

        except Exception as e:
            self.notify(f"Error loading schema: {e}", severity="warning")
        finally:
            self._stop_schema_spinner()

    def _update_schema_cache(self: AppProtocol, schema_cache: dict, table_metadata: dict | None = None) -> None:
        """Update the schema cache (called on main thread)."""
        self._schema_cache = schema_cache
        if table_metadata is not None:
            self._table_metadata = table_metadata
