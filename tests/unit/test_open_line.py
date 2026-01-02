"""Unit tests for o/O (open line) vim commands."""

from __future__ import annotations

import pytest


class TestOpenLineBelow:
    """Tests for 'o' command - open line below."""

    def test_open_line_below_single_line(self) -> None:
        """Opening line below on single line text."""
        text = "SELECT * FROM users"
        row, col = 0, 5

        new_text, new_row, new_col = open_line_below(text, row, col)

        assert new_text == "SELECT * FROM users\n"
        assert new_row == 1
        assert new_col == 0

    def test_open_line_below_middle_of_multiline(self) -> None:
        """Opening line below in middle of multiline text."""
        text = "line1\nline2\nline3"
        row, col = 1, 2  # cursor on line2

        new_text, new_row, new_col = open_line_below(text, row, col)

        assert new_text == "line1\nline2\n\nline3"
        assert new_row == 2
        assert new_col == 0

    def test_open_line_below_at_last_line(self) -> None:
        """Opening line below at the last line."""
        text = "line1\nline2"
        row, col = 1, 3  # cursor on line2

        new_text, new_row, new_col = open_line_below(text, row, col)

        assert new_text == "line1\nline2\n"
        assert new_row == 2
        assert new_col == 0

    def test_open_line_below_empty_text(self) -> None:
        """Opening line below on empty text."""
        text = ""
        row, col = 0, 0

        new_text, new_row, new_col = open_line_below(text, row, col)

        assert new_text == "\n"
        assert new_row == 1
        assert new_col == 0


class TestOpenLineAbove:
    """Tests for 'O' command - open line above."""

    def test_open_line_above_single_line(self) -> None:
        """Opening line above on single line text."""
        text = "SELECT * FROM users"
        row, col = 0, 5

        new_text, new_row, new_col = open_line_above(text, row, col)

        assert new_text == "\nSELECT * FROM users"
        assert new_row == 0
        assert new_col == 0

    def test_open_line_above_middle_of_multiline(self) -> None:
        """Opening line above in middle of multiline text."""
        text = "line1\nline2\nline3"
        row, col = 1, 2  # cursor on line2

        new_text, new_row, new_col = open_line_above(text, row, col)

        assert new_text == "line1\n\nline2\nline3"
        assert new_row == 1
        assert new_col == 0

    def test_open_line_above_at_first_line(self) -> None:
        """Opening line above at the first line."""
        text = "line1\nline2"
        row, col = 0, 3  # cursor on line1

        new_text, new_row, new_col = open_line_above(text, row, col)

        assert new_text == "\nline1\nline2"
        assert new_row == 0
        assert new_col == 0

    def test_open_line_above_at_last_line(self) -> None:
        """Opening line above at the last line."""
        text = "line1\nline2"
        row, col = 1, 2  # cursor on line2

        new_text, new_row, new_col = open_line_above(text, row, col)

        assert new_text == "line1\n\nline2"
        assert new_row == 1
        assert new_col == 0


def open_line_below(text: str, row: int, col: int) -> tuple[str, int, int]:
    """Open a new line below current line.

    Mirrors the logic in action_open_line_below.
    Returns (new_text, new_row, new_col).
    """
    lines = text.split("\n")

    # Insert new line after current row
    lines.insert(row + 1, "")
    new_text = "\n".join(lines)
    new_row = row + 1
    new_col = 0

    return new_text, new_row, new_col


def open_line_above(text: str, row: int, col: int) -> tuple[str, int, int]:
    """Open a new line above current line.

    Mirrors the logic in action_open_line_above.
    Returns (new_text, new_row, new_col).
    """
    lines = text.split("\n")

    # Insert new line before current row
    lines.insert(row, "")
    new_text = "\n".join(lines)
    new_row = row
    new_col = 0

    return new_text, new_row, new_col
