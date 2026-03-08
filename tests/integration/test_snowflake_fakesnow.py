"""Integration tests for Snowflake using fakesnow."""

from __future__ import annotations

import pytest

from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter

fakesnow = pytest.importorskip("fakesnow")


class TestSnowflakeFakeSnow:
    """Integration tests using fakesnow to simulate Snowflake locally."""

    @pytest.fixture
    def adapter(self):
        return SnowflakeAdapter()

    @pytest.fixture
    def config(self):
        return ConnectionConfig(
            name="test-snowflake",
            db_type="snowflake",
            endpoint=TcpEndpoint(
                host="xy12345.us-east-1",
                database="TEST_DB",
                username="testuser",
                password="testpass",
            ),
            options={"schema": "PUBLIC", "warehouse": "COMPUTE_WH"}
        )

    def test_connect_and_query(self, adapter, config):
        """Test connection and basic query execution using fakesnow."""

        # Patch snowflake.connector with fakesnow
        with fakesnow.patch():
            import snowflake.connector

            # Create a connection to setup data
            # fakesnow uses DuckDB under the hood.
            # We need to initialize the 'remote' state.
            # Usually fakesnow redirects connect() to a local duckdb.

            # Setup data
            conn = snowflake.connector.connect(
                user="testuser",
                password="testpass",
                account="xy12345",
                database="TEST_DB"
            )
            cursor = conn.cursor()
            cursor.execute("CREATE DATABASE IF NOT EXISTS TEST_DB")
            cursor.execute("USE DATABASE TEST_DB")
            cursor.execute("CREATE SCHEMA IF NOT EXISTS PUBLIC")
            cursor.execute("USE SCHEMA PUBLIC")
            cursor.execute("CREATE TABLE users (id INT, name STRING)")
            cursor.execute("INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')")
            conn.commit() # fakesnow/duckdb auto-commits usually, but explicit is good.

            # Now test our adapter
            # We need to ensure the adapter uses the patched snowflake.connector
            # The adapter does `import_driver_module`.
            # We need to ensure that import returns our patched module.
            # Since we imported snowflake.connector inside the patch block, sys.modules should be patched.

            # Connect via adapter
            db_conn = adapter.connect(config)

            # Verify databases
            dbs = adapter.get_databases(db_conn)
            assert "TEST_DB" in dbs

            # Verify tables
            # Note: fakesnow might behave slightly differently than real snowflake regarding SHOW/info schema
            # But it aims to support standard SQL.
            # Adapter uses information_schema by default.
            tables = adapter.get_tables(db_conn, database="TEST_DB")
            # fakesnow stores table names in uppercase usually? Or preserves case?
            # DuckDB preserves case if quoted, otherwise lowercase?
            # Snowflake is usually uppercase.
            # Let's check for existence in a case-insensitive way if needed, or print.
            table_names = [t[1].upper() for t in tables]
            assert "USERS" in table_names

            # Verify columns
            cols = adapter.get_columns(db_conn, "USERS", database="TEST_DB", schema="PUBLIC")
            col_names = [c.name.upper() for c in cols]
            assert "ID" in col_names
            assert "NAME" in col_names

            # Execute Query
            cols, rows, truncated = adapter.execute_query(db_conn, "SELECT * FROM users ORDER BY id")
            assert len(rows) == 2
            assert rows[0] == (1, 'Alice')
            assert rows[1] == (2, 'Bob')

            # Test schema awareness
            # fakesnow might support schemas?
            # DuckDB has schemas.

            cursor.close()
            db_conn.close()

    def test_metadata_queries(self, adapter, config):
        """Test metadata retrieval specifics."""
        with fakesnow.patch():
            import snowflake.connector
            conn = snowflake.connector.connect(
                user="testuser", password="testpass", account="acc", database="TEST_DB"
            )
            c = conn.cursor()
            c.execute("CREATE DATABASE IF NOT EXISTS META_DB")
            c.execute("USE DATABASE META_DB")
            c.execute("CREATE SCHEMA IF NOT EXISTS DATA")
            c.execute("CREATE TABLE DATA.products (sku VARCHAR, price NUMBER)")
            conn.commit()

            db_conn = adapter.connect(config)

            # Test get_tables for specific database
            tables = adapter.get_tables(db_conn, database="META_DB")
            # Filter for our table
            my_tables = [t for t in tables if t[1].upper() == "PRODUCTS"]
            assert len(my_tables) == 1
            assert my_tables[0][0].upper() == "DATA" # schema

            db_conn.close()
