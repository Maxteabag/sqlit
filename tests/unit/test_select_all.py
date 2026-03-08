"""Test for select_all functionality.

This test verifies that select_all_range returns correct coordinates.
The actual UI integration test (action_select_all with Textual Selection)
requires textual to be installed and is tested via integration tests.

Fix applied: action_select_all now uses textual.widgets.text_area.Selection
instead of a tuple, as Textual's TextArea requires a Selection object.
"""

from __future__ import annotations

from sqlit.domains.query.editing.clipboard import select_all_range


def test_select_all_range_basic() -> None:
    """Test select_all_range returns correct range."""
    text = "hello\nworld"
    start_row, start_col, end_row, end_col = select_all_range(text)

    assert start_row == 0
    assert start_col == 0
    assert end_row == 1
    assert end_col == 5  # len("world")


def test_select_all_range_single_line() -> None:
    """Test select_all_range with single line."""
    text = "hello"
    start_row, start_col, end_row, end_col = select_all_range(text)

    assert start_row == 0
    assert start_col == 0
    assert end_row == 0
    assert end_col == 5


def test_select_all_range_empty() -> None:
    """Test select_all_range with empty text."""
    text = ""
    start_row, start_col, end_row, end_col = select_all_range(text)

    assert start_row == 0
    assert start_col == 0
    assert end_row == 0
    assert end_col == 0


def test_select_all_range_multiline() -> None:
    """Test select_all_range with multiple lines."""
    text = "line1\nline2\nline3"
    start_row, start_col, end_row, end_col = select_all_range(text)

    assert start_row == 0
    assert start_col == 0
    assert end_row == 2
    assert end_col == 5  # len("line3")
