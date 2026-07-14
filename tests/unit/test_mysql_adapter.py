"""Unit tests for MySQL/MariaDB adapter behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter


# DB-API column descriptions are tuples of 7-tuples; we only care about the name
# in the first position, so a single-element tuple is sufficient for tests.
def _make_cursor(result_sets: list[Any]) -> MagicMock:
    """Build a mock cursor that yields the given result sets.

    Each entry is (description, rows). description is a tuple of column
    description tuples (DB-API style) or None to indicate a status-only
    result set. nextset() advances to the next entry and returns True until
    exhausted.
    """
    cursor = MagicMock()
    cursor.description = result_sets[0][0]
    cursor.fetchall.return_value = result_sets[0][1]
    cursor.fetchmany.return_value = result_sets[0][1]

    state: dict[str, Any] = {"index": 0, "sets": result_sets}

    def _advance() -> bool:
        state["index"] += 1
        if state["index"] >= len(state["sets"]):
            return False
        desc, rows = state["sets"][state["index"]]
        cursor.description = desc
        cursor.fetchall.return_value = rows
        cursor.fetchmany.return_value = rows
        return True

    cursor.nextset = MagicMock(side_effect=_advance)
    return cursor


def _desc(*names: str) -> tuple[tuple[str, ...], ...]:
    """Build a DB-API style description tuple from column names."""
    return tuple((name,) for name in names)


def test_execute_query_returns_first_result_set() -> None:
    adapter = MySQLAdapter()
    cursor = _make_cursor([
        (_desc("id", "name"), [(1, "Alice"), (2, "Bob")]),
    ])
    conn = MagicMock()
    conn.cursor.return_value = cursor

    columns, rows, truncated = adapter.execute_query(conn, "SELECT * FROM users")

    assert columns == ["id", "name"]
    assert rows == [(1, "Alice"), (2, "Bob")]
    assert truncated is False


def test_execute_query_skips_status_only_result_sets() -> None:
    """Stored procedures may emit a status-only result set before the data."""
    adapter = MySQLAdapter()
    cursor = _make_cursor([
        (None, []),
        (_desc("id", "name"), [(1, "Alice")]),
    ])
    conn = MagicMock()
    conn.cursor.return_value = cursor

    columns, rows, _ = adapter.execute_query(conn, "CALL getalltheme()")

    assert columns == ["id", "name"]
    assert rows == [(1, "Alice")]


def test_execute_query_consumes_remaining_result_sets() -> None:
    """Remaining result sets should be consumed to keep the connection clean."""
    adapter = MySQLAdapter()
    cursor = _make_cursor([
        (_desc("id", "name"), [(1, "Alice")]),
        (_desc("code"), [("a",), ("b",)]),
        (None, []),
    ])
    conn = MagicMock()
    conn.cursor.return_value = cursor

    adapter.execute_query(conn, "CALL getalltheme()")

    # nextset should have been called until all result sets are consumed
    assert cursor.nextset.call_count == 3


def test_execute_query_with_max_rows_truncates() -> None:
    adapter = MySQLAdapter()
    cursor = _make_cursor([
        (_desc("id"), [(1,), (2,), (3,)]),
    ])
    cursor.fetchmany.side_effect = lambda size: [(1,), (2,), (3,)][:size]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    columns, rows, truncated = adapter.execute_query(conn, "SELECT * FROM users", max_rows=2)

    assert columns == ["id"]
    assert rows == [(1,), (2,)]
    assert truncated is True
    cursor.fetchmany.assert_called_once_with(3)


def test_execute_query_no_result_set_returns_empty() -> None:
    adapter = MySQLAdapter()
    cursor = _make_cursor([
        (None, []),
    ])
    conn = MagicMock()
    conn.cursor.return_value = cursor

    columns, rows, truncated = adapter.execute_query(conn, "CALL update_only()")

    assert columns == []
    assert rows == []
    assert truncated is False
