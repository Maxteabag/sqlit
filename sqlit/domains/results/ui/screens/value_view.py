"""Value view screen for displaying cell contents."""

from __future__ import annotations

import json

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.shared.ui.widgets import Dialog
from sqlit.shared.ui.widgets_json_tree import JSONTreeView, parse_json_value


class ValueViewScreen(ModalScreen):
    """Modal screen for viewing a single (potentially long) value with tree/syntax toggle."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("y", "copy", "Copy"),
        Binding("t", "toggle_view", "Toggle View"),
        Binding("z", "collapse_all", "Collapse All", show=False),
    ]

    CSS = """
    ValueViewScreen {
        align: center middle;
        background: transparent;
    }

    #value-dialog {
        width: 90;
        height: 70%;
    }

    #value-scroll {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 1;
    }

    #value-scroll.hidden {
        display: none;
    }

    #value-text {
        width: auto;
        height: auto;
    }

    #json-tree-modal {
        height: 1fr;
        border: solid $primary-darken-2;
    }

    #json-tree-modal.hidden {
        display: none;
    }
    """

    def __init__(self, value: str, title: str = "Value"):
        super().__init__()
        self._raw_value = value
        self._title = title
        self._is_json = False
        self._parsed_json: dict | list | None = None
        self._tree_mode = True
        self._is_json, self._parsed_json = parse_json_value(value)

    @property
    def value(self) -> str:
        return self._raw_value

    def _format_syntax_value(self) -> str | Syntax:
        """Format value for syntax view."""
        if self._is_json and self._parsed_json is not None:
            formatted = json.dumps(self._parsed_json, indent=2, ensure_ascii=False)
            return Syntax(formatted, "json", theme="ansi_dark", word_wrap=True)
        return self._raw_value

    def compose(self) -> ComposeResult:
        shortcuts = [("Copy", "y"), ("Close", "<enter>")]
        if self._is_json:
            # Start in tree mode, so show "Syntax View" as what we'd switch to
            shortcuts.insert(0, ("Syntax View", "t"))
            shortcuts.insert(0, ("Collapse", "z"))
        with Dialog(id="value-dialog", title=self._title, shortcuts=shortcuts):
            with VerticalScroll(id="value-scroll", classes="hidden"):
                yield Static(self._format_syntax_value(), id="value-text", markup=False)
            yield JSONTreeView("JSON", id="json-tree-modal", classes="hidden")

    def on_mount(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild the display based on current mode."""
        try:
            scroll_widget = self.query_one("#value-scroll", VerticalScroll)
            tree_widget = self.query_one("#json-tree-modal", JSONTreeView)

            if self._is_json and self._tree_mode and self._parsed_json is not None:
                scroll_widget.add_class("hidden")
                tree_widget.remove_class("hidden")

                tree_widget.set_json(self._parsed_json, self._title)
                tree_widget.focus()
            else:
                tree_widget.add_class("hidden")
                scroll_widget.remove_class("hidden")
                scroll_widget.focus()
        except Exception:
            pass

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)

    def action_toggle_view(self) -> None:
        """Toggle between tree and syntax view."""
        if self._is_json:
            self._tree_mode = not self._tree_mode
            self._rebuild()

    def action_collapse_all(self) -> None:
        """Collapse all tree nodes."""
        if self._is_json and self._tree_mode:
            try:
                self.query_one("#json-tree-modal", JSONTreeView).action_collapse_all()
            except Exception:
                pass

    def action_copy(self) -> None:
        from sqlit.shared.ui.widgets import flash_widget

        copied = getattr(self.app, "_copy_text", None)
        if callable(copied):
            copied(self.value)
            try:
                if self._tree_mode and self._is_json:
                    flash_widget(self.query_one("#json-tree-modal"))
                else:
                    flash_widget(self.query_one("#value-text"))
            except Exception:
                pass
        else:
            self.notify("Copy unavailable", timeout=2)
