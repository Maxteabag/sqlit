"""PostgreSQL fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.environ.get("POSTGRES_USER", "testuser")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "TestPassword123!")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "test_sqlit")


def postgres_available() -> bool:
    """Check if PostgreSQL is available."""
    return is_port_open(POSTGRES_HOST, POSTGRES_PORT)


@pytest.fixture(scope="session")
def postgres_server_ready() -> bool:
    """Check if PostgreSQL is ready and return True/False."""
    if not postgres_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def postgres_db(postgres_server_ready: bool) -> str:
    """Set up PostgreSQL test database."""
    if not postgres_server_ready:
        pytest.skip("PostgreSQL is not available")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed")

    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")

        cursor.execute("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE test_products (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
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

        # Create test sequence for integration tests
        cursor.execute("CREATE SEQUENCE test_sequence START 1")

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
        pytest.skip(f"Failed to setup PostgreSQL database: {e}")

    yield POSTGRES_DATABASE

    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        cursor.execute("DROP SEQUENCE IF EXISTS test_sequence")
        cursor.execute("DROP FUNCTION IF EXISTS test_audit_func")
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def postgres_connection(postgres_db: str) -> str:
    """Create a sqlit CLI connection for PostgreSQL and clean up after test."""
    connection_name = f"test_postgres_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "postgresql",
        "--name",
        connection_name,
        "--server",
        POSTGRES_HOST,
        "--port",
        str(POSTGRES_PORT),
        "--database",
        postgres_db,
        "--username",
        POSTGRES_USER,
        "--password",
        POSTGRES_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "POSTGRES_DATABASE",
    "POSTGRES_HOST",
    "POSTGRES_PASSWORD",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "postgres_available",
    "postgres_connection",
    "postgres_db",
    "postgres_server_ready",
]
