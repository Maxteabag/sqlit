"""MariaDB fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# Note: Using 127.0.0.1 instead of localhost to force TCP connection (localhost uses Unix socket)
MARIADB_HOST = os.environ.get("MARIADB_HOST", "127.0.0.1")
MARIADB_PORT = int(os.environ.get("MARIADB_PORT", "3307"))
MARIADB_USER = os.environ.get("MARIADB_USER", "root")
MARIADB_PASSWORD = os.environ.get("MARIADB_PASSWORD", "TestPassword123!")
MARIADB_DATABASE = os.environ.get("MARIADB_DATABASE", "test_sqlit")


def mariadb_available() -> bool:
    """Check if MariaDB is available."""
    return is_port_open(MARIADB_HOST, MARIADB_PORT)


@pytest.fixture(scope="session")
def mariadb_server_ready() -> bool:
    """Check if MariaDB is ready and return True/False."""
    if not mariadb_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def mariadb_db(mariadb_server_ready: bool) -> str:
    """Set up MariaDB test database."""
    if not mariadb_server_ready:
        pytest.skip("MariaDB is not available")

    try:
        import mariadb
    except ImportError:
        pytest.skip("mariadb is not installed")

    try:
        conn = mariadb.connect(
            host=MARIADB_HOST,
            port=MARIADB_PORT,
            database=MARIADB_DATABASE,
            user=MARIADB_USER,
            password=MARIADB_PASSWORD,
            connect_timeout=10,
        )
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS test_users")
        cursor.execute("DROP TABLE IF EXISTS test_products")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        cursor.execute("DROP SEQUENCE IF EXISTS test_sequence")

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

        # Create test trigger for integration tests
        cursor.execute("""
            CREATE TRIGGER trg_test_users_audit
            AFTER INSERT ON test_users
            FOR EACH ROW
            BEGIN
                SET @dummy = 1;
            END
        """)

        # Create test sequence for integration tests (MariaDB 10.3+)
        cursor.execute("CREATE SEQUENCE test_sequence START WITH 1 INCREMENT BY 1")

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

        conn.commit()
        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup MariaDB database: {e}")

    yield MARIADB_DATABASE

    try:
        conn = mariadb.connect(
            host=MARIADB_HOST,
            port=MARIADB_PORT,
            database=MARIADB_DATABASE,
            user=MARIADB_USER,
            password=MARIADB_PASSWORD,
            connect_timeout=10,
        )
        cursor = conn.cursor()
        cursor.execute("DROP TRIGGER IF EXISTS trg_test_users_audit")
        cursor.execute("DROP TABLE IF EXISTS test_users")
        cursor.execute("DROP TABLE IF EXISTS test_products")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        cursor.execute("DROP SEQUENCE IF EXISTS test_sequence")
        conn.commit()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def mariadb_connection(mariadb_db: str) -> str:
    """Create a sqlit CLI connection for MariaDB and clean up after test."""
    connection_name = f"test_mariadb_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mariadb",
        "--name",
        connection_name,
        "--server",
        MARIADB_HOST,
        "--port",
        str(MARIADB_PORT),
        "--database",
        mariadb_db,
        "--username",
        MARIADB_USER,
        "--password",
        MARIADB_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "MARIADB_DATABASE",
    "MARIADB_HOST",
    "MARIADB_PASSWORD",
    "MARIADB_PORT",
    "MARIADB_USER",
    "mariadb_available",
    "mariadb_connection",
    "mariadb_db",
    "mariadb_server_ready",
]
