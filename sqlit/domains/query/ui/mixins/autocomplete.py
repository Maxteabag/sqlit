"""Autocomplete mixin for SSMSTUI."""

from __future__ import annotations

from typing import Any

from textual.widgets import TextArea

from sqlit.shared.ui.protocols import AutocompleteMixinHost
from sqlit.shared.ui.spinner import Spinner

from .autocomplete_schema import AutocompleteSchemaMixin
from .autocomplete_suggestions import AutocompleteSuggestionsMixin


class AutocompleteMixin(AutocompleteSchemaMixin, AutocompleteSuggestionsMixin):
    """Mixin providing SQL autocomplete functionality."""

    _schema_worker: Any | None = None
    _schema_spinner: Spinner | None = None
    _schema_cache: dict[str, Any] = {}
    _table_metadata: dict[str, tuple[str, str, str | None]] = {}
    _autocomplete_debounce_timer: Any | None = None
    _schema_pending_dbs: list[str | None] = []
    _schema_total_jobs: int = 0
    _schema_completed_jobs: int = 0
    _schema_scheduler: Any = None
    _text_just_changed: bool = False
    # Shared cache for raw DB objects - used by both tree and autocomplete
    # Structure: {db_name: {"tables": [(schema, name), ...], "views": [...], "procedures": [...]}}
    _db_object_cache: dict[str, dict[str, list[Any]]] = {}

    def _show_autocomplete(self: AutocompleteMixinHost, suggestions: list[str], filter_text: str) -> None:
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

    def _hide_autocomplete(self: AutocompleteMixinHost) -> None:
        """Hide the autocomplete dropdown."""
        try:
            self.autocomplete_dropdown.hide()
        except Exception:
            pass  # Widget not mounted yet
        self._autocomplete_visible = False

    def _apply_autocomplete(self: AutocompleteMixinHost) -> None:
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

    def on_text_area_changed(self: AutocompleteMixinHost, event: TextArea.Changed) -> None:
        """Handle text changes in the query editor for autocomplete."""
        from sqlit.core.vim import VimMode
        from sqlit.domains.shell.app.idle_scheduler import on_user_activity

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

    def _trigger_autocomplete(self: AutocompleteMixinHost, text_area: TextArea) -> None:
        """Actually trigger autocomplete after debounce delay."""
        from sqlit.domains.shell.app.idle_scheduler import Priority, get_idle_scheduler

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

    def on_descendant_blur(self: AutocompleteMixinHost, event: Any) -> None:
        """Handle blur events - don't hide autocomplete on window focus loss."""
        # Only hide if focus moves to another widget within the app (not window blur)
        # We want autocomplete to stay visible when user moves mouse to another window
        pass

    def action_autocomplete_next(self: AutocompleteMixinHost) -> None:
        """Move to next autocomplete suggestion."""
        if self._autocomplete_visible:
            self.autocomplete_dropdown.move_selection(1)

    def action_autocomplete_prev(self: AutocompleteMixinHost) -> None:
        """Move to previous autocomplete suggestion."""
        if self._autocomplete_visible:
            self.autocomplete_dropdown.move_selection(-1)

    def action_autocomplete_close(self: AutocompleteMixinHost) -> None:
        """Close autocomplete dropdown without exiting insert mode."""
        self._hide_autocomplete()

    def action_autocomplete_accept(self: AutocompleteMixinHost) -> None:
        """Accept the current autocomplete suggestion."""
        if self._autocomplete_visible:
            self._apply_autocomplete()

    def on_text_area_selection_changed(self: AutocompleteMixinHost, event: Any) -> None:
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

    def on_key(self: AutocompleteMixinHost, event: Any) -> None:
        """Handle key events for autocomplete navigation."""
        from sqlit.core.vim import VimMode
        from sqlit.domains.shell.app.idle_scheduler import on_user_activity

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
