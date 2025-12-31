"""Oracle fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# Oracle connection settings for Docker
ORACLE_HOST = os.environ.get("ORACLE_HOST", "localhost")
ORACLE_PORT = int(os.environ.get("ORACLE_PORT", "1521"))
ORACLE_USER = os.environ.get("ORACLE_USER", "testuser")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "TestPassword123!")
ORACLE_SERVICE = os.environ.get("ORACLE_SERVICE", "FREEPDB1")


def oracle_available() -> bool:
    """Check if Oracle is available."""
    return is_port_open(ORACLE_HOST, ORACLE_PORT)


@pytest.fixture(scope="session")
def oracle_server_ready() -> bool:
    """Check if Oracle is ready and return True/False."""
    if not oracle_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def oracle_db(oracle_server_ready: bool) -> str:
    """Set up Oracle test database."""
    if not oracle_server_ready:
        pytest.skip("Oracle is not available")

    try:
        import oracledb
    except ImportError:
        pytest.skip("oracledb is not installed")

    try:
        dsn = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
        conn = oracledb.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=dsn,
        )
        cursor = conn.cursor()

        # Oracle lacks `DROP TABLE IF EXISTS`; ignore "does not exist" errors.
        for table in ["test_users", "test_products"]:
            try:
                cursor.execute(f"DROP TABLE {table} CASCADE CONSTRAINTS")
            except oracledb.DatabaseError:
                pass  # Table doesn't exist

        try:
            cursor.execute("DROP VIEW test_user_emails")
        except oracledb.DatabaseError:
            pass

        cursor.execute("""
            CREATE TABLE test_users (
                id NUMBER PRIMARY KEY,
                name VARCHAR2(100) NOT NULL,
                email VARCHAR2(100)
            )
        """)

        cursor.execute("""
            CREATE TABLE test_products (
                id NUMBER PRIMARY KEY,
                name VARCHAR2(100) NOT NULL,
                price NUMBER(10,2) NOT NULL,
                stock NUMBER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """)

        cursor.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

        cursor.execute("""
            CREATE OR REPLACE TRIGGER trg_test_users_audit
            AFTER INSERT ON test_users
            BEGIN
                NULL;
            END;
        """)

        cursor.execute("CREATE SEQUENCE test_sequence START WITH 1 INCREMENT BY 1")

        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com')
        """)
        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (2, 'Bob', 'bob@example.com')
        """)
        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (3, 'Charlie', 'charlie@example.com')
        """)

        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100)
        """)
        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (2, 'Gadget', 19.99, 50)
        """)
        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (3, 'Gizmo', 29.99, 25)
        """)

        conn.commit()
        conn.close()
    except Exception as e:
        pytest.skip(f"Failed to setup Oracle database: {e}")

    yield ORACLE_SERVICE

    try:
        conn = oracledb.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}",
        )
        cursor = conn.cursor()

        for stmt in [
            "DROP VIEW test_user_emails",
            "DROP TABLE test_users CASCADE CONSTRAINTS",
            "DROP TABLE test_products CASCADE CONSTRAINTS",
            "DROP SEQUENCE test_sequence",
        ]:
            try:
                cursor.execute(stmt)
            except oracledb.DatabaseError:
                pass

        conn.commit()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def oracle_connection(oracle_db: str) -> str:
    """Create a sqlit CLI connection for Oracle and clean up after test."""
    connection_name = f"test_oracle_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "oracle",
        "--name",
        connection_name,
        "--server",
        ORACLE_HOST,
        "--port",
        str(ORACLE_PORT),
        "--database",
        oracle_db,
        "--username",
        ORACLE_USER,
        "--password",
        ORACLE_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "ORACLE_HOST",
    "ORACLE_PASSWORD",
    "ORACLE_PORT",
    "ORACLE_SERVICE",
    "ORACLE_USER",
    "oracle_available",
    "oracle_connection",
    "oracle_db",
    "oracle_server_ready",
]
