"""Tests for ExasolAdapter introspection and query execution.

Everything runs against a mocked pyexasol connection - no driver is imported.
Two shapes matter and are pinned deliberately:

* ``conn.meta.list_*`` return already-fetched lists of dicts with UPPERCASE keys
  (pyexasol hard-codes ``fetch_dict=True`` there), while ``execute_snapshot``
  returns an ``ExaStatement`` that still needs an explicit ``fetchall()``.
  Feeding tuples here would pass against an index-based implementation and so
  would pin nothing at all.
* Every statement mock sets ``result_type`` explicitly. On a bare ``MagicMock``
  the ``!= "resultSet"`` comparison is trivially true, which would make a
  result-set test go green while asserting nothing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from sqlit.domains.connections.providers.adapters.base import ColumnInfo
from sqlit.domains.connections.providers.exasol.adapter import ExasolAdapter


@pytest.fixture
def adapter() -> ExasolAdapter:
    return ExasolAdapter()


@pytest.fixture
def mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.meta.list_tables.return_value = []
    conn.meta.list_views.return_value = []
    conn.meta.list_columns.return_value = []
    conn.meta.execute_snapshot.return_value.fetchall.return_value = []
    return conn


def _statement(*, result_type: str, columns: tuple[str, ...] = (), rows: list[Any] | None = None) -> MagicMock:
    """Build a statement mock with result_type ALWAYS set explicitly."""
    available = list(rows or [])
    stmt = MagicMock()
    stmt.result_type = result_type
    stmt.column_names.return_value = list(columns)
    stmt.fetchall.return_value = available
    stmt.fetchmany.side_effect = lambda size: available[:size]
    return stmt


# --- Introspection ----------------------------------------------------------


def test_get_tables_reads_schema_and_name_by_key(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    mock_conn.meta.list_tables.return_value = [
        {"TABLE_SCHEMA": "SALES", "TABLE_NAME": "ORDERS"},
        {"TABLE_SCHEMA": "SALES", "TABLE_NAME": "CUSTOMERS"},
    ]

    assert adapter.get_tables(mock_conn) == [("SALES", "ORDERS"), ("SALES", "CUSTOMERS")]


def test_get_views_reads_schema_and_name_by_key(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    mock_conn.meta.list_views.return_value = [
        {"VIEW_SCHEMA": "SALES", "VIEW_NAME": "V_ORDERS"},
        {"VIEW_SCHEMA": "REPORTING", "VIEW_NAME": "V_TOTALS"},
    ]

    assert adapter.get_views(mock_conn) == [("SALES", "V_ORDERS"), ("REPORTING", "V_TOTALS")]


def test_get_columns_combines_primary_key_and_column_information(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    pk = MagicMock()
    pk.fetchall.return_value = [{"COLUMN_NAME": "ID"}]
    columns = MagicMock()
    columns.fetchall.return_value = [
        {"COLUMN_NAME": "ID", "COLUMN_TYPE": "DECIMAL(18,0)"},
        {"COLUMN_NAME": "NAME", "COLUMN_TYPE": "VARCHAR(200) UTF8"},
    ]
    mock_conn.meta.execute_snapshot.side_effect = [pk, columns]

    result = adapter.get_columns(mock_conn, "ORDERS", schema="SALES")

    assert result == [
        ColumnInfo(name="ID", data_type="DECIMAL(18,0)", is_primary_key=True),
        ColumnInfo(name="NAME", data_type="VARCHAR(200) UTF8", is_primary_key=False),
    ]


def test_primary_key_lookup_is_snapshot_executed_and_parameterised(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    adapter.get_columns(mock_conn, "ORDERS", schema="SALES")

    # conn.meta.* wraps the query in Exasol's snapshot-execution hint, so it
    # cannot be blocked by a metadata lock; conn.execute would not be.
    mock_conn.execute.assert_not_called()
    assert mock_conn.meta.execute_snapshot.call_count == 2

    sql, params = mock_conn.meta.execute_snapshot.call_args_list[0].args
    assert "SYS.EXA_ALL_CONSTRAINT_COLUMNS" in sql
    assert "CONSTRAINT_TYPE = 'PRIMARY KEY'" in sql
    # Placeholders, not interpolated values.
    assert "{schema!s}" in sql
    assert "{table!s}" in sql
    assert params == {"schema": "SALES", "table": "ORDERS"}


def test_table_without_a_primary_key_flags_no_column(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    pk = MagicMock()
    pk.fetchall.return_value = []
    columns = MagicMock()
    columns.fetchall.return_value = [
        {"COLUMN_NAME": "A", "COLUMN_TYPE": "BOOLEAN"},
        {"COLUMN_NAME": "B", "COLUMN_TYPE": "DATE"},
    ]
    mock_conn.meta.execute_snapshot.side_effect = [pk, columns]

    result = adapter.get_columns(mock_conn, "LOG", schema="SALES")

    assert [column.is_primary_key for column in result] == [False, False]


def test_get_columns_without_a_schema_queries_the_empty_schema(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    adapter.get_columns(mock_conn, "ORDERS")

    assert adapter.default_schema == ""
    assert mock_conn.meta.execute_snapshot.call_args.args[1] == {"schema": "", "table": "ORDERS"}


def test_get_procedures_returns_scripting_script_names(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    mock_conn.meta.execute_snapshot.return_value.fetchall.return_value = [
        {"SCRIPT_SCHEMA": "SALES", "SCRIPT_NAME": "REBUILD"},
        {"SCRIPT_SCHEMA": "SALES", "SCRIPT_NAME": "PURGE"},
    ]

    assert adapter.get_procedures(mock_conn) == ["REBUILD", "PURGE"]

    sql = mock_conn.meta.execute_snapshot.call_args.args[0]
    assert "SYS.EXA_ALL_SCRIPTS" in sql
    # SCRIPTING is Exasol's scripting-program type, as opposed to UDF, ADAPTER
    # and PREPROCESSOR.
    assert "SCRIPT_TYPE = 'SCRIPTING'" in sql
    mock_conn.execute.assert_not_called()


@pytest.mark.parametrize("method_name", ["get_databases", "get_indexes", "get_triggers", "get_sequences"])
def test_unsupported_object_kinds_return_empty_without_querying(adapter: ExasolAdapter, method_name: str) -> None:
    conn = MagicMock()

    assert getattr(adapter, method_name)(conn) == []
    assert conn.mock_calls == []


# --- Query execution --------------------------------------------------------


def test_row_count_statement_returns_empty_without_fetching(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    stmt = _statement(result_type="rowCount")
    mock_conn.execute.return_value = stmt

    assert adapter.execute_query(mock_conn, "INSERT INTO SALES.ORDERS VALUES (1)") == ([], [], False)

    # The guard has to precede any fetch: ExaStatement.__next__ raises
    # ExaRuntimeError for a rowCount statement, and fetchmany() iterates.
    stmt.fetchall.assert_not_called()
    stmt.fetchmany.assert_not_called()


def test_result_set_statement_returns_every_row_as_a_tuple(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    # Lists in, tuples out - this pins the conversion rather than the input type.
    stmt = _statement(result_type="resultSet", columns=("ID", "NAME"), rows=[[1, "a"], [2, "b"]])
    mock_conn.execute.return_value = stmt

    columns, rows, truncated = adapter.execute_query(mock_conn, "SELECT * FROM SALES.ORDERS")

    assert columns == ["ID", "NAME"]
    assert rows == [(1, "a"), (2, "b")]
    assert all(isinstance(row, tuple) for row in rows)
    assert truncated is False
    stmt.fetchmany.assert_not_called()


@pytest.mark.parametrize(("available", "expected_truncated"), [(2, False), (3, True)])
def test_truncation_flag_at_the_max_rows_boundary(
    adapter: ExasolAdapter, mock_conn: MagicMock, available: int, expected_truncated: bool
) -> None:
    stmt = _statement(result_type="resultSet", columns=("N",), rows=[(n,) for n in range(available)])
    mock_conn.execute.return_value = stmt

    _, rows, truncated = adapter.execute_query(mock_conn, "SELECT N FROM SALES.ORDERS", max_rows=2)

    assert len(rows) == 2
    assert truncated is expected_truncated


def test_one_row_beyond_the_limit_is_requested(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    stmt = _statement(result_type="resultSet", columns=("N",), rows=[(1,)])
    mock_conn.execute.return_value = stmt

    adapter.execute_query(mock_conn, "SELECT N FROM SALES.ORDERS", max_rows=2)

    # One extra row is what makes truncation detectable.
    stmt.fetchmany.assert_called_once_with(3)
    stmt.fetchall.assert_not_called()


def test_execute_non_query_calls_rowcount_as_a_method(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    stmt = _statement(result_type="rowCount")
    stmt.rowcount.return_value = 7
    mock_conn.execute.return_value = stmt

    result = adapter.execute_non_query(mock_conn, "DELETE FROM SALES.ORDERS")

    # rowcount is a method on ExaStatement, not a property: reading it would hand
    # int() a bound method.
    stmt.rowcount.assert_called_once_with()
    assert result == 7
    assert isinstance(result, int)
    # No explicit commit - the connection is opened with autocommit=True.
    mock_conn.commit.assert_not_called()


def test_execute_test_query_does_not_use_cursor(adapter: ExasolAdapter, mock_conn: MagicMock) -> None:
    # The inherited implementation calls conn.cursor(), which pyexasol lacks.
    # Deleting the attribute makes any access raise AttributeError.
    del mock_conn.cursor

    adapter.execute_test_query(mock_conn)

    assert adapter.test_query == "SELECT 1"
    mock_conn.execute.assert_called_once_with("SELECT 1")
    mock_conn.execute.return_value.fetchval.assert_called_once_with()


# --- Identifier quoting and select building ---------------------------------


def test_quote_identifier_wraps_in_double_quotes(adapter: ExasolAdapter) -> None:
    assert adapter.quote_identifier("MY_TABLE") == '"MY_TABLE"'


def test_quote_identifier_doubles_an_embedded_double_quote(adapter: ExasolAdapter) -> None:
    assert adapter.quote_identifier('WEIRD"NAME') == '"WEIRD""NAME"'


def test_build_select_query_qualifies_with_the_schema(adapter: ExasolAdapter) -> None:
    assert adapter.build_select_query("T", 10, schema="S") == 'SELECT * FROM "S"."T" LIMIT 10'


def test_build_select_query_without_a_schema_omits_the_segment(adapter: ExasolAdapter) -> None:
    query = adapter.build_select_query("T", 10)

    assert query == 'SELECT * FROM "T" LIMIT 10'
    # No leading dot from an empty schema segment.
    assert '."T"' not in query
