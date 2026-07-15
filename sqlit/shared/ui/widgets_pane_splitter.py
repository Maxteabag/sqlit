"""Draggable pane splitter widget for resizing sidebar and query/results panes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widget import Widget

if TYPE_CHECKING:
    from textual import events
    from textual.app import RenderResult


class PaneSplitter(Widget):
    """A thin draggable divider that resizes an adjacent pane on mouse drag.

    A ``vertical`` splitter resizes the explorer sidebar width; a ``horizontal``
    splitter resizes the query/results split height. The host app supplies the
    ``_resize_sidebar`` / ``_resize_split`` / ``_persist_pane_sizes`` methods.
    """

    DEFAULT_CSS = """
    PaneSplitter {
        background: $panel-lighten-1;
    }

    PaneSplitter:hover {
        background: $accent;
    }

    PaneSplitter.-vertical {
        width: 1;
        height: 1fr;
    }

    PaneSplitter.-horizontal {
        height: 1;
        width: 1fr;
    }
    """

    def __init__(self, *, orientation: str, id: str | None = None) -> None:
        super().__init__(id=id)
        self.orientation = orientation
        self._dragging = False
        self.add_class("-vertical" if orientation == "vertical" else "-horizontal")

    def render(self) -> RenderResult:
        # Blank: the divider is a solid bar drawn by its CSS background. Without
        # this override, Textual's default Widget.render() shows the widget's
        # CSS identifier as placeholder text.
        return Text("")

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.capture_mouse()
        self._dragging = True
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging:
            return
        if self.orientation == "vertical":
            resize = getattr(self.app, "_resize_sidebar", None)
            if callable(resize):
                resize(int(event.delta_x), persist=False)
        else:
            resize = getattr(self.app, "_resize_split", None)
            if callable(resize):
                resize(int(event.delta_y), persist=False)
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.release_mouse()
            persist = getattr(self.app, "_persist_pane_sizes", None)
            if callable(persist):
                persist()
            event.stop()
