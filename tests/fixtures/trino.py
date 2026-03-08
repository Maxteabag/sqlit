"""Trino fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
TRINO_PORT = int(os.environ.get("TRINO_PORT", "8082"))
TRINO_USER = os.environ.get("TRINO_USER", "testuser")
TRINO_PASSWORD = os.environ.get("TRINO_PASSWORD", "")
TRINO_CATALOG = os.environ.get("TRINO_CATALOG", "memory")
TRINO_SCHEMA = os.environ.get("TRINO_SCHEMA", "default")
TRINO_HTTP_SCHEME = os.environ.get("TRINO_HTTP_SCHEME", "http")


def trino_available() -> bool:
    """Check if Trino is available."""
    return is_port_open(TRINO_HOST, TRINO_PORT)


def _build_trino_auth():
    if not TRINO_PASSWORD:
        return None
    try:
        from trino.auth import BasicAuthentication
    except Exception as exc:
        raise RuntimeError("Trino BasicAuthentication is unavailable") from exc
    return BasicAuthentication(TRINO_USER, TRINO_PASSWORD)


def _trino_connect(*, catalog: str | None = None, schema: str | None = None):
    import trino.dbapi

    connect_args: dict[str, object] = {
        "host": TRINO_HOST,
        "port": TRINO_PORT,
        "user": TRINO_USER,
        "http_scheme": TRINO_HTTP_SCHEME,
    }
    if catalog:
        connect_args["catalog"] = catalog
    if schema:
        connect_args["schema"] = schema
    auth = _build_trino_auth()
    if auth:
        connect_args["auth"] = auth
    return trino.dbapi.connect(**connect_args)


def _execute(cursor, statement: str) -> None:
    cursor.execute(statement)
    try:
        cursor.fetchall()
    except Exception:
        pass


@pytest.fixture(scope="session")
def trino_server_ready() -> bool:
    """Check if Trino is ready and return True/False."""
    if not trino_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def trino_db(trino_server_ready: bool) -> str:
    """Set up Trino test schema and tables."""
    if not trino_server_ready:
        pytest.skip("Trino is not available")

    try:
        import trino  # noqa: F401
    except ImportError:
        pytest.skip("trino is not installed")

    try:
        conn = _trino_connect()
        cursor = conn.cursor()
        cursor.execute("SHOW CATALOGS")
        catalogs = [row[0] for row in cursor.fetchall()]
        if TRINO_CATALOG not in catalogs:
            pytest.skip(f"Trino catalog '{TRINO_CATALOG}' not found")
        conn.close()

        conn = _trino_connect(catalog=TRINO_CATALOG, schema=TRINO_SCHEMA)
        cursor = conn.cursor()

        try:
            _execute(cursor, f"CREATE SCHEMA IF NOT EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}")
        except Exception:
            try:
                _execute(cursor, f"CREATE SCHEMA {TRINO_CATALOG}.{TRINO_SCHEMA}")
            except Exception:
                pass

        for stmt in [
            f"DROP VIEW IF EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.test_user_emails",
            f"DROP TABLE IF EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.test_users",
            f"DROP TABLE IF EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.test_products",
        ]:
            try:
                _execute(cursor, stmt)
            except Exception:
                pass

        _execute(
            cursor,
            f"""
            CREATE TABLE {TRINO_CATALOG}.{TRINO_SCHEMA}.test_users (
                id INTEGER,
                name VARCHAR,
                email VARCHAR
            )
            """,
        )

        _execute(
            cursor,
            f"""
            CREATE TABLE {TRINO_CATALOG}.{TRINO_SCHEMA}.test_products (
                id INTEGER,
                name VARCHAR,
                price DOUBLE,
                stock INTEGER
            )
            """,
        )

        _execute(
            cursor,
            f"""
            CREATE VIEW {TRINO_CATALOG}.{TRINO_SCHEMA}.test_user_emails AS
            SELECT id, name, email FROM {TRINO_CATALOG}.{TRINO_SCHEMA}.test_users WHERE email IS NOT NULL
            """,
        )

        _execute(
            cursor,
            f"""
            INSERT INTO {TRINO_CATALOG}.{TRINO_SCHEMA}.test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
            """,
        )

        _execute(
            cursor,
            f"""
            INSERT INTO {TRINO_CATALOG}.{TRINO_SCHEMA}.test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
            """,
        )

        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup Trino schema: {e}")

    yield TRINO_CATALOG

    try:
        conn = _trino_connect(catalog=TRINO_CATALOG, schema=TRINO_SCHEMA)
        cursor = conn.cursor()
        for stmt in [
            f"DROP VIEW IF EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.test_user_emails",
            f"DROP TABLE IF EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.test_users",
            f"DROP TABLE IF EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.test_products",
        ]:
            try:
                _execute(cursor, stmt)
            except Exception:
                pass
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def trino_connection(trino_db: str) -> str:
    """Create a sqlit CLI connection for Trino and clean up after test."""
    connection_name = f"test_trino_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "trino",
        "--name",
        connection_name,
        "--server",
        TRINO_HOST,
        "--port",
        str(TRINO_PORT),
        "--database",
        TRINO_CATALOG,
        "--schema",
        TRINO_SCHEMA,
        "--username",
        TRINO_USER,
    ]
    if TRINO_PASSWORD:
        args.extend(["--password", TRINO_PASSWORD])
    else:
        args.extend(["--password", ""])
    if TRINO_HTTP_SCHEME:
        args.extend(["--http-scheme", TRINO_HTTP_SCHEME])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "TRINO_CATALOG",
    "TRINO_HOST",
    "TRINO_HTTP_SCHEME",
    "TRINO_PASSWORD",
    "TRINO_PORT",
    "TRINO_SCHEMA",
    "TRINO_USER",
    "trino_available",
    "trino_connection",
    "trino_db",
    "trino_server_ready",
]
