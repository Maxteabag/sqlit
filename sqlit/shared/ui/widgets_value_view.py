"""Inline value viewer widget for sqlit."""

from __future__ import annotations

import json
from typing import Any

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static

from sqlit.shared.ui.widgets_json_tree import JSONTreeView, parse_json_value


class InlineValueView(Container):
    """Inline widget for viewing a cell value with tree/syntax toggle for JSON."""

    DEFAULT_CSS = """
    InlineValueView {
        display: none;
        height: 1fr;
        background: $surface;
    }

    InlineValueView.visible {
        display: block;
    }

    InlineValueView #syntax-scroll {
        height: 1fr;
        padding: 1;
    }

    InlineValueView #syntax-scroll.hidden {
        display: none;
    }

    InlineValueView #value-content {
        width: auto;
        height: auto;
    }

    InlineValueView #json-tree {
        height: 1fr;
        padding: 0 1;
    }

    InlineValueView #json-tree.hidden {
        display: none;
    }
    """

    can_focus = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._raw_value: str = ""
        self._column_name: str = ""
        self._is_json: bool = False
        self._tree_mode: bool = True
        self._parsed_json: dict | list | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="syntax-scroll", classes="hidden"):
            yield Static("", id="value-content", markup=False)
        yield JSONTreeView("JSON", id="json-tree", classes="hidden")

    def set_value(self, value: str, column_name: str = "") -> None:
        """Set the value to display."""
        self._raw_value = value
        self._column_name = column_name
        self._is_json, self._parsed_json = parse_json_value(value)
        self._rebuild()

    def toggle_view_mode(self) -> None:
        """Toggle between tree and syntax view."""
        self._tree_mode = not self._tree_mode
        self._rebuild()

    def collapse_all_nodes(self) -> None:
        """Collapse all tree nodes."""
        if self._is_json and self._tree_mode:
            try:
                self.query_one("#json-tree", JSONTreeView).action_collapse_all()
            except Exception:
                pass

    def expand_all_nodes(self) -> None:
        """Expand all tree nodes."""
        if self._is_json and self._tree_mode:
            try:
                self.query_one("#json-tree", JSONTreeView).action_expand_all()
            except Exception:
                pass

    def _rebuild(self) -> None:
        """Rebuild the display based on current mode."""
        try:
            scroll_widget = self.query_one("#syntax-scroll", VerticalScroll)
            static_widget = self.query_one("#value-content", Static)
            tree_widget = self.query_one("#json-tree", JSONTreeView)

            if self._is_json and self._tree_mode and self._parsed_json is not None:
                scroll_widget.add_class("hidden")
                tree_widget.remove_class("hidden")

                label = self._column_name or "JSON"
                tree_widget.set_json(self._parsed_json, label)
                tree_widget.focus()
            else:
                tree_widget.add_class("hidden")
                scroll_widget.remove_class("hidden")

                formatted = self._format_syntax_value()
                static_widget.update(formatted)
                scroll_widget.scroll_home(animate=False)
                scroll_widget.focus()
        except Exception:
            pass

    def _format_syntax_value(self) -> str | Syntax:
        """Format value for syntax view."""
        import textwrap

        if self._is_json and self._parsed_json is not None:
            formatted = json.dumps(self._parsed_json, indent=2, ensure_ascii=False)
            return Syntax(formatted, "json", theme="ansi_dark", word_wrap=True)

        wrap_width = max(self.size.width - 4, 20) if self.size.width > 0 else 100
        if len(self._raw_value) > wrap_width and "\n" not in self._raw_value:
            return textwrap.fill(self._raw_value, width=wrap_width)

        return self._raw_value

    def on_resize(self, event: Any) -> None:
        """Re-wrap text when widget is resized."""
        if self.is_visible and not self._tree_mode:
            self._rebuild()

    def show(self) -> None:
        """Show the value view."""
        self._tree_mode = True
        self.add_class("visible")
        if self.parent:
            self.parent.add_class("value-view-active")
        self._rebuild()

    def hide(self) -> None:
        """Hide the value view."""
        self.remove_class("visible")
        if self.parent:
            self.parent.remove_class("value-view-active")

    @property
    def is_visible(self) -> bool:
        """Check if value view is visible."""
        return "visible" in self.classes

    @property
    def value(self) -> str:
        """Get the current raw value (for copying)."""
        return self._raw_value

    def get_cursor_value_json(self) -> str | None:
        """Get the current tree node's value as JSON string."""
        if not self._is_json or not self._tree_mode:
            return None
        try:
            tree = self.query_one("#json-tree", JSONTreeView)
            return tree.get_cursor_value_json()
        except Exception:
            return None

    def get_cursor_field_json(self) -> str | None:
        """Get the current tree node as 'key': value JSON string."""
        if not self._is_json or not self._tree_mode:
            return None
        try:
            tree = self.query_one("#json-tree", JSONTreeView)
            return tree.get_cursor_field_json()
        except Exception:
            return None

    def get_tree_widget(self) -> JSONTreeView | None:
        """Get the JSON tree widget for flashing."""
        if not self._is_json or not self._tree_mode:
            return None
        try:
            return self.query_one("#json-tree", JSONTreeView)
        except Exception:
            return None
