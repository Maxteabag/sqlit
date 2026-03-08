"""Utility helpers for widget effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.widget import Widget


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
