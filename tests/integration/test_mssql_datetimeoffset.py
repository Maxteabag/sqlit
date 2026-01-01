"""Integration tests for SQL Server datetimeoffset support.

These tests verify that the mssql-python adapter can correctly handle
datetimeoffset values (timezone-aware datetime columns).
"""

from __future__ import annotations

import os

import pytest

MSSQL_HOST = os.environ.get("MSSQL_HOST", "localhost")
MSSQL_PORT = int(os.environ.get("MSSQL_PORT", "1434"))
MSSQL_USER = os.environ.get("MSSQL_USER", "sa")
MSSQL_PASSWORD = os.environ.get("MSSQL_PASSWORD", "YourStrong@Passw0rd")
MSSQL_DATABASE = os.environ.get("MSSQL_DATABASE", "master")


@pytest.fixture
def mssql_adapter():
    """Get MSSQL adapter instance."""
    from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
    return SQLServerAdapter()


@pytest.fixture
def mssql_config():
    """Get MSSQL connection config."""
    from tests.helpers import ConnectionConfig
    return ConnectionConfig(
        name="test-mssql-dto",
        db_type="mssql",
        server=MSSQL_HOST,
        port=str(MSSQL_PORT),
        database=MSSQL_DATABASE,
        username=MSSQL_USER,
        password=MSSQL_PASSWORD,
        options={"auth_type": "sql"},
    )


def is_mssql_available() -> bool:
    """Check if SQL Server is available."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((MSSQL_HOST, MSSQL_PORT))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.mssql
class TestMSSQLDatetimeOffset:
    """Integration tests for datetimeoffset column support."""

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self, mssql_adapter, mssql_config):
        """Skip tests if SQL Server is not available."""
        if not is_mssql_available():
            pytest.skip("SQL Server is not available")
        import importlib.util

        if importlib.util.find_spec("mssql_python") is None:
            pytest.skip("mssql-python is not installed")
        try:
            conn = mssql_adapter.connect(mssql_config)
            conn.close()
        except Exception as exc:
            pytest.skip(f"SQL Server credentials not available: {exc}")

    def test_query_datetimeoffset_column(self, mssql_adapter, mssql_config):
        """Test that querying a table with datetimeoffset columns works."""
        conn = mssql_adapter.connect(mssql_config)

        try:
            cursor = conn.cursor()

            # Create table with datetimeoffset column
            cursor.execute("""
                IF OBJECT_ID('test_audit_log', 'U') IS NOT NULL
                    DROP TABLE test_audit_log
            """)
            cursor.execute("""
                CREATE TABLE test_audit_log (
                    id INT PRIMARY KEY,
                    action NVARCHAR(100),
                    created_at DATETIMEOFFSET NOT NULL,
                    modified_at DATETIMEOFFSET
                )
            """)

            # Insert test data with various timezone offsets
            cursor.execute("""
                INSERT INTO test_audit_log (id, action, created_at, modified_at) VALUES
                (1, 'INSERT', '2024-01-15 10:30:00.123456 -05:00', '2024-01-15 11:00:00.000000 -05:00'),
                (2, 'UPDATE', '2024-06-20 14:45:30.500000 +00:00', '2024-06-20 15:00:00.000000 +00:00'),
                (3, 'DELETE', '2024-12-01 08:15:45.999999 +05:30', NULL)
            """)
            conn.commit()

            # Query the table - this would fail before the fix
            columns, rows, truncated = mssql_adapter.execute_query(
                conn, "SELECT * FROM test_audit_log ORDER BY id"
            )

            # Verify we got results
            assert len(columns) == 4
            assert len(rows) == 3

            # Verify column names
            assert columns == ["id", "action", "created_at", "modified_at"]

            # Verify datetimeoffset values are returned with correct values
            # (as strings or datetime objects).
            # Row 1: Eastern time (-05:00)
            assert rows[0][0] == 1
            assert rows[0][1] == "INSERT"
            created_1 = rows[0][2]
            created_1_str = created_1 if isinstance(created_1, str) else created_1.isoformat(" ")
            assert "2024-01-15" in created_1_str
            assert "10:30:00" in created_1_str
            assert "-05:00" in created_1_str

            # Row 2: UTC (+00:00)
            assert rows[1][0] == 2
            assert rows[1][1] == "UPDATE"
            created_2 = rows[1][2]
            created_2_str = created_2 if isinstance(created_2, str) else created_2.isoformat(" ")
            assert "2024-06-20" in created_2_str
            assert "+00:00" in created_2_str

            # Row 3: India time (+05:30)
            assert rows[2][0] == 3
            assert rows[2][1] == "DELETE"
            created_3 = rows[2][2]
            created_3_str = created_3 if isinstance(created_3, str) else created_3.isoformat(" ")
            assert "2024-12-01" in created_3_str
            assert "+05:30" in created_3_str
            # NULL value should be None
            assert rows[2][3] is None

            # Clean up
            cursor.execute("DROP TABLE test_audit_log")
            conn.commit()

        finally:
            conn.close()

    def test_select_star_with_audit_columns(self, mssql_adapter, mssql_config):
        """Test SELECT * on a typical table with audit timestamp columns.

        This is the most common use case - tables with CreatedAt/ModifiedAt columns.
        """
        conn = mssql_adapter.connect(mssql_config)

        try:
            cursor = conn.cursor()

            cursor.execute("""
                IF OBJECT_ID('test_entities', 'U') IS NOT NULL
                    DROP TABLE test_entities
            """)
            cursor.execute("""
                CREATE TABLE test_entities (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    name NVARCHAR(100) NOT NULL,
                    description NVARCHAR(MAX),
                    created_at DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET(),
                    modified_at DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET()
                )
            """)

            cursor.execute("""
                INSERT INTO test_entities (name, description) VALUES
                ('Entity 1', 'First entity'),
                ('Entity 2', 'Second entity')
            """)
            conn.commit()

            # SELECT * should work without errors
            columns, rows, truncated = mssql_adapter.execute_query(
                conn, "SELECT * FROM test_entities"
            )

            assert len(rows) == 2
            assert len(columns) == 5

            # Verify the datetimeoffset columns are present and formatted
            for row in rows:
                created_at = row[3]
                modified_at = row[4]
                # Should be non-empty values (string or datetime) with date components
                assert created_at is not None
                assert modified_at is not None
                created_str = created_at if isinstance(created_at, str) else created_at.isoformat(" ")
                modified_str = modified_at if isinstance(modified_at, str) else modified_at.isoformat(" ")
                assert len(created_str) > 10  # date + time (+ optional timezone)
                assert len(modified_str) > 10

            # Clean up
            cursor.execute("DROP TABLE test_entities")
            conn.commit()

        finally:
            conn.close()
