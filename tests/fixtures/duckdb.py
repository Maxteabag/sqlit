"""DuckDB fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.fixtures.utils import cleanup_connection, run_cli


@pytest.fixture(scope="function")
def duckdb_db_path(tmp_path: Path) -> Path:
    """Create a temporary DuckDB database file path."""
    return tmp_path / "test_database.duckdb"


@pytest.fixture(scope="function")
def duckdb_db(duckdb_db_path: Path) -> Path:
    """Create a temporary DuckDB database with test data."""
    try:
        import duckdb
    except ImportError:
        pytest.skip("duckdb is not installed")

    conn = duckdb.connect(str(duckdb_db_path))

    conn.execute("""
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            email VARCHAR UNIQUE
        )
    """)

    conn.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            price DECIMAL(10,2) NOT NULL,
            stock INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE VIEW test_user_emails AS
        SELECT id, name, email FROM test_users WHERE email IS NOT NULL
    """)

    # Create test index for integration tests
    conn.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

    # Create test sequence for integration tests
    conn.execute("CREATE SEQUENCE test_sequence START 1")

    # Note: DuckDB doesn't support triggers

    conn.execute("""
        INSERT INTO test_users (id, name, email) VALUES
        (1, 'Alice', 'alice@example.com'),
        (2, 'Bob', 'bob@example.com'),
        (3, 'Charlie', 'charlie@example.com')
    """)

    conn.execute("""
        INSERT INTO test_products (id, name, price, stock) VALUES
        (1, 'Widget', 9.99, 100),
        (2, 'Gadget', 19.99, 50),
        (3, 'Gizmo', 29.99, 25)
    """)

    conn.close()

    return duckdb_db_path


@pytest.fixture(scope="function")
def duckdb_connection(duckdb_db: Path) -> str:
    """Create a sqlit CLI connection for DuckDB and clean up after test."""
    connection_name = f"test_duckdb_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "duckdb",
        "--name",
        connection_name,
        "--file-path",
        str(duckdb_db),
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "duckdb_connection",
    "duckdb_db",
    "duckdb_db_path",
]
