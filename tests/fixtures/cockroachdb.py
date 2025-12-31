"""CockroachDB fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# CockroachDB connection settings for Docker
COCKROACHDB_HOST = os.environ.get("COCKROACHDB_HOST", "localhost")
COCKROACHDB_PORT = int(os.environ.get("COCKROACHDB_PORT", "26257"))
COCKROACHDB_USER = os.environ.get("COCKROACHDB_USER", "root")
COCKROACHDB_PASSWORD = os.environ.get("COCKROACHDB_PASSWORD", "")
COCKROACHDB_DATABASE = os.environ.get("COCKROACHDB_DATABASE", "test_sqlit")


def cockroachdb_available() -> bool:
    """Check if CockroachDB is available."""
    return is_port_open(COCKROACHDB_HOST, COCKROACHDB_PORT)


@pytest.fixture(scope="session")
def cockroachdb_server_ready() -> bool:
    """Check if CockroachDB is ready and return True/False."""
    if not cockroachdb_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def cockroachdb_db(cockroachdb_server_ready: bool) -> str:
    """Set up CockroachDB test database."""
    if not cockroachdb_server_ready:
        pytest.skip("CockroachDB is not available")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed")

    try:
        conn = psycopg2.connect(
            host=COCKROACHDB_HOST,
            port=COCKROACHDB_PORT,
            database="defaultdb",
            user=COCKROACHDB_USER,
            password=COCKROACHDB_PASSWORD or None,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Database creation requires a connection to an existing DB (e.g. `defaultdb`).
        cursor.execute(f"DROP DATABASE IF EXISTS {COCKROACHDB_DATABASE}")
        cursor.execute(f"CREATE DATABASE {COCKROACHDB_DATABASE}")
        conn.close()

        conn = psycopg2.connect(
            host=COCKROACHDB_HOST,
            port=COCKROACHDB_PORT,
            database=COCKROACHDB_DATABASE,
            user=COCKROACHDB_USER,
            password=COCKROACHDB_PASSWORD or None,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE test_users (
                id INT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE test_products (
                id INT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                stock INT DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """)

        # Create test index for integration tests
        cursor.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

        # Create test sequence for integration tests
        cursor.execute("CREATE SEQUENCE test_sequence START 1")

        # Create test trigger for integration tests (CockroachDB 24.3+)
        # Note: CockroachDB has limited trigger support, using simple AFTER trigger
        try:
            cursor.execute("""
                CREATE OR REPLACE FUNCTION test_audit_func() RETURNS TRIGGER AS $$
                BEGIN
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            cursor.execute("""
                CREATE TRIGGER trg_test_users_audit
                AFTER INSERT ON test_users
                FOR EACH ROW EXECUTE FUNCTION test_audit_func()
            """)
        except Exception:
            pass  # Triggers may not be supported in older CockroachDB versions

        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
        """)

        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
        """)

        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup CockroachDB database: {e}")

    yield COCKROACHDB_DATABASE

    try:
        conn = psycopg2.connect(
            host=COCKROACHDB_HOST,
            port=COCKROACHDB_PORT,
            database="defaultdb",
            user=COCKROACHDB_USER,
            password=COCKROACHDB_PASSWORD or None,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS {COCKROACHDB_DATABASE}")
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def cockroachdb_connection(cockroachdb_db: str) -> str:
    """Create a sqlit CLI connection for CockroachDB and clean up after test."""
    connection_name = f"test_cockroachdb_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "cockroachdb",
        "--name",
        connection_name,
        "--server",
        COCKROACHDB_HOST,
        "--port",
        str(COCKROACHDB_PORT),
        "--database",
        cockroachdb_db,
        "--username",
        COCKROACHDB_USER,
    ]
    if COCKROACHDB_PASSWORD:
        args.extend(["--password", COCKROACHDB_PASSWORD])
    else:
        args.extend(["--password", ""])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "COCKROACHDB_DATABASE",
    "COCKROACHDB_HOST",
    "COCKROACHDB_PASSWORD",
    "COCKROACHDB_PORT",
    "COCKROACHDB_USER",
    "cockroachdb_available",
    "cockroachdb_connection",
    "cockroachdb_db",
    "cockroachdb_server_ready",
]
