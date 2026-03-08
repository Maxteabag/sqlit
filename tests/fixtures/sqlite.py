"""SQLite fixtures."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from tests.fixtures.utils import cleanup_connection, run_cli


@pytest.fixture(scope="function")
def sqlite_db_path(tmp_path: Path) -> Path:
    """Create a temporary SQLite database file path."""
    return tmp_path / "test_database.db"


@pytest.fixture(scope="function")
def sqlite_db(sqlite_db_path: Path) -> Path:
    """Create a temporary SQLite database with test data."""
    conn = sqlite3.connect(sqlite_db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE VIEW test_user_emails AS
        SELECT id, name, email FROM test_users WHERE email IS NOT NULL
    """)

    # Create test index for integration tests
    cursor.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

    # Create test trigger for integration tests
    cursor.execute("""
        CREATE TRIGGER trg_test_users_audit
        AFTER INSERT ON test_users
        BEGIN
            SELECT 1;
        END
    """)

    cursor.executemany(
        "INSERT INTO test_users (id, name, email) VALUES (?, ?, ?)",
        [
            (1, "Alice", "alice@example.com"),
            (2, "Bob", "bob@example.com"),
            (3, "Charlie", "charlie@example.com"),
        ],
    )

    cursor.executemany(
        "INSERT INTO test_products (id, name, price, stock) VALUES (?, ?, ?, ?)",
        [
            (1, "Widget", 9.99, 100),
            (2, "Gadget", 19.99, 50),
            (3, "Gizmo", 29.99, 25),
        ],
    )

    conn.commit()
    conn.close()

    return sqlite_db_path


@pytest.fixture(scope="function")
def sqlite_connection(sqlite_db: Path) -> str:
    """Create a sqlit CLI connection for SQLite and clean up after test."""
    connection_name = f"test_sqlite_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "sqlite",
        "--name",
        connection_name,
        "--file-path",
        str(sqlite_db),
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "sqlite_connection",
    "sqlite_db",
    "sqlite_db_path",
]
