"""SQL Server fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

MSSQL_HOST = os.environ.get("MSSQL_HOST", "localhost")
MSSQL_PORT = int(os.environ.get("MSSQL_PORT", "1434"))
MSSQL_USER = os.environ.get("MSSQL_USER", "sa")
MSSQL_PASSWORD = os.environ.get("MSSQL_PASSWORD", "TestPassword123!")
MSSQL_DATABASE = os.environ.get("MSSQL_DATABASE", "test_sqlit")


def mssql_available() -> bool:
    """Check if SQL Server is available."""
    return is_port_open(MSSQL_HOST, MSSQL_PORT)


@pytest.fixture(scope="session")
def mssql_server_ready() -> bool:
    """Check if SQL Server is ready and return True/False."""
    if not mssql_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def mssql_db(mssql_server_ready: bool) -> str:
    """Set up SQL Server test database."""
    if not mssql_server_ready:
        pytest.skip("SQL Server is not available")

    try:
        import mssql_python  # type: ignore[import]
    except ImportError:
        pytest.skip("mssql-python is not installed")

    conn_str = (
        f"SERVER={MSSQL_HOST},{MSSQL_PORT};"
        f"DATABASE=master;"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASSWORD};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )

    try:
        conn = mssql_python.connect(conn_str)
        conn.autocommit = True  # type: ignore[assignment]
        cursor = conn.cursor()

        cursor.execute(f"SELECT name FROM sys.databases WHERE name = '{MSSQL_DATABASE}'")
        if cursor.fetchone():
            cursor.execute(f"ALTER DATABASE [{MSSQL_DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"DROP DATABASE [{MSSQL_DATABASE}]")

        cursor.execute(f"CREATE DATABASE [{MSSQL_DATABASE}]")
        cursor.close()
        conn.close()

        conn_str = (
            f"SERVER={MSSQL_HOST},{MSSQL_PORT};"
            f"DATABASE={MSSQL_DATABASE};"
            f"UID={MSSQL_USER};"
            f"PWD={MSSQL_PASSWORD};"
            "Encrypt=yes;TrustServerCertificate=yes;"
        )
        conn = mssql_python.connect(conn_str)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE test_users (
                id INT PRIMARY KEY,
                name NVARCHAR(100) NOT NULL,
                email NVARCHAR(100) UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE test_products (
                id INT PRIMARY KEY,
                name NVARCHAR(100) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                stock INT DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """)

        cursor.execute("""
            CREATE PROCEDURE sp_test_get_users
            AS
            BEGIN
                SELECT * FROM test_users ORDER BY id;
            END
        """)

        # Create test index for integration tests
        cursor.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

        # Create test trigger for integration tests
        cursor.execute("""
            CREATE TRIGGER trg_test_users_audit
            ON test_users
            AFTER INSERT
            AS
            BEGIN
                SET NOCOUNT ON;
            END
        """)

        # Create test sequence for integration tests
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
        cursor.close()
        conn.close()

    except Exception as e:  # pragma: no cover - environment-specific failures
        pytest.skip(f"Failed to setup SQL Server database: {e}")

    yield MSSQL_DATABASE

    try:
        conn = mssql_python.connect(
            f"SERVER={MSSQL_HOST},{MSSQL_PORT};"
            f"DATABASE=master;"
            f"UID={MSSQL_USER};"
            f"PWD={MSSQL_PASSWORD};"
            "Encrypt=yes;TrustServerCertificate=yes;",
        )
        conn.autocommit = True  # type: ignore[assignment]
        cursor = conn.cursor()
        cursor.execute(f"SELECT name FROM sys.databases WHERE name = '{MSSQL_DATABASE}'")
        if cursor.fetchone():
            cursor.execute(f"ALTER DATABASE [{MSSQL_DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"DROP DATABASE [{MSSQL_DATABASE}]")
        cursor.close()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def mssql_connection(mssql_db: str) -> str:
    """Create a sqlit CLI connection for SQL Server and clean up after test."""
    connection_name = f"test_mssql_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mssql",
        "--name",
        connection_name,
        "--server",
        f"{MSSQL_HOST},{MSSQL_PORT}" if MSSQL_PORT != 1433 else MSSQL_HOST,
        "--database",
        mssql_db,
        "--auth-type",
        "sql",
        "--username",
        MSSQL_USER,
        "--password",
        MSSQL_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "MSSQL_DATABASE",
    "MSSQL_HOST",
    "MSSQL_PASSWORD",
    "MSSQL_PORT",
    "MSSQL_USER",
    "mssql_available",
    "mssql_connection",
    "mssql_db",
    "mssql_server_ready",
]
