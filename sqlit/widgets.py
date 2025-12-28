"""Custom widgets for sqlit."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.strip import Strip
from textual.widgets import Static, TextArea
from textual_fastdatatable import DataTable as FastDataTable

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.events import Key
    from textual.widget import Widget


class QueryTextArea(TextArea):
    """TextArea that defers Enter key to app when autocomplete is visible."""

    def _on_key(self, event: Key) -> None:
        """Intercept Enter key when autocomplete is visible."""
        if event.key == "enter":
            # Check if autocomplete is visible on the app
            app = self.app
            if getattr(app, "_autocomplete_visible", False):
                # Hide autocomplete and suppress re-triggering from the newline
                if hasattr(app, "_hide_autocomplete"):
                    app._hide_autocomplete()
                app._suppress_autocomplete_on_newline = True
        # For all other keys, use default TextArea behavior
        super()._on_key(event)


class SqlitDataTable(FastDataTable):
    """FastDataTable with correct header behavior when show_header is False."""

    def render_line(self, y: int) -> Strip:
        width, _ = self.size
        scroll_x, scroll_y = self.scroll_offset

        fixed_rows_height = self.fixed_rows
        if self.show_header:
            fixed_rows_height += self.header_height

        if y >= fixed_rows_height:
            y += scroll_y

        if not self.show_header:
            # FastDataTable still renders the header row at y=0; offset by 1 when hidden.
            y += 1

        return self._render_line(y, scroll_x, scroll_x + width, self.rich_style)


class ResultsTableContainer(Container):
    """A focusable container for the results DataTable.

    This container holds focus when its child DataTable is replaced,
    preventing focus from jumping to another widget during table updates.
    Key events are forwarded to the child DataTable.
    """

    can_focus = True

    def on_key(self, event: Key) -> None:
        """Forward key events to the child DataTable."""
        # Find the DataTable child
        try:
            table = self.query_one(SqlitDataTable)
            # Let the table handle navigation keys
            if event.key in ("up", "down", "left", "right", "pageup", "pagedown", "home", "end"):
                # Simulate the key on the table
                table.post_message(event)
                event.stop()
        except Exception:
            pass

    def on_focus(self, event: Any) -> None:
        """When container gets focus, style it as active."""
        self.add_class("container-focused")

    def on_blur(self, event: Any) -> None:
        """When container loses focus, remove active styling."""
        self.remove_class("container-focused")


def flash_widget(
    widget: Widget,
    css_class: str = "flash",
    duration: float = 0.15,
    on_complete: Callable[[], None] | None = None,
) -> None:
    """Flash a widget by temporarily adding a CSS class.

    Args:
        widget: The widget to flash.
        css_class: The CSS class to add (default: "flash").
        duration: How long to show the flash in seconds (default: 0.15).
        on_complete: Optional callback to run after flash completes.
    """
    widget.add_class(css_class)

    def cleanup() -> None:
        widget.remove_class(css_class)
        if on_complete:
            on_complete()

    widget.set_timer(duration, cleanup)


class VimMode(Enum):
    """Vim editing modes."""

    NORMAL = "NORMAL"
    INSERT = "INSERT"


class KeyBinding:
    """Represents a single key binding for display."""

    def __init__(self, key: str, label: str, action: str, disabled: bool = False):
        self.key = key
        self.label = label
        self.action = action
        self.disabled = disabled


class ContextFooter(Horizontal):
    """A context-aware footer that shows relevant keybindings."""

    DEFAULT_CSS = """
    ContextFooter {
        height: 1;
        dock: bottom;
        background: $footer-background;
        color: $footer-key-foreground;
        padding: 0 1;
    }

    #footer-left {
        width: 1fr;
        height: 1;
    }

    #footer-right {
        width: auto;
        height: 1;
        text-align: right;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._left_bindings: list[KeyBinding] = []
        self._right_bindings: list[KeyBinding] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="footer-left")
        yield Static("", id="footer-right")

    def set_bindings(self, left: list[KeyBinding], right: list[KeyBinding]) -> None:
        """Update the displayed bindings."""
        self._left_bindings = left
        self._right_bindings = right
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild the footer content with left and right sections."""

        def format_binding(binding: KeyBinding) -> str:
            if binding.disabled:
                return f"[$text-muted strike]{binding.label}: {binding.key}[/]"
            return f"{binding.label}: [bold]{binding.key}[/]"

        left = "  ".join(format_binding(b) for b in self._left_bindings)
        right = "  ".join(format_binding(b) for b in self._right_bindings)
        self.query_one("#footer-left", Static).update(left)
        self.query_one("#footer-right", Static).update(right)


class Dialog(Container):
    """A styled modal dialog container with optional border title/subtitle.

    The shortcuts parameter accepts a list of (action, key) tuples that will be
    formatted consistently as "action: [bold]key[/]" in the subtitle.
    """

    DEFAULT_CSS = """
    Dialog {
        border: round $primary;
        background: $surface;
        color: $primary;
        padding: 1;
        height: auto;
        max-height: 85%;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-visibility: hidden;

        border-title-align: left;
        border-title-color: $primary;
        border-title-background: $surface;
        border-title-style: bold;

        border-subtitle-align: right;
        border-subtitle-color: $primary;
        border-subtitle-background: $surface;
        border-subtitle-style: none;
    }
    """

    def __init__(
        self,
        title: str | None = None,
        shortcuts: list[tuple[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the dialog.

        Args:
            title: The dialog title (shown in border title).
            shortcuts: List of (action, key) tuples for the subtitle.
                       Example: [("Save", "^S"), ("Cancel", "<esc>")]
        """
        super().__init__(**kwargs)
        if title is not None:
            self.border_title = title
        if shortcuts:
            # Use a visible separator. Border subtitles can collapse regular spaces,
            # so we use non-breaking spaces to preserve padding around the separator.
            def format_key(key: str) -> str:
                # Wrap key in <> if not already wrapped
                if key.startswith("<") and key.endswith(">"):
                    return key
                return f"<{key}>"

            subtitle = "\u00a0·\u00a0".join(
                f"{action}: [bold]{format_key(key)}[/]" for action, key in shortcuts
            )
            self.border_subtitle = subtitle


class FilterInput(Static):
    """Filter input widget for search/filter functionality."""

    DEFAULT_CSS = """
    FilterInput {
        width: 100%;
        height: 1;
        background: $surface;
        display: none;
        padding: 0 1;
    }

    FilterInput.visible {
        display: block;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("", *args, **kwargs)
        self.filter_text: str = ""
        self.match_count: int = 0
        self.total_count: int = 0

    def set_filter(self, text: str, match_count: int = 0, total_count: int = 0, truncated: bool = False) -> None:
        """Set the filter text and match count."""
        self.filter_text = text
        self.match_count = match_count
        self.total_count = total_count
        self.truncated = truncated
        self._rebuild()

    def clear(self) -> None:
        """Clear the filter."""
        self.filter_text = ""
        self.match_count = 0
        self.total_count = 0
        self.truncated = False
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild the display."""
        if not self.filter_text:
            self.update("[dim]/[/] ")
        else:
            # Show "5000+" if results were truncated
            count_display = f"{self.match_count}+" if self.truncated else str(self.match_count)
            count_text = f"[dim]{count_display}/{self.total_count}[/]"
            self.update(f"[dim]/[/] {self.filter_text} {count_text}")

    def show(self) -> None:
        """Show the filter input."""
        self.add_class("visible")
        self._rebuild()

    def hide(self) -> None:
        """Hide the filter input."""
        self.remove_class("visible")

    @property
    def is_visible(self) -> bool:
        """Check if filter is visible."""
        return "visible" in self.classes


# Aliases for filter inputs in different contexts
TreeFilterInput = FilterInput
ResultsFilterInput = FilterInput


class AutocompleteDropdown(VerticalScroll):
    """Dropdown widget for SQL autocomplete suggestions with scrollbar."""

    DEFAULT_CSS = """
    AutocompleteDropdown {
        layer: autocomplete;
        width: auto;
        min-width: 25;
        max-width: 80;
        height: auto;
        max-height: 12;
        background: $surface;
        border: round $border;
        padding: 0;
        display: none;
        scrollbar-size: 1 1;
        constrain: inside inside;
    }

    AutocompleteDropdown.visible {
        display: block;
    }

    AutocompleteDropdown .autocomplete-item {
        width: 100%;
        height: 1;
        padding: 0 1;
    }

    AutocompleteDropdown .autocomplete-item.selected {
        background: $primary;
        color: $background;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.items: list[str] = []
        self.filtered_items: list[str] = []
        self.selected_index: int = 0
        self.filter_text: str = ""

    def set_items(self, items: list[str], filter_text: str = "") -> None:
        """Set the autocomplete items and filter."""
        self.items = items
        self.filter_text = filter_text.lower()

        if self.filter_text:
            self.filtered_items = [item for item in items if item.lower().startswith(self.filter_text)]
        else:
            self.filtered_items = items[:50]  # Show more items with scrolling

        self.selected_index = 0
        self._rebuild()
        # Reset scroll to top
        self.scroll_to(y=0, animate=False)

    def move_selection(self, delta: int) -> None:
        """Move selection up or down."""
        if not self.filtered_items:
            return
        old_index = self.selected_index
        self.selected_index = (self.selected_index + delta) % len(self.filtered_items)
        self._update_selection(old_index, self.selected_index)
        self._scroll_to_selected()

    def _update_selection(self, old_index: int, new_index: int) -> None:
        """Update selection by toggling CSS classes (fast)."""
        children = list(self.children)
        if old_index < len(children):
            children[old_index].remove_class("selected")
        if new_index < len(children):
            children[new_index].add_class("selected")

    def _scroll_to_selected(self) -> None:
        """Scroll to ensure selected item is visible."""
        if not self.filtered_items:
            return
        # Each item is 1 line high, scroll to show selected
        self.scroll_to(y=max(0, self.selected_index - 5), animate=False)

    def get_selected(self) -> str | None:
        """Get the currently selected item."""
        if self.filtered_items and 0 <= self.selected_index < len(self.filtered_items):
            return self.filtered_items[self.selected_index]
        return None

    def _rebuild(self) -> None:
        """Rebuild the dropdown content (only called when items change)."""
        # Remove all existing children
        self.remove_children()

        if not self.filtered_items:
            self.mount(Static("[dim]No matches[/]"))
            return

        # Create item widgets
        for i, item in enumerate(self.filtered_items):
            label = Static(f" {item} ", classes="autocomplete-item")
            if i == self.selected_index:
                label.add_class("selected")
            self.mount(label)

    def show(self) -> None:
        """Show the dropdown."""
        self.add_class("visible")

    def hide(self) -> None:
        """Hide the dropdown and reset selection."""
        self.remove_class("visible")
        self.selected_index = 0

    @property
    def is_visible(self) -> bool:
        """Check if dropdown is visible."""
        return "visible" in self.classes
