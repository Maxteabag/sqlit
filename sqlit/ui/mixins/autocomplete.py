"""Autocomplete mixin for SSMSTUI."""

from __future__ import annotations

from typing import Any

from textual.timer import Timer
from textual.widgets import TextArea
from textual.worker import Worker

from ..protocols import AppProtocol

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class AutocompleteMixin:
    """Mixin providing SQL autocomplete functionality."""

    _schema_worker: Worker[Any] | None = None
    _schema_spinner_timer: Timer | None = None
    _schema_cache: dict[str, Any] = {}
    _table_metadata: dict[str, tuple[str, str, str | None]] = {}

    def _get_word_before_cursor(self, text: str, cursor_pos: int) -> tuple[str, str]:
        """Get the current word being typed and the context keyword before it."""
        if cursor_pos <= 0 or cursor_pos > len(text):
            return "", ""

        before_cursor = text[:cursor_pos]

        word_start = cursor_pos
        while word_start > 0 and before_cursor[word_start - 1] not in " \t\n,()[]":
            word_start -= 1
        current_word = before_cursor[word_start:cursor_pos]

        if "." in current_word:
            parts = current_word.rsplit(".", 1)
            table_name = parts[0].strip("[]")
            return parts[1] if len(parts) > 1 else "", f"column:{table_name}"

        context_text = before_cursor[:word_start].upper().strip()

        table_keywords = ["FROM", "JOIN", "INTO", "UPDATE", "TABLE"]
        for kw in table_keywords:
            if context_text.endswith(kw):
                return current_word, "table"

        if context_text.endswith("EXEC") or context_text.endswith("EXECUTE"):
            return current_word, "procedure"

        if context_text.endswith("SELECT") or context_text.endswith(","):
            return current_word, "column_or_table"

        return current_word, ""

    def _get_autocomplete_suggestions(self: AppProtocol, word: str, context: str) -> list[str]:
        """Get autocomplete suggestions based on context."""
        suggestions = []

        if context == "table":
            suggestions = self._schema_cache["tables"] + self._schema_cache["views"]
        elif context == "procedure":
            suggestions = self._schema_cache["procedures"]
        elif context.startswith("column:"):
            table_name = context.split(":", 1)[1].lower()
            if table_name not in self._schema_cache["columns"]:
                self._load_columns_for_table(table_name)
            suggestions = self._schema_cache["columns"].get(table_name, [])
        elif context == "column_or_table":
            all_columns = []
            for cols in self._schema_cache["columns"].values():
                all_columns.extend(cols)
            suggestions = list(set(all_columns)) + self._schema_cache["tables"]

        if word:
            word_lower = word.lower()
            suggestions = [s for s in suggestions if s.lower().startswith(word_lower)]

        return suggestions[:50]

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
                    columns = adapter.get_columns(connection, actual_table_name, database, schema_name)
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
        self.autocomplete_dropdown.hide()
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

        word, context = self._get_word_before_cursor(text, cursor_pos)

        if context:
            is_column_context = context.startswith("column:")
            if is_column_context or len(word) >= 1:
                suggestions = self._get_autocomplete_suggestions(word, context)
                if suggestions:
                    self._show_autocomplete(suggestions, word)
                else:
                    self._hide_autocomplete()
            else:
                self._hide_autocomplete()
        else:
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
        """Load database schema asynchronously in a worker thread.

        Only loads tables, views, and procedures. Columns are loaded lazily.
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

        try:
            # Get database list in thread
            databases: list[str | None]
            if adapter.supports_multiple_databases:
                db = config.database
                if db and db.lower() not in ("", "master"):
                    databases = [db]
                else:
                    all_dbs = await asyncio.to_thread(adapter.get_databases, connection)
                    system_dbs = {"master", "tempdb", "model", "msdb"}
                    databases = [d for d in all_dbs if d.lower() not in system_dbs]
            else:
                databases = [None]

            for database in databases:
                try:
                    # Get tables in thread (NO columns - lazy loaded)
                    tables = await asyncio.to_thread(adapter.get_tables, connection, database)
                    for schema_name, table_name in tables:
                        display_name = adapter.format_table_name(schema_name, table_name)
                        schema_cache["tables"].append(display_name)
                        # Store metadata for lazy column loading
                        table_metadata[display_name.lower()] = (schema_name, table_name, database)
                        table_metadata[table_name.lower()] = (schema_name, table_name, database)
                        if database:
                            full_name = f"{adapter.quote_identifier(database)}.{adapter.quote_identifier(display_name)}"
                            schema_cache["tables"].append(full_name)
                            table_metadata[full_name.lower()] = (schema_name, table_name, database)

                    # Get views in thread (NO columns - lazy loaded)
                    views = await asyncio.to_thread(adapter.get_views, connection, database)
                    for schema_name, view_name in views:
                        display_name = adapter.format_table_name(schema_name, view_name)
                        schema_cache["views"].append(display_name)
                        # Store metadata for lazy column loading
                        table_metadata[display_name.lower()] = (schema_name, view_name, database)
                        table_metadata[view_name.lower()] = (schema_name, view_name, database)
                        if database:
                            full_name = f"{adapter.quote_identifier(database)}.{adapter.quote_identifier(display_name)}"
                            schema_cache["views"].append(full_name)
                            table_metadata[full_name.lower()] = (schema_name, view_name, database)

                    if adapter.supports_stored_procedures:
                        procedures = await asyncio.to_thread(adapter.get_procedures, connection, database)
                        schema_cache["procedures"].extend(procedures)

                except Exception:
                    pass

            # Deduplicate
            schema_cache["tables"] = list(dict.fromkeys(schema_cache["tables"]))
            schema_cache["views"] = list(dict.fromkeys(schema_cache["views"]))
            schema_cache["procedures"] = list(dict.fromkeys(schema_cache["procedures"]))

            # Update cache (we're back on main thread after await)
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
