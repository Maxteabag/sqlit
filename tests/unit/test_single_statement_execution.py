"""Tests for single statement execution functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sqlit.domains.query.app.multi_statement import find_statement_at_cursor
from sqlit.domains.query.ui.mixins.query_execution import QueryExecutionMixin


@pytest.mark.parametrize(
    "sql, row, col, expected_stmt",
    [
        ("SELECT * FROM users", 0, 5, "SELECT * FROM users"),
        ("SELECT 1; SELECT 2; SELECT 3", 0, 3, "SELECT 1"),
        ("SELECT 1; SELECT 2; SELECT 3", 0, 12, "SELECT 2"),
        ("SELECT ';'; SELECT 2", 0, 8, "SELECT ';'"),
        ("SELECT 1\n\nSELECT 2", 0, 3, "SELECT 1\n\nSELECT 2"),
        ("SELECT 1;\n\nSELECT 2", 2, 3, "SELECT 2"),
        ("SELECT *\nFROM users;\nSELECT 2", 1, 5, "SELECT *\nFROM users"),
        ("SELECT 1;   SELECT 2", 0, 10, "SELECT 1"),
    ],
)
def test_find_statement_at_cursor_logic(sql: str, row: int, col: int, expected_stmt: str) -> None:
    """Test the logic for finding a statement at the cursor position."""
    result = find_statement_at_cursor(sql, row, col)
    assert result is not None
    assert result[0] == expected_stmt


class MockHost(QueryExecutionMixin):
    """Mock host for testing QueryExecutionMixin actions."""

    def __init__(self) -> None:
        self.current_connection = MagicMock()
        self.current_provider = MagicMock()
        self.query_input = MagicMock()
        # Mock cursor_location as a tuple that can be unpacked
        self.query_input.cursor_location = (0, 0)
        self.notify = MagicMock()
        self.run_worker = MagicMock()
        self.query_executing = False
        self._query_worker = None
        self._query_spinner = None

    def _start_query_spinner(self) -> None:
        self.query_executing = True

    def _run_query_async(self, query: str, keep_insert_mode: bool) -> str:
        return "mock_coro"


def test_action_execute_single_statement_triggers_worker() -> None:
    """Test that action_execute_single_statement correctly triggers a worker."""
    host = MockHost()
    host.query_input.text = "SELECT 1; SELECT 2"
    host.query_input.cursor_location = (0, 12)

    host.action_execute_single_statement()

    host.run_worker.assert_called_once()
    kwargs = host.run_worker.call_args.kwargs
    assert kwargs["name"] == "query_execution_single"
    assert host.query_executing is True


def test_action_execute_single_statement_guards() -> None:
    """Test the guards in action_execute_single_statement."""
    host = MockHost()

    # Test No Connection
    host.current_connection = None
    host.action_execute_single_statement()
    host.notify.assert_called_with("Connect to a server to execute queries", severity="warning")

    # Test Empty Query
    host.current_connection = MagicMock()
    host.query_input.text = ""
    host.action_execute_single_statement()
    host.notify.assert_called_with("No query to execute", severity="warning")


@patch("sqlit.domains.query.app.multi_statement.find_statement_at_cursor")
def test_action_execute_single_statement_no_statement_found(mock_find: MagicMock) -> None:
    """Test handling when no statement is found at the cursor."""
    host = MockHost()
    host.current_connection = MagicMock()
    host.query_input.text = "SELECT 1"
    host.query_input.cursor_location = (0, 0)
    mock_find.return_value = None

    host.action_execute_single_statement()

    host.notify.assert_called_once_with("No statement found at cursor", severity="warning")
    host.run_worker.assert_not_called()
