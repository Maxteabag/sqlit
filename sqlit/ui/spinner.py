"""Reusable spinner animation utility."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from textual.timer import Timer
    from textual.widget import Widget

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """A reusable spinner animation.

    Usage:
        spinner = Spinner(widget, on_tick=lambda frame: status.update(f"{frame} Loading..."))
        spinner.start()
        # ... do work ...
        spinner.stop()

    Or without callback (for status bar polling):
        spinner = Spinner(widget)
        spinner.start()
        # In status bar: if spinner.running: show(spinner.frame)
        spinner.stop()
    """

    def __init__(
        self,
        widget: Widget,
        on_tick: Callable[[str], None] | None = None,
        fps: float = 12,
    ):
        """Initialize the spinner.

        Args:
            widget: The Textual widget to attach the timer to.
            on_tick: Optional callback called with current spinner frame on each tick.
            fps: Frames per second for animation (default 12).
        """
        self._widget = widget
        self._on_tick = on_tick
        self._fps = fps
        self._index = 0
        self._timer: Timer | None = None
        self._running = False

    @property
    def frame(self) -> str:
        """Get the current spinner frame."""
        return SPINNER_FRAMES[self._index % len(SPINNER_FRAMES)]

    @property
    def running(self) -> bool:
        """Check if the spinner is currently running."""
        return self._running

    def start(self) -> None:
        """Start the spinner animation."""
        self._index = 0
        self._running = True
        if self._timer is not None:
            self._timer.stop()
        self._timer = self._widget.set_interval(1 / self._fps, self._tick)
        # Immediately show first frame
        if self._on_tick:
            self._on_tick(self.frame)

    def stop(self) -> None:
        """Stop the spinner animation."""
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        """Advance to next frame and call callback."""
        self._index = (self._index + 1) % len(SPINNER_FRAMES)
        if self._on_tick:
            self._on_tick(self.frame)
