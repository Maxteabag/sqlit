"""Integration tests for Azure SQL Database.

Azure SQL Database is a cloud-based version of SQL Server that does NOT support
cross-database queries. These tests verify that sqlit works correctly with Azure SQL.

To run these tests, set the following environment variables:
    AZURE_SQL_SERVER=your-server.database.windows.net
    AZURE_SQL_DATABASE=your-database
    AZURE_SQL_USER=your-username
    AZURE_SQL_PASSWORD=your-password

Example:
    export AZURE_SQL_SERVER=myserver.database.windows.net
    export AZURE_SQL_DATABASE=mydb
    export AZURE_SQL_USER=sqladmin
    export AZURE_SQL_PASSWORD='MyPassword123!'
    pytest tests/integration/test_azure_sql.py -v
"""

from __future__ import annotations

import os

import pytest

# Azure SQL connection settings from environment
AZURE_SQL_SERVER = os.environ.get("AZURE_SQL_SERVER", "")
AZURE_SQL_DATABASE = os.environ.get("AZURE_SQL_DATABASE", "")
AZURE_SQL_USER = os.environ.get("AZURE_SQL_USER", "")
AZURE_SQL_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "")


def azure_sql_configured() -> bool:
    """Check if Azure SQL credentials are configured."""
    return all([AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USER, AZURE_SQL_PASSWORD])


def azure_sql_available() -> bool:
    """Check if Azure SQL is reachable."""
    if not azure_sql_configured():
        return False

    try:
        import mssql_python
    except ImportError:
        return False

    try:
        conn_str = (
            f"SERVER={AZURE_SQL_SERVER};"
            f"DATABASE={AZURE_SQL_DATABASE};"
            f"UID={AZURE_SQL_USER};"
            f"PWD={AZURE_SQL_PASSWORD};"
            "Encrypt=yes;TrustServerCertificate=no;"
        )
        conn = mssql_python.connect(conn_str)
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def azure_sql_conn():
    """Create an Azure SQL connection for testing."""
    if not azure_sql_configured():
        pytest.skip("Azure SQL credentials not configured")

    try:
        import mssql_python
    except ImportError:
        pytest.skip("mssql-python is not installed")

    if not azure_sql_available():
        pytest.skip("Azure SQL is not reachable")

    conn_str = (
        f"SERVER={AZURE_SQL_SERVER};"
        f"DATABASE={AZURE_SQL_DATABASE};"
        f"UID={AZURE_SQL_USER};"
        f"PWD={AZURE_SQL_PASSWORD};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )

    conn = mssql_python.connect(conn_str)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def azure_sql_adapter():
    """Create an MSSQL adapter instance."""
    try:
        import mssql_python  # noqa: F401
    except ImportError:
        pytest.skip("mssql-python is not installed")

    from sqlit.db.adapters.mssql import SQLServerAdapter
    return SQLServerAdapter()


class TestAzureSQLCompatibility:
    """Test that MSSQL adapter works with Azure SQL Database.

    Azure SQL Database does not support cross-database queries like:
    - [Database].INFORMATION_SCHEMA.TABLES
    - [Database].sys.tables

    These tests verify that all adapter methods work correctly.
    """

    def test_get_tables(self, azure_sql_conn, azure_sql_adapter):
        """Test fetching tables from Azure SQL."""
        # Should work without errors (Azure SQL doesn't support cross-db queries)
        tables = azure_sql_adapter.get_tables(azure_sql_conn, database=AZURE_SQL_DATABASE)
        assert isinstance(tables, list)
        # Each table should be a (schema, name) tuple
        for table in tables:
            assert len(table) == 2
            assert isinstance(table[0], str)  # schema
            assert isinstance(table[1], str)  # name

    def test_get_views(self, azure_sql_conn, azure_sql_adapter):
        """Test fetching views from Azure SQL."""
        views = azure_sql_adapter.get_views(azure_sql_conn, database=AZURE_SQL_DATABASE)
        assert isinstance(views, list)

    def test_get_procedures(self, azure_sql_conn, azure_sql_adapter):
        """Test fetching stored procedures from Azure SQL."""
        procedures = azure_sql_adapter.get_procedures(azure_sql_conn, database=AZURE_SQL_DATABASE)
        assert isinstance(procedures, list)

    def test_get_indexes(self, azure_sql_conn, azure_sql_adapter):
        """Test fetching indexes from Azure SQL."""
        indexes = azure_sql_adapter.get_indexes(azure_sql_conn, database=AZURE_SQL_DATABASE)
        assert isinstance(indexes, list)

    def test_get_triggers(self, azure_sql_conn, azure_sql_adapter):
        """Test fetching triggers from Azure SQL."""
        triggers = azure_sql_adapter.get_triggers(azure_sql_conn, database=AZURE_SQL_DATABASE)
        assert isinstance(triggers, list)

    def test_get_sequences(self, azure_sql_conn, azure_sql_adapter):
        """Test fetching sequences from Azure SQL."""
        sequences = azure_sql_adapter.get_sequences(azure_sql_conn, database=AZURE_SQL_DATABASE)
        assert isinstance(sequences, list)

    def test_get_columns_for_existing_table(self, azure_sql_conn, azure_sql_adapter):
        """Test fetching columns for a table from Azure SQL."""
        # First get tables to find one to test with
        tables = azure_sql_adapter.get_tables(azure_sql_conn, database=AZURE_SQL_DATABASE)
        if not tables:
            pytest.skip("No tables in Azure SQL database to test columns")

        schema, table_name = tables[0]
        columns = azure_sql_adapter.get_columns(
            azure_sql_conn,
            table=table_name,
            database=AZURE_SQL_DATABASE,
            schema=schema or "dbo",
        )
        assert isinstance(columns, list)
        if columns:
            assert hasattr(columns[0], "name")
            assert hasattr(columns[0], "data_type")

    def test_execute_simple_query(self, azure_sql_conn, azure_sql_adapter):
        """Test executing a simple query on Azure SQL."""
        columns, rows, truncated = azure_sql_adapter.execute_query(
            azure_sql_conn,
            "SELECT 1 AS test_value",
        )
        assert columns == ["test_value"]
        assert len(rows) == 1
        assert rows[0][0] == 1


class TestAzureSQLWithoutDefaultDatabase:
    """Test Azure SQL behavior when no default database is specified.

    Note: Azure SQL Database doesn't support querying across databases,
    but it does support USE to switch context within the same logical server
    (for Azure SQL Managed Instance) or within the connected database.
    """

    def test_adapter_handles_database_parameter(self, azure_sql_conn, azure_sql_adapter):
        """Test that adapter correctly handles database parameter."""
        # The adapter should use USE [database] instead of cross-db syntax
        # This test verifies it doesn't raise an error about cross-database references
        try:
            tables = azure_sql_adapter.get_tables(azure_sql_conn, database=AZURE_SQL_DATABASE)
            # If we get here without error, the adapter is working correctly
            assert isinstance(tables, list)
        except Exception as e:
            error_msg = str(e).lower()
            # These errors indicate cross-database syntax was used (which is wrong)
            assert "cross-database" not in error_msg, (
                f"Adapter appears to be using cross-database syntax: {e}"
            )
            assert "server name" not in error_msg, (
                f"Adapter appears to be using cross-database syntax: {e}"
            )
            raise
