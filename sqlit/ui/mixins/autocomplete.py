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
    get_context,
)

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AutocompleteMixin:
    """Mixin providing SQL autocomplete functionality."""

    _schema_worker: Worker[Any] | None = None
    _schema_spinner_timer: Timer | None = None
    _schema_cache: dict[str, Any] = {}
    _table_metadata: dict[str, tuple[str, str, str | None]] = {}

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
        """Get autocomplete suggestions using the new SQL completion engine."""
        suggestions = get_context(text, cursor_pos)
        if not suggestions:
            return []

        current_word = self._get_current_word(text, cursor_pos)
        results: list[str] = []

        # Build alias map for column lookups
        alias_map = self._build_alias_map(text)

        # Get table refs for column scoping
        table_refs = extract_table_refs(text)

        for suggestion in suggestions:
            if suggestion.type == SuggestionType.TABLE:
                # Suggest tables and views
                results.extend(self._schema_cache.get("tables", []))
                results.extend(self._schema_cache.get("views", []))

            elif suggestion.type == SuggestionType.COLUMN:
                # Suggest columns from all tables in scope
                loading = getattr(self, "_columns_loading", set())
                any_loading = False

                for ref in table_refs:
                    table_key = ref.name.lower()
                    if table_key in self._schema_cache.get("columns", {}):
                        results.extend(self._schema_cache["columns"][table_key])
                    elif table_key in loading:
                        any_loading = True
                    else:
                        self._load_columns_for_table(table_key)
                        any_loading = True

                if any_loading and not results:
                    results.append("Loading...")

            elif suggestion.type == SuggestionType.ALIAS_COLUMN:
                # Suggest columns for specific table/alias
                scope = suggestion.table_scope
                if scope:
                    scope_lower = scope.lower()
                    table_key = scope_lower

                    # Check if it's an alias
                    if scope_lower in alias_map:
                        table_key = alias_map[scope_lower].lower()

                    # Check if columns are in cache
                    if table_key in self._schema_cache.get("columns", {}):
                        results.extend(self._schema_cache["columns"][table_key])
                    else:
                        # Check if currently loading
                        loading = getattr(self, "_columns_loading", set())
                        if table_key in loading or scope_lower in loading:
                            results.append("Loading...")
                        else:
                            # Start loading columns
                            self._load_columns_for_table(table_key)
                            results.append("Loading...")

            elif suggestion.type == SuggestionType.PROCEDURE:
                results.extend(self._schema_cache.get("procedures", []))

            elif suggestion.type == SuggestionType.KEYWORD:
                results.extend(get_all_keywords())
                results.extend(get_all_functions())

            elif suggestion.type == SuggestionType.OPERATOR:
                results.extend(SQL_OPERATORS)

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_results: list[str] = []
        for r in results:
            if r.lower() not in seen:
                seen.add(r.lower())
                unique_results.append(r)

        # Apply fuzzy matching
        return fuzzy_match(current_word, unique_results)

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
                    columns = self._run_db_call(
                        adapter.get_columns, connection, actual_table_name, database, schema_name
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

        if event.text_area.id != "query-input":
            return

        # Mark that text just changed so selection_changed knows to ignore cursor movement
        self._text_just_changed = True

        if self._autocomplete_just_applied:
            self._autocomplete_just_applied = False
            self._hide_autocomplete()
            return

        if self.vim_mode != VimMode.INSERT:
            self._hide_autocomplete()
            return

        if not self.current_connection:
            return

        text = event.text_area.text
        cursor_loc = event.text_area.cursor_location
        cursor_pos = self._location_to_offset(text, cursor_loc)

        # Get current word for display purposes
        current_word = self._get_current_word(text, cursor_pos)

        # Get suggestions using the new SQL completion engine
        suggestions = self._get_autocomplete_suggestions(text, cursor_pos)

        if suggestions:
            self._show_autocomplete(suggestions, current_word)
        else:
            self._hide_autocomplete()

    def on_descendant_blur(self: AppProtocol, event: Any) -> None:
        """Hide autocomplete when query input loses focus."""
        # Check if the blur is from the query input
        if hasattr(event, "widget") and getattr(event.widget, "id", None) == "query-input":
            self._hide_autocomplete()

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
        elif event.key == "tab":
            if self.vim_mode == VimMode.INSERT and dropdown.filtered_items:
                self._apply_autocomplete()
                event.prevent_default()
                event.stop()
        elif event.key == "escape":
            self._hide_autocomplete()
            event.prevent_default()
            event.stop()

    def _load_schema_cache(self: AppProtocol) -> None:
        """Load database schema for autocomplete asynchronously."""
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

        # Start schema indexing spinner
        self._start_schema_spinner()

        # Run schema loading in background thread
        self._schema_worker = self.run_worker(
            self._load_schema_cache_async(),
            name="schema_cache_loading",
            exclusive=True,
        )

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
                db = config.database
                if db and db.lower() not in ("", "master"):
                    databases = [db]
                else:
                    all_dbs = await run_db_call(adapter.get_databases, connection)
                    system_dbs = {"master", "tempdb", "model", "msdb"}
                    databases = [d for d in all_dbs if d.lower() not in system_dbs]
            else:
                databases = [None]

            for database in databases:
                try:
                    # Get tables
                    tables = await run_db_call(adapter.get_tables, connection, database)
                    for schema_name, table_name in tables:
                        display_name = adapter.format_table_name(schema_name, table_name)
                        schema_cache["tables"].append(display_name)
                        table_metadata[display_name.lower()] = (schema_name, table_name, database)
                        table_metadata[table_name.lower()] = (schema_name, table_name, database)
                        if database:
                            full_name = f"{adapter.quote_identifier(database)}.{adapter.quote_identifier(display_name)}"
                            schema_cache["tables"].append(full_name)
                            table_metadata[full_name.lower()] = (schema_name, table_name, database)

                    # Get views
                    views = await run_db_call(adapter.get_views, connection, database)
                    for schema_name, view_name in views:
                        display_name = adapter.format_table_name(schema_name, view_name)
                        schema_cache["views"].append(display_name)
                        table_metadata[display_name.lower()] = (schema_name, view_name, database)
                        table_metadata[view_name.lower()] = (schema_name, view_name, database)
                        if database:
                            full_name = f"{adapter.quote_identifier(database)}.{adapter.quote_identifier(display_name)}"
                            schema_cache["views"].append(full_name)
                            table_metadata[full_name.lower()] = (schema_name, view_name, database)

                    # Get procedures
                    if adapter.supports_stored_procedures:
                        procedures = await run_db_call(adapter.get_procedures, connection, database)
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
