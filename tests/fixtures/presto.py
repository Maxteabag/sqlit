"""Presto fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

PRESTO_HOST = os.environ.get("PRESTO_HOST", "localhost")
PRESTO_PORT = int(os.environ.get("PRESTO_PORT", "8083"))
PRESTO_USER = os.environ.get("PRESTO_USER", "testuser")
PRESTO_PASSWORD = os.environ.get("PRESTO_PASSWORD", "")
PRESTO_CATALOG = os.environ.get("PRESTO_CATALOG", "memory")
PRESTO_SCHEMA = os.environ.get("PRESTO_SCHEMA", "default")
PRESTO_HTTP_SCHEME = os.environ.get("PRESTO_HTTP_SCHEME", "http")


def presto_available() -> bool:
    """Check if Presto is available."""
    return is_port_open(PRESTO_HOST, PRESTO_PORT)


def _build_presto_auth():
    if not PRESTO_PASSWORD:
        return None
    try:
        from prestodb.auth import BasicAuthentication
    except Exception as exc:
        raise RuntimeError("Presto BasicAuthentication is unavailable") from exc
    return BasicAuthentication(PRESTO_USER, PRESTO_PASSWORD)


def _presto_connect(*, catalog: str | None = None, schema: str | None = None):
    import prestodb.dbapi

    connect_args: dict[str, object] = {
        "host": PRESTO_HOST,
        "port": PRESTO_PORT,
        "user": PRESTO_USER,
        "http_scheme": PRESTO_HTTP_SCHEME,
    }
    if catalog:
        connect_args["catalog"] = catalog
    if schema:
        connect_args["schema"] = schema
    auth = _build_presto_auth()
    if auth:
        connect_args["auth"] = auth
    return prestodb.dbapi.connect(**connect_args)


def _execute(cursor, statement: str) -> None:
    cursor.execute(statement)
    try:
        cursor.fetchall()
    except Exception:
        pass


@pytest.fixture(scope="session")
def presto_server_ready() -> bool:
    """Check if Presto is ready and return True/False."""
    if not presto_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def presto_db(presto_server_ready: bool) -> str:
    """Set up Presto test schema and tables."""
    if not presto_server_ready:
        pytest.skip("Presto is not available")

    try:
        import prestodb  # noqa: F401
    except ImportError:
        pytest.skip("presto-python-client is not installed")

    try:
        conn = _presto_connect()
        cursor = conn.cursor()
        cursor.execute("SHOW CATALOGS")
        catalogs = [row[0] for row in cursor.fetchall()]
        if PRESTO_CATALOG not in catalogs:
            pytest.skip(f"Presto catalog '{PRESTO_CATALOG}' not found")
        conn.close()

        conn = _presto_connect(catalog=PRESTO_CATALOG, schema=PRESTO_SCHEMA)
        cursor = conn.cursor()

        try:
            _execute(cursor, f"CREATE SCHEMA IF NOT EXISTS {PRESTO_CATALOG}.{PRESTO_SCHEMA}")
        except Exception:
            try:
                _execute(cursor, f"CREATE SCHEMA {PRESTO_CATALOG}.{PRESTO_SCHEMA}")
            except Exception:
                pass

        for stmt in [
            f"DROP VIEW IF EXISTS {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_user_emails",
            f"DROP TABLE IF EXISTS {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_users",
            f"DROP TABLE IF EXISTS {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_products",
        ]:
            try:
                _execute(cursor, stmt)
            except Exception:
                pass

        _execute(
            cursor,
            f"""
            CREATE TABLE {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_users (
                id INTEGER,
                name VARCHAR,
                email VARCHAR
            )
            """,
        )

        _execute(
            cursor,
            f"""
            CREATE TABLE {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_products (
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
            CREATE VIEW {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_user_emails AS
            SELECT id, name, email FROM {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_users WHERE email IS NOT NULL
            """,
        )

        _execute(
            cursor,
            f"""
            INSERT INTO {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
            """,
        )

        _execute(
            cursor,
            f"""
            INSERT INTO {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
            """,
        )

        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup Presto schema: {e}")

    yield PRESTO_CATALOG

    try:
        conn = _presto_connect(catalog=PRESTO_CATALOG, schema=PRESTO_SCHEMA)
        cursor = conn.cursor()
        for stmt in [
            f"DROP VIEW IF EXISTS {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_user_emails",
            f"DROP TABLE IF EXISTS {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_users",
            f"DROP TABLE IF EXISTS {PRESTO_CATALOG}.{PRESTO_SCHEMA}.test_products",
        ]:
            try:
                _execute(cursor, stmt)
            except Exception:
                pass
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def presto_connection(presto_db: str) -> str:
    """Create a sqlit CLI connection for Presto and clean up after test."""
    connection_name = f"test_presto_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "presto",
        "--name",
        connection_name,
        "--server",
        PRESTO_HOST,
        "--port",
        str(PRESTO_PORT),
        "--database",
        PRESTO_CATALOG,
        "--schema",
        PRESTO_SCHEMA,
        "--username",
        PRESTO_USER,
    ]
    if PRESTO_PASSWORD:
        args.extend(["--password", PRESTO_PASSWORD])
    else:
        args.extend(["--password", ""])
    if PRESTO_HTTP_SCHEME:
        args.extend(["--http-scheme", PRESTO_HTTP_SCHEME])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "PRESTO_CATALOG",
    "PRESTO_HOST",
    "PRESTO_HTTP_SCHEME",
    "PRESTO_PASSWORD",
    "PRESTO_PORT",
    "PRESTO_SCHEMA",
    "PRESTO_USER",
    "presto_available",
    "presto_connection",
    "presto_db",
    "presto_server_ready",
]
