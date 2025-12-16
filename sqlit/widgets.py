"""Custom widgets for sqlit."""

from __future__ import annotations

from enum import Enum
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static


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
        background: $surface;
        color: $primary;
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
        border: solid $primary;
        background: $surface;
        padding: 1;
        height: auto;
        max-height: 85%;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-visibility: hidden;

        border-title-align: left;
        border-title-color: $text-muted;
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
            subtitle = "\u00a0·\u00a0".join(f"{action}: [bold]{key}[/]" for action, key in shortcuts)
            self.border_subtitle = subtitle


class AutocompleteDropdown(Static):
    """Dropdown widget for SQL autocomplete suggestions."""

    DEFAULT_CSS = """
    AutocompleteDropdown {
        layer: autocomplete;
        width: auto;
        min-width: 20;
        max-width: 50;
        height: auto;
        max-height: 10;
        background: $surface;
        border: solid $primary;
        padding: 0;
        display: none;
    }

    AutocompleteDropdown.visible {
        display: block;
    }

    AutocompleteDropdown .autocomplete-item {
        padding: 0 1;
    }

    AutocompleteDropdown .autocomplete-item.selected {
        background: $primary;
        color: $background;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("", *args, **kwargs)
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
            self.filtered_items = items[:20]

        self.selected_index = 0
        self._rebuild()

    def move_selection(self, delta: int) -> None:
        """Move selection up or down."""
        if not self.filtered_items:
            return
        self.selected_index = (self.selected_index + delta) % len(self.filtered_items)
        self._rebuild()

    def get_selected(self) -> str | None:
        """Get the currently selected item."""
        if self.filtered_items and 0 <= self.selected_index < len(self.filtered_items):
            return self.filtered_items[self.selected_index]
        return None

    def _rebuild(self) -> None:
        """Rebuild the dropdown content."""
        if not self.filtered_items:
            self.update("[dim]No matches[/]")
            return

        lines = []
        for i, item in enumerate(self.filtered_items[:10]):
            if i == self.selected_index:
                lines.append(f"[reverse] {item} [/]")
            else:
                lines.append(f" {item} ")
        self.update("\n".join(lines))

    def show(self) -> None:
        """Show the dropdown."""
        self.add_class("visible")

    def hide(self) -> None:
        """Hide the dropdown."""
        self.remove_class("visible")

    @property
    def is_visible(self) -> bool:
        """Check if dropdown is visible."""
        return "visible" in self.classes
