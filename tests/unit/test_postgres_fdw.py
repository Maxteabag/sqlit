"""Regression coverage for PostgreSQL foreign-table discovery."""

from unittest.mock import MagicMock

from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter


def test_get_tables_requests_base_and_foreign_tables() -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = [
        ("public", "local_users"),
        ("remote", "foreign_orders"),
    ]

    tables = PostgreSQLAdapter().get_tables(connection)

    assert tables == [
        ("public", "local_users"),
        ("remote", "foreign_orders"),
    ]
    query = cursor.execute.call_args.args[0]
    assert "table_type IN ('BASE TABLE', 'FOREIGN')" in query
