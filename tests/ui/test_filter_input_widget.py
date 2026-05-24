"""Tests for the shared FilterInput widget.

Regression: typing markup-special characters like '[' into the filter
must not crash the app. FilterInput interpolates the user-entered
filter text into a Rich markup string, so the text has to be escaped
before being passed to Static.update().
"""

from __future__ import annotations

from rich.markup import render as render_markup

from sqlit.shared.ui.widgets_filter import FilterInput


def _rebuild_output(text: str, match_count: int, total: int) -> str:
    """Drive FilterInput._rebuild without instantiating the Textual widget.

    Capture whatever string would be passed to Static.update().
    """
    widget = object.__new__(FilterInput)
    widget.filter_text = text
    widget.match_count = match_count
    widget.total_count = total
    widget.truncated = False

    captured: list[str] = []
    widget.update = captured.append  # type: ignore[method-assign]
    widget._rebuild()
    assert captured, "_rebuild should call update()"
    return captured[-1]


class TestFilterInputMarkup:
    """The rendered markup must be well-formed for any user-typed text."""

    def test_plain_text_renders(self):
        out = _rebuild_output("hello", 2, 10)
        # Must not raise; should contain the user text.
        render_markup(out)
        assert "hello" in out

    def test_open_bracket_does_not_break_markup(self):
        """Regression: typing '[' produced an unbalanced '[/]' close tag."""
        out = _rebuild_output("no[", 0, 3)
        # The crash was here: parsing this string raised MarkupError.
        render_markup(out)

    def test_close_bracket_does_not_break_markup(self):
        out = _rebuild_output("foo]", 0, 3)
        render_markup(out)

    def test_rich_tag_in_filter_text_is_inert(self):
        """A user typing '[red]' should not actually colorize the display."""
        out = _rebuild_output("[red]", 0, 3)
        rendered = render_markup(out)
        # The escaped text should appear as literal characters in the output.
        assert "[red]" in rendered.plain

    def test_empty_filter_text_renders(self):
        out = _rebuild_output("", 0, 0)
        render_markup(out)
