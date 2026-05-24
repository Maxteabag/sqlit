"""Impala fixtures."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest

from tests.fixtures.utils import cleanup_connection, is_binary_port_open, run_cli

IMPALA_HOST = os.environ.get("IMPALA_HOST", "localhost")
IMPALA_PORT = int(os.environ.get("IMPALA_PORT", "21050"))
IMPALA_DATABASE = os.environ.get("IMPALA_DATABASE", "test_sqlit")
IMPALA_AUTH_MECHANISM = os.environ.get("IMPALA_AUTH_MECHANISM", "NOSASL")


def impala_available() -> bool:
    """Check if Impala is available."""
    return is_binary_port_open(IMPALA_HOST, IMPALA_PORT)


@pytest.fixture(scope="session")
def impala_server_ready() -> bool:
    """Check if Impala is ready and return True/False."""
    if not impala_available():
        return False

    # Impala's catalog/statestore take a while to settle even after the HS2 port
    # opens. Give it a moment so the first CREATE DATABASE doesn't race.
    time.sleep(5)
    return True


@pytest.fixture(scope="function")
def impala_db(impala_server_ready: bool) -> Iterator[str]:
    """Set up Impala test database and tables.

    Impala has some quirks compared to classic RDBMSes:
      * No UPDATE/DELETE on plain text/parquet tables.
      * Tables need a file format; we use STORED AS PARQUET.
      * Indexes/triggers/sequences don't exist; those base tests are gated by
        adapter capabilities and should be skipped automatically.
    """
    if not impala_server_ready:
        pytest.skip("Impala is not available")

    try:
        from impala.dbapi import connect as impala_connect
    except ImportError:
        pytest.skip("impyla is not installed")

    try:
        conn = impala_connect(
            host=IMPALA_HOST,
            port=IMPALA_PORT,
            auth_mechanism=IMPALA_AUTH_MECHANISM,
        )
    except Exception as e:
        pytest.skip(f"cannot connect to Impala: {e}")

    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {IMPALA_DATABASE}")
        cursor.execute(f"USE {IMPALA_DATABASE}")

        # Reset tables so each test starts clean. Impala can't TRUNCATE text
        # tables reliably, so drop and recreate.
        for stmt in [
            "DROP VIEW IF EXISTS test_user_emails",
            "DROP TABLE IF EXISTS test_users",
            "DROP TABLE IF EXISTS test_products",
        ]:
            try:
                cursor.execute(stmt)
            except Exception:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_users (
                id INT,
                name STRING,
                email STRING
            )
            STORED AS PARQUET
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_products (
                id INT,
                name STRING,
                price DECIMAL(10,2),
                stock INT
            )
            STORED AS PARQUET
        """)

        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
        """)

        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', CAST(9.99 AS DECIMAL(10,2)), 100),
            (2, 'Gadget', CAST(19.99 AS DECIMAL(10,2)), 50),
            (3, 'Gizmo', CAST(29.99 AS DECIMAL(10,2)), 25)
        """)

        cursor.execute("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """)
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        pytest.skip(f"Failed to setup Impala database: {e}")
    finally:
        try:
            cursor.close()
        except Exception:
            pass

    try:
        conn.close()
    except Exception:
        pass

    yield IMPALA_DATABASE

    try:
        conn = impala_connect(
            host=IMPALA_HOST,
            port=IMPALA_PORT,
            auth_mechanism=IMPALA_AUTH_MECHANISM,
        )
        cursor = conn.cursor()
        try:
            cursor.execute(f"USE {IMPALA_DATABASE}")
            for stmt in [
                "DROP TABLE IF EXISTS test_users",
                "DROP TABLE IF EXISTS test_products",
            ]:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass
        finally:
            cursor.close()
            conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def impala_connection(impala_db: str) -> Iterator[str]:
    """Create a sqlit CLI connection for Impala and clean up after test."""
    connection_name = f"test_impala_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "impala",
        "--name",
        connection_name,
        "--server",
        IMPALA_HOST,
        "--port",
        str(IMPALA_PORT),
        "--database",
        impala_db,
        "--auth-mechanism",
        IMPALA_AUTH_MECHANISM,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "IMPALA_AUTH_MECHANISM",
    "IMPALA_DATABASE",
    "IMPALA_HOST",
    "IMPALA_PORT",
    "impala_available",
    "impala_connection",
    "impala_db",
    "impala_server_ready",
]
