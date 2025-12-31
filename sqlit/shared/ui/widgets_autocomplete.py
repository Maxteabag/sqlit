"""Autocomplete widgets for sqlit."""

from __future__ import annotations

from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Static


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
