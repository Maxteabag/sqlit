"""Oracle-specific statement execution behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter


@pytest.fixture
def adapter() -> OracleAdapter:
    return OracleAdapter()


@pytest.fixture
def mock_conn() -> MagicMock:
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.description = None
    cursor.rowcount = 0
    return conn


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("SELECT ';' AS value FROM DUAL;", "SELECT ';' AS value FROM DUAL"),
        ("SELECT 1 FROM DUAL;  \n", "SELECT 1 FROM DUAL"),
        ("SELECT 1 FROM DUAL", "SELECT 1 FROM DUAL"),
    ],
)
def test_execute_query_removes_sql_statement_terminator(
    adapter: OracleAdapter,
    mock_conn: MagicMock,
    query: str,
    expected: str,
) -> None:
    """python-oracledb rejects SQL statements ending in a semicolon."""
    adapter.execute_query(mock_conn, query)

    mock_conn.cursor.return_value.execute.assert_called_once_with(expected)


def test_execute_non_query_removes_sql_statement_terminator(
    adapter: OracleAdapter,
    mock_conn: MagicMock,
) -> None:
    """Issue #260: ALTER SESSION must reach python-oracledb without ``;``."""
    adapter.execute_non_query(mock_conn, "ALTER SESSION SET EDITION = V0;")

    mock_conn.cursor.return_value.execute.assert_called_once_with("ALTER SESSION SET EDITION = V0")


@pytest.mark.parametrize(
    "statement",
    [
        "BEGIN NULL; END;",
        "DECLARE value NUMBER := 1; BEGIN NULL; END;",
        "CREATE OR REPLACE PROCEDURE p AS BEGIN NULL; END;",
        "-- setup\nBEGIN NULL; END;",
        "/* setup */ CREATE OR REPLACE EDITIONABLE FUNCTION f RETURN NUMBER "
        "AS BEGIN RETURN 1; END;",
        "CREATE OR REPLACE TYPE BODY t AS MEMBER PROCEDURE p IS "
        "BEGIN NULL; END; END;",
    ],
)
def test_execute_non_query_preserves_plsql_terminator(
    adapter: OracleAdapter,
    mock_conn: MagicMock,
    statement: str,
) -> None:
    """The final semicolon is part of PL/SQL syntax, not a client terminator."""
    adapter.execute_non_query(mock_conn, statement)

    mock_conn.cursor.return_value.execute.assert_called_once_with(statement)
