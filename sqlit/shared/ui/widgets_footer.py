"""Footer widgets for sqlit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


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
