"""Regression coverage for stored procedures that return DB-API result sets."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter
from sqlit.domains.query.app.query_service import DialectQueryAnalyzer, QueryResult, QueryService


class ResultSetCursor:
    def __init__(self, result_sets: list[tuple[Any, list[tuple[Any, ...]]]]) -> None:
        self._sets = result_sets
        self._index = 0
        self.description = result_sets[0][0]
        self.executed: str | None = None
        self.nextset_calls = 0

    def execute(self, query: str) -> None:
        self.executed = query

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._sets[self._index][1]

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        return self._sets[self._index][1][:size]

    def nextset(self) -> bool:
        self.nextset_calls += 1
        self._index += 1
        if self._index >= len(self._sets):
            return False
        self.description = self._sets[self._index][0]
        return True


def _description(*names: str) -> tuple[tuple[str], ...]:
    return tuple((name,) for name in names)


@pytest.mark.parametrize(
    ("adapter", "statement"),
    [
        (MySQLAdapter(), "CALL get_users()"),
        (MySQLAdapter(), "CALL\nget_users()"),
        (MySQLAdapter(), "-- report\nCALL get_users()"),
        (SQLServerAdapter(), "EXEC get_users"),
        (SQLServerAdapter(), "EXEC\tget_users"),
        (SQLServerAdapter(), "/* report */ EXEC get_users"),
        (SQLServerAdapter(), "EXECUTE get_users"),
    ],
)
def test_procedure_call_is_routed_to_row_execution(adapter: Any, statement: str) -> None:
    cursor = ResultSetCursor([(None, []), (_description("id", "name"), [(1, "Alice")]), (None, [])])
    connection = MagicMock()
    connection.cursor.return_value = cursor
    executor = MagicMock(wraps=adapter)
    service = QueryService(analyzer=DialectQueryAnalyzer(adapter))

    result = service.execute(connection, executor, statement, save_to_history=False)

    assert result == QueryResult(columns=["id", "name"], rows=[(1, "Alice")], row_count=1, truncated=False)
    executor.execute_query.assert_called_once_with(connection, statement, None)
    executor.execute_non_query.assert_not_called()
    assert cursor.nextset_calls == 3


@pytest.mark.parametrize(
    ("adapter", "statement"),
    [(MySQLAdapter(), "CALL update_users()"), (SQLServerAdapter(), "EXEC update_users")],
)
def test_procedure_without_rows_consumes_all_status_sets(adapter: Any, statement: str) -> None:
    cursor = ResultSetCursor([(None, []), (None, [])])
    connection = MagicMock()
    connection.cursor.return_value = cursor

    columns, rows, truncated = adapter.execute_query(connection, statement)

    assert (columns, rows, truncated) == ([], [], False)
    assert cursor.nextset_calls == 2


def test_procedure_results_respect_row_limit_and_drain_connection() -> None:
    adapter = MySQLAdapter()
    cursor = ResultSetCursor([(_description("id"), [(1,), (2,), (3,)]), (None, [])])
    connection = MagicMock()
    connection.cursor.return_value = cursor

    columns, rows, truncated = adapter.execute_query(connection, "CALL get_users()", max_rows=2)

    assert columns == ["id"]
    assert rows == [(1,), (2,)]
    assert truncated is True
    assert cursor.nextset_calls == 2


def test_stored_procedure_keywords_are_provider_specific() -> None:
    """CALL must not globally bypass non-query execution for other providers."""
    from sqlit.domains.connections.providers.firebird.adapter import FirebirdAdapter
    from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

    assert MySQLAdapter().classify_query("CALL update_users()") is True
    assert SQLServerAdapter().classify_query("EXEC update_users") is True
    assert OracleAdapter().classify_query("CALL update_users()") is False
    assert FirebirdAdapter().classify_query("EXECUTE PROCEDURE update_users") is False


@pytest.mark.parametrize(
    "statement",
    [
        "EXECUTE AS USER = 'reporter'",
        "EXECUTE AS\nUSER = 'reporter'",
        "EXECUTE /* context */ AS\tLOGIN = 'reporter'",
        "EXECUTE ('UPDATE users SET active = 1')",
        "EXEC @sql",
    ],
)
def test_sql_server_non_procedure_execute_forms_remain_non_queries(statement: str) -> None:
    assert SQLServerAdapter().classify_query(statement) is False
