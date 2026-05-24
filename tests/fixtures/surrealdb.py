"""SurrealDB fixtures."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# SurrealDB connection settings for Docker
SURREALDB_HOST = os.environ.get("SURREALDB_HOST", "localhost")
SURREALDB_PORT = int(os.environ.get("SURREALDB_PORT", "8000"))
SURREALDB_USER = os.environ.get("SURREALDB_USER", "root")
SURREALDB_PASSWORD = os.environ.get("SURREALDB_PASSWORD", "root")
SURREALDB_NAMESPACE = os.environ.get("SURREALDB_NAMESPACE", "test_ns")
SURREALDB_DATABASE = os.environ.get("SURREALDB_DATABASE", "test_sqlit")


def surrealdb_available() -> bool:
    """Check if SurrealDB is available."""
    return is_port_open(SURREALDB_HOST, SURREALDB_PORT)


@pytest.fixture(scope="session")
def surrealdb_server_ready() -> bool:
    """Check if SurrealDB is ready and return True/False."""
    if not surrealdb_available():
        return False

    time.sleep(1)
    return True


def _create_surrealdb_client():
    """Create a SurrealDB client using the official SDK (surrealdb>=1.0)."""
    import surrealdb

    url = f"ws://{SURREALDB_HOST}:{SURREALDB_PORT}/rpc"
    db = surrealdb.Surreal(url)
    db.signin({"username": SURREALDB_USER, "password": SURREALDB_PASSWORD})
    db.use(SURREALDB_NAMESPACE, SURREALDB_DATABASE)
    return db


def _setup_surrealdb_test_tables(client) -> None:
    """Set up test tables in SurrealDB."""
    # Clean up any previous test objects (ignore errors)
    for stmt in (
        "REMOVE TABLE IF EXISTS test_user_emails",
        "REMOVE TABLE IF EXISTS test_users",
        "REMOVE TABLE IF EXISTS test_products",
    ):
        try:
            client.query(stmt)
        except Exception:
            pass

    # Define tables (SurrealDB is schemaless by default; SCHEMAFULL makes
    # INFO FOR TABLE return field/index metadata for adapter introspection).
    client.query(
        """
        DEFINE TABLE test_users SCHEMAFULL;
        DEFINE FIELD name ON test_users TYPE string;
        DEFINE FIELD email ON test_users TYPE option<string>;
        DEFINE INDEX idx_test_users_email ON test_users FIELDS email UNIQUE;
        """
    )

    client.query(
        """
        DEFINE TABLE test_products SCHEMAFULL;
        DEFINE FIELD name ON test_products TYPE string;
        DEFINE FIELD price ON test_products TYPE number;
        DEFINE FIELD stock ON test_products TYPE int DEFAULT 0;
        """
    )

    # SurrealDB view-like table: DEFINE TABLE ... AS SELECT
    client.query(
        """
        DEFINE TABLE test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email != NONE;
        """
    )

    # Seed rows. SurrealDB assigns record IDs like test_users:1 when id is numeric.
    client.query(
        """
        CREATE test_users:1 SET name = 'Alice', email = 'alice@example.com';
        CREATE test_users:2 SET name = 'Bob', email = 'bob@example.com';
        CREATE test_users:3 SET name = 'Charlie', email = 'charlie@example.com';
        """
    )

    client.query(
        """
        CREATE test_products:1 SET name = 'Widget', price = 9.99, stock = 100;
        CREATE test_products:2 SET name = 'Gadget', price = 19.99, stock = 50;
        CREATE test_products:3 SET name = 'Gizmo', price = 29.99, stock = 25;
        """
    )


def _cleanup_surrealdb_test_tables(client) -> None:
    """Clean up test tables in SurrealDB."""
    for stmt in (
        "REMOVE TABLE IF EXISTS test_user_emails",
        "REMOVE TABLE IF EXISTS test_users",
        "REMOVE TABLE IF EXISTS test_products",
    ):
        try:
            client.query(stmt)
        except Exception:
            pass


@pytest.fixture(scope="function")
def surrealdb_db(surrealdb_server_ready: bool) -> Iterator[str]:
    """Set up SurrealDB test database."""
    if not surrealdb_server_ready:
        pytest.skip("SurrealDB is not available")

    import importlib.util

    if importlib.util.find_spec("surrealdb") is None:
        pytest.skip("surrealdb is not installed")

    try:
        client = _create_surrealdb_client()
        _setup_surrealdb_test_tables(client)
        client.close()
    except Exception as e:
        pytest.skip(f"Failed to setup SurrealDB database: {e}")

    yield SURREALDB_DATABASE

    try:
        client = _create_surrealdb_client()
        _cleanup_surrealdb_test_tables(client)
        client.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def surrealdb_connection(surrealdb_db: str) -> Iterator[str]:
    """Create a sqlit CLI connection for SurrealDB and clean up after test."""
    connection_name = f"test_surrealdb_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "surrealdb",
        "--name",
        connection_name,
        "--server",
        SURREALDB_HOST,
        "--port",
        str(SURREALDB_PORT),
        "--namespace",
        SURREALDB_NAMESPACE,
        "--database",
        surrealdb_db,
        "--username",
        SURREALDB_USER,
        "--password",
        SURREALDB_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "SURREALDB_DATABASE",
    "SURREALDB_HOST",
    "SURREALDB_NAMESPACE",
    "SURREALDB_PASSWORD",
    "SURREALDB_PORT",
    "SURREALDB_USER",
    "surrealdb_available",
    "surrealdb_connection",
    "surrealdb_db",
    "surrealdb_server_ready",
]
