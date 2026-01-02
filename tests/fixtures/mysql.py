"""MySQL fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# Note: We use root user because MySQL's testuser only has localhost access inside the container
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "TestPassword123!")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "test_sqlit")


def mysql_available() -> bool:
    """Check if MySQL is available."""
    return is_port_open(MYSQL_HOST, MYSQL_PORT)


@pytest.fixture(scope="session")
def mysql_server_ready() -> bool:
    """Check if MySQL is ready and return True/False."""
    if not mysql_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def mysql_db(mysql_server_ready: bool) -> str:
    """Set up MySQL test database."""
    if not mysql_server_ready:
        pytest.skip("MySQL is not available")

    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL is not installed")

    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            connect_timeout=10,
        )
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS test_users")
        cursor.execute("DROP TABLE IF EXISTS test_products")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")

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
        pytest.skip(f"Failed to setup MySQL database: {e}")

    yield MYSQL_DATABASE

    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            connect_timeout=10,
        )
        cursor = conn.cursor()
        cursor.execute("DROP TRIGGER IF EXISTS trg_test_users_audit")
        cursor.execute("DROP TABLE IF EXISTS test_users")
        cursor.execute("DROP TABLE IF EXISTS test_products")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        conn.commit()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def mysql_connection(mysql_db: str) -> str:
    """Create a sqlit CLI connection for MySQL and clean up after test."""
    connection_name = f"test_mysql_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mysql",
        "--name",
        connection_name,
        "--server",
        MYSQL_HOST,
        "--port",
        str(MYSQL_PORT),
        "--database",
        mysql_db,
        "--username",
        MYSQL_USER,
        "--password",
        MYSQL_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "MYSQL_DATABASE",
    "MYSQL_HOST",
    "MYSQL_PASSWORD",
    "MYSQL_PORT",
    "MYSQL_USER",
    "mysql_available",
    "mysql_connection",
    "mysql_db",
    "mysql_server_ready",
]
