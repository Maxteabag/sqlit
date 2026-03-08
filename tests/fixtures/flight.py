"""Apache Arrow Flight SQL fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# Flight SQL Fixtures
FLIGHT_HOST = os.environ.get("FLIGHT_HOST", "localhost")
FLIGHT_PORT = int(os.environ.get("FLIGHT_PORT", "31337"))
FLIGHT_USER = os.environ.get("FLIGHT_USER", "")
FLIGHT_PASSWORD = os.environ.get("FLIGHT_PASSWORD", "")
FLIGHT_DATABASE = os.environ.get("FLIGHT_DATABASE", "")


def flight_available() -> bool:
    """Check if Flight SQL server is available."""
    return is_port_open(FLIGHT_HOST, FLIGHT_PORT)


@pytest.fixture(scope="session")
def flight_server_ready() -> bool:
    """Check if Flight SQL server is ready and return True/False."""
    if not flight_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def flight_db(flight_server_ready: bool) -> str:
    """Set up Flight SQL test database."""
    if not flight_server_ready:
        pytest.skip("Flight SQL server is not available")

    try:
        import adbc_driver_flightsql.dbapi as flight_sql
    except ImportError:
        pytest.skip("adbc-driver-flightsql is not installed")

    try:
        # Build connection URI
        uri = f"grpc://{FLIGHT_HOST}:{FLIGHT_PORT}"

        db_kwargs: dict[str, str] = {}
        if FLIGHT_USER or FLIGHT_PASSWORD:
            db_kwargs["username"] = FLIGHT_USER
            db_kwargs["password"] = FLIGHT_PASSWORD

        conn = flight_sql.connect(uri, db_kwargs=db_kwargs)

        # Create test tables using standard SQL
        with conn.cursor() as cursor:
            # Try to create test tables
            try:
                cursor.execute("DROP TABLE IF EXISTS test_users")
            except Exception:
                pass
            try:
                cursor.execute("DROP TABLE IF EXISTS test_products")
            except Exception:
                pass

            cursor.execute("""
                CREATE TABLE test_users (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100),
                    email VARCHAR(100)
                )
            """)

            cursor.execute("""
                CREATE TABLE test_products (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100),
                    price DECIMAL(10, 2),
                    stock INTEGER
                )
            """)

            # Insert test data
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
        pytest.skip(f"Failed to setup Flight SQL database: {e}")

    yield FLIGHT_DATABASE or "default"

    # Cleanup
    try:
        uri = f"grpc://{FLIGHT_HOST}:{FLIGHT_PORT}"
        db_kwargs = {}
        if FLIGHT_USER or FLIGHT_PASSWORD:
            db_kwargs["username"] = FLIGHT_USER
            db_kwargs["password"] = FLIGHT_PASSWORD
        conn = flight_sql.connect(uri, db_kwargs=db_kwargs)
        with conn.cursor() as cursor:
            try:
                cursor.execute("DROP TABLE IF EXISTS test_users")
            except Exception:
                pass
            try:
                cursor.execute("DROP TABLE IF EXISTS test_products")
            except Exception:
                pass
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def flight_connection(flight_db: str) -> str:
    """Create a sqlit CLI connection for Flight SQL and clean up after test."""
    connection_name = f"test_flight_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "flight",
        "--name",
        connection_name,
        "--server",
        FLIGHT_HOST,
        "--port",
        str(FLIGHT_PORT),
    ]
    if FLIGHT_DATABASE:
        args.extend(["--database", FLIGHT_DATABASE])
    if FLIGHT_USER:
        args.extend(["--username", FLIGHT_USER])
    if FLIGHT_PASSWORD:
        args.extend(["--password", FLIGHT_PASSWORD])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "FLIGHT_DATABASE",
    "FLIGHT_HOST",
    "FLIGHT_PASSWORD",
    "FLIGHT_PORT",
    "FLIGHT_USER",
    "flight_available",
    "flight_connection",
    "flight_db",
    "flight_server_ready",
]
