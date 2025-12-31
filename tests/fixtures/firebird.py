"""Firebird fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

FIREBIRD_HOST = os.environ.get("FIREBIRD_HOST", "localhost")
FIREBIRD_PORT = int(os.environ.get("FIREBIRD_PORT", "3050"))
FIREBIRD_USER = os.environ.get("FIREBIRD_USER", "testuser")
FIREBIRD_PASSWORD = os.environ.get("FIREBIRD_PASSWORD", "TestPassword123!")
FIREBIRD_DATABASE = os.environ.get("FIREBIRD_DATABASE", "/var/lib/firebird/data/test_sqlit.fdb")


def firebird_available() -> bool:
    """Check if Firebird is available."""
    return is_port_open(FIREBIRD_HOST, FIREBIRD_PORT)


@pytest.fixture(scope="session")
def firebird_server_ready() -> bool:
    """Check if Firebird is ready and return True/False."""
    if not firebird_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def firebird_db(firebird_server_ready: bool) -> str:
    """Set up Firebird test database."""
    if not firebird_server_ready:
        pytest.skip("Firebird is not available")

    try:
        import firebirdsql
    except ImportError:
        pytest.skip("firebirdsql is not installed")

    try:
        conn = firebirdsql.connect(
            host=FIREBIRD_HOST,
            port=FIREBIRD_PORT,
            database=FIREBIRD_DATABASE,
            user=FIREBIRD_USER,
            password=FIREBIRD_PASSWORD,
        )
    except Exception as e:
        pytest.skip(f"cannot connect to database: {e}")

    cursor = conn.cursor()
    try:
        for cleanup in [
            "DROP VIEW test_user_emails",
        ]:
            try:
                cursor.execute(cleanup)
            except firebirdsql.DatabaseError:
                pass
        conn.commit()

        cursor.execute("""
            RECREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
            )
        """)

        cursor.execute("""
            RECREATE TABLE test_products (
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

        cursor.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

        cursor.execute("""
            RECREATE TRIGGER trg_test_users_audit FOR test_users
            BEFORE INSERT
            AS
            BEGIN
                NEW.email = LOWER(NEW.email);
            END
        """)

        cursor.execute("RECREATE GENERATOR test_sequence START WITH 1 INCREMENT 1")

        conn.commit()

        # Firebird doesn't support bulk inserts with VALUES
        for insert in [
            "INSERT INTO test_users (id, name, email) VALUES (1, 'Alice', 'alice@example.com')",
            "INSERT INTO test_users (id, name, email) VALUES (2, 'Bob', 'bob@example.com')",
            "INSERT INTO test_users (id, name, email) VALUES (3, 'Charlie', 'charlie@example.com')",
            "INSERT INTO test_products (id, name, price, stock) VALUES (1, 'Widget', 9.99, 100)",
            "INSERT INTO test_products (id, name, price, stock) VALUES (2, 'Gadget', 19.99, 50)",
            "INSERT INTO test_products (id, name, price, stock) VALUES (3, 'Gizmo', 29.99, 25)",
        ]:
            cursor.execute(insert)

        conn.commit()
    except Exception as e:
        pytest.skip(f"Failed to setup Firebird database: {e}")
    finally:
        conn.close()

    yield FIREBIRD_DATABASE

    try:
        conn = firebirdsql.connect(
            host=FIREBIRD_HOST,
            port=FIREBIRD_PORT,
            database=FIREBIRD_DATABASE,
            user=FIREBIRD_USER,
            password=FIREBIRD_PASSWORD,
        )
    except Exception as e:
        pytest.skip(f"Failed to connect to Firebird database for teardown: {e}")

    cursor = conn.cursor()
    try:
        for cleanup in [
            "DROP VIEW test_user_emails",
            "DROP TABLE test_users",
            "DROP TABLE test_products",
            "DROP TRIGGER trg_test_users_audit",
            "DROP SEQUENCE test_sequence",
        ]:
            try:
                cursor.execute(cleanup)
            except firebirdsql.DatabaseError:
                pass
    finally:
        conn.commit()
        conn.close()


@pytest.fixture(scope="function")
def firebird_connection(firebird_db: str) -> str:
    """Create a sqlit CLI connection for Firebird and clean up after test."""
    connection_name = f"test_firebird_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "firebird",
        "--name",
        connection_name,
        "--server",
        FIREBIRD_HOST,
        "--port",
        str(FIREBIRD_PORT),
        "--database",
        firebird_db,
        "--username",
        FIREBIRD_USER,
        "--password",
        FIREBIRD_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "FIREBIRD_DATABASE",
    "FIREBIRD_HOST",
    "FIREBIRD_PASSWORD",
    "FIREBIRD_PORT",
    "FIREBIRD_USER",
    "firebird_available",
    "firebird_connection",
    "firebird_db",
    "firebird_server_ready",
]
