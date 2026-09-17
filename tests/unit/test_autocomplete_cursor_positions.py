"""Tests for cursor position conversion used by autocomplete."""

import pytest

from sqlit.domains.query.ui.mixins.autocomplete import AutocompleteMixin


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r"])
def test_cursor_location_round_trip_for_line_endings(separator: str) -> None:
    """Cursor conversion supports all common pasted-text line endings."""
    lines = ["SELECT", "    column_name", "FROM users"]
    text = separator.join(lines)
    location = (2, 4)
    expected_offset = len(lines[0]) + len(separator) + len(lines[1]) + len(separator) + location[1]

    offset = AutocompleteMixin._location_to_offset(None, text, location)

    assert offset == expected_offset
    assert AutocompleteMixin._offset_to_location(None, text, offset) == location


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r"])
def test_offset_to_location_after_trailing_line_ending(separator: str) -> None:
    """An offset after a trailing line ending maps to the next empty row."""
    text = f"SELECT{separator}"

    assert AutocompleteMixin._offset_to_location(None, text, len(text)) == (1, 0)


def test_offset_to_location_for_empty_text() -> None:
    """An empty editor starts at the first row and column."""
    assert AutocompleteMixin._offset_to_location(None, "", 0) == (0, 0)
