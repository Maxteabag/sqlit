"""Tests for pasting text into the query editor."""

import pytest

from sqlit.domains.query.editing import PasteResult, paste_text


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r"])
def test_paste_normalizes_line_endings(separator: str) -> None:
    """Pasted queries use the line endings expected by editor operations."""
    clipboard = separator.join(["SELECT", "FROM users"])

    result = paste_text("", 0, 0, clipboard)

    assert result == PasteResult("SELECT\nFROM users", 1, 10)
