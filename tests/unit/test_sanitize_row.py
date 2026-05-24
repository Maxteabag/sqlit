"""Unit tests for row sanitization in CursorBasedAdapter."""

from __future__ import annotations

from sqlit.domains.connections.providers.adapters.base import _sanitize_cell, _sanitize_row


def test_sanitize_cell_converts_memoryview_to_bytes() -> None:
    mv = memoryview(b"\xde\xad\xbe\xef")
    result = _sanitize_cell(mv)
    assert result == b"\xde\xad\xbe\xef"
    assert isinstance(result, bytes)


def test_sanitize_cell_passes_through_other_types() -> None:
    assert _sanitize_cell(42) == 42
    assert _sanitize_cell("hello") == "hello"
    assert _sanitize_cell(None) is None
    assert _sanitize_cell(3.14) == 3.14


def test_sanitize_row_converts_memoryview_in_tuple() -> None:
    row = (1, "row1", memoryview(b"\xca\xfe\xba\xbe"))
    result = _sanitize_row(row)
    assert result == (1, "row1", b"\xca\xfe\xba\xbe")
    assert isinstance(result[2], bytes)


def test_sanitize_row_without_memoryview_unchanged() -> None:
    row = (1, "text", None, 3.14)
    result = _sanitize_row(row)
    assert result == (1, "text", None, 3.14)
