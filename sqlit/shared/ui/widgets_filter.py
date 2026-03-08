"""Filter widgets for sqlit."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static


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
