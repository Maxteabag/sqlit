"""ER diagram modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.shared.ui.widgets import Dialog


class DiagramScreen(ModalScreen):
    """Full-screen modal displaying an ER diagram."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=False, priority=True),
        Binding("q", "close", "Close", show=False),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("h", "scroll_left", "Left", show=False),
        Binding("l", "scroll_right", "Right", show=False),
        Binding("down", "scroll_down", "Down", show=False),
        Binding("up", "scroll_up", "Up", show=False),
        Binding("left", "scroll_left", "Left", show=False),
        Binding("right", "scroll_right", "Right", show=False),
        Binding("ctrl+d", "page_down", "Page Down", show=False),
        Binding("ctrl+u", "page_up", "Page Up", show=False),
        Binding("g", "scroll_home", "Top", show=False),
        Binding("G", "scroll_end", "Bottom", show=False),
    ]

    CSS = """
    DiagramScreen {
        align: center middle;
        background: $background 80%;
    }

    #diagram-dialog {
        width: 95%;
        height: 90%;
        max-width: 200;
    }

    #diagram-scroll {
        height: 1fr;
        overflow: auto;
    }

    #diagram-content {
        width: auto;
        min-width: 100%;
        color: $text;
    }
    """

    def __init__(self, diagram_text: str, title: str = "ER Diagram") -> None:
        super().__init__()
        self._diagram_text = diagram_text
        self._title = title

    def compose(self) -> ComposeResult:
        shortcuts = [("Close", "q"), ("Scroll", "hjkl")]
        with Dialog(id="diagram-dialog", title=self._title, shortcuts=shortcuts):
            with VerticalScroll(id="diagram-scroll"):
                yield Static(self._diagram_text, id="diagram-content")

    def on_mount(self) -> None:
        self.query_one("#diagram-scroll").focus()

    def action_close(self) -> None:
        self.dismiss()

    def action_scroll_down(self) -> None:
        self.query_one("#diagram-scroll").scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#diagram-scroll").scroll_up()

    def action_scroll_left(self) -> None:
        self.query_one("#diagram-scroll").scroll_left()

    def action_scroll_right(self) -> None:
        self.query_one("#diagram-scroll").scroll_right()

    def action_page_down(self) -> None:
        scroll = self.query_one("#diagram-scroll")
        scroll.scroll_page_down()

    def action_page_up(self) -> None:
        scroll = self.query_one("#diagram-scroll")
        scroll.scroll_page_up()

    def action_scroll_home(self) -> None:
        self.query_one("#diagram-scroll").scroll_home()

    def action_scroll_end(self) -> None:
        self.query_one("#diagram-scroll").scroll_end()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
