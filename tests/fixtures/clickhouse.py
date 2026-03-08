"""ClickHouse fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# ClickHouse Fixtures
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "TestPassword123!")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "test_sqlit")


def clickhouse_available() -> bool:
    """Check if ClickHouse is available."""
    return is_port_open(CLICKHOUSE_HOST, CLICKHOUSE_PORT)


@pytest.fixture(scope="session")
def clickhouse_server_ready() -> bool:
    """Check if ClickHouse is ready and return True/False."""
    if not clickhouse_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def clickhouse_db(clickhouse_server_ready: bool) -> str:
    """Set up ClickHouse test database."""
    if not clickhouse_server_ready:
        pytest.skip("ClickHouse is not available")

    try:
        import clickhouse_connect
    except ImportError:
        pytest.skip("clickhouse-connect is not installed")

    try:
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )

        # Create test database
        client.command(f"DROP DATABASE IF EXISTS {CLICKHOUSE_DATABASE}")
        client.command(f"CREATE DATABASE {CLICKHOUSE_DATABASE}")

        # Connect to test database
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
            database=CLICKHOUSE_DATABASE,
        )

        client.command("""
            CREATE TABLE test_users (
                id UInt32,
                name String,
                email String
            ) ENGINE = MergeTree()
            ORDER BY id
        """)

        client.command("""
            CREATE TABLE test_products (
                id UInt32,
                name String,
                price Float64,
                stock UInt32
            ) ENGINE = MergeTree()
            ORDER BY id
        """)

        client.command("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email != ''
        """)

        # Create test data skipping index for integration tests
        client.command("""
            ALTER TABLE test_users ADD INDEX idx_test_users_email email TYPE set(100) GRANULARITY 1
        """)

        # Note: ClickHouse doesn't support triggers or sequences

        client.command("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
        """)

        client.command("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
        """)

    except Exception as e:
        pytest.skip(f"Failed to setup ClickHouse database: {e}")

    yield CLICKHOUSE_DATABASE

    try:
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )
        client.command(f"DROP DATABASE IF EXISTS {CLICKHOUSE_DATABASE}")
    except Exception:
        pass


@pytest.fixture(scope="function")
def clickhouse_connection(clickhouse_db: str) -> str:
    """Create a sqlit CLI connection for ClickHouse and clean up after test."""
    connection_name = f"test_clickhouse_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "clickhouse",
        "--name",
        connection_name,
        "--server",
        CLICKHOUSE_HOST,
        "--port",
        str(CLICKHOUSE_PORT),
        "--database",
        clickhouse_db,
        "--username",
        CLICKHOUSE_USER,
    ]
    if CLICKHOUSE_PASSWORD:
        args.extend(["--password", CLICKHOUSE_PASSWORD])
    else:
        args.extend(["--password", ""])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "CLICKHOUSE_DATABASE",
    "CLICKHOUSE_HOST",
    "CLICKHOUSE_PASSWORD",
    "CLICKHOUSE_PORT",
    "CLICKHOUSE_USER",
    "clickhouse_available",
    "clickhouse_connection",
    "clickhouse_db",
    "clickhouse_server_ready",
]
