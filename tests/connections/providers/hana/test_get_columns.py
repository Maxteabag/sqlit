"""Tests for HANA adapter column discovery.

Regression coverage for #153: SYS.CONSTRAINT_COLUMNS and SYS.COLUMNS
are not queryable in current HANA Cloud schemas. get_columns must use
SYS.CONSTRAINTS (which already exposes COLUMN_NAME and IS_PRIMARY_KEY
per column) and SYS.TABLE_COLUMNS.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sqlit.domains.connections.providers.adapters.base import ColumnInfo
from sqlit.domains.connections.providers.hana.adapter import HanaAdapter


@pytest.fixture
def adapter() -> HanaAdapter:
    return HanaAdapter()


@pytest.fixture
def mock_conn() -> MagicMock:
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.cursor.return_value = cursor
    return conn


def _executed_sql(mock_conn: MagicMock) -> list[str]:
    return [call.args[0].lower() for call in mock_conn.cursor.return_value.execute.call_args_list]


def test_get_columns_does_not_use_deprecated_or_missing_views(
    adapter: HanaAdapter, mock_conn: MagicMock
) -> None:
    adapter.get_columns(mock_conn, "MY_TABLE", schema="MY_SCHEMA")

    sqls = _executed_sql(mock_conn)
    joined = " | ".join(sqls)
    assert "sys.constraint_columns" not in joined
    assert "from sys.columns" not in joined
    assert "sys.table_columns" in joined


def test_get_columns_filters_primary_key_on_constraints_view(
    adapter: HanaAdapter, mock_conn: MagicMock
) -> None:
    adapter.get_columns(mock_conn, "MY_TABLE", schema="MY_SCHEMA")

    sqls = _executed_sql(mock_conn)
    pk_query = next(sql for sql in sqls if "sys.constraints" in sql)
    assert "is_primary_key" in pk_query
    assert "column_name" in pk_query


def test_get_columns_passes_schema_and_table_as_parameters(
    adapter: HanaAdapter, mock_conn: MagicMock
) -> None:
    adapter.get_columns(mock_conn, "MY_TABLE", schema="MY_SCHEMA")

    calls = mock_conn.cursor.return_value.execute.call_args_list
    assert len(calls) == 2
    for call in calls:
        assert call.args[1] == ("MY_SCHEMA", "MY_TABLE")


def test_get_columns_combines_pk_and_column_results(
    adapter: HanaAdapter, mock_conn: MagicMock
) -> None:
    cursor = mock_conn.cursor.return_value
    cursor.fetchall.side_effect = [
        [("ID",)],
        [("ID", "INTEGER"), ("NAME", "NVARCHAR")],
    ]

    result = adapter.get_columns(mock_conn, "MY_TABLE", schema="MY_SCHEMA")

    assert result == [
        ColumnInfo(name="ID", data_type="INTEGER", is_primary_key=True),
        ColumnInfo(name="NAME", data_type="NVARCHAR", is_primary_key=False),
    ]


def test_get_columns_defaults_schema_when_not_provided(
    adapter: HanaAdapter, mock_conn: MagicMock
) -> None:
    adapter.get_columns(mock_conn, "MY_TABLE")

    calls = mock_conn.cursor.return_value.execute.call_args_list
    for call in calls:
        assert call.args[1] == (adapter.default_schema, "MY_TABLE")
