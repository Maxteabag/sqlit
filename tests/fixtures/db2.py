"""IBM Db2 fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

DB2_HOST = os.environ.get("DB2_HOST", "localhost")
DB2_PORT = int(os.environ.get("DB2_PORT", "50000"))
DB2_USER = os.environ.get("DB2_USER", "db2inst1")
DB2_PASSWORD = os.environ.get("DB2_PASSWORD", "TestPassword123!")
DB2_DATABASE = os.environ.get("DB2_DATABASE", "testdb")


def db2_available() -> bool:
    """Check if Db2 is available."""
    return is_port_open(DB2_HOST, DB2_PORT)


@pytest.fixture(scope="session")
def db2_server_ready() -> bool:
    """Check if Db2 is ready and return True/False."""
    if not db2_available():
        return False

    time.sleep(5)
    return True


@pytest.fixture(scope="function")
def db2_db(db2_server_ready: bool) -> str:
    """Set up Db2 test database."""
    if not db2_server_ready:
        pytest.skip("Db2 is not available")

    try:
        import ibm_db_dbi
    except ImportError:
        pytest.skip("ibm_db is not installed")

    try:
        conn_str = (
            f"DATABASE={DB2_DATABASE};"
            f"HOSTNAME={DB2_HOST};"
            f"PORT={DB2_PORT};"
            "PROTOCOL=TCPIP;"
            f"UID={DB2_USER};"
            f"PWD={DB2_PASSWORD};"
        )
        conn = ibm_db_dbi.connect(conn_str, "", "")
        cursor = conn.cursor()
        try:
            cursor.execute(f"SET CURRENT SCHEMA = {DB2_USER.upper()}")
        except Exception:
            pass

        for stmt in [
            "DROP VIEW test_user_emails",
            "DROP TRIGGER trg_test_users_audit",
            "DROP TABLE test_users",
            "DROP TABLE test_products",
            "DROP SEQUENCE test_sequence",
        ]:
            try:
                cursor.execute(stmt)
            except Exception:
                pass

        cursor.execute("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100)
            )
        """)

        cursor.execute("""
            CREATE TABLE test_products (
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
            CREATE TRIGGER trg_test_users_audit
            NO CASCADE BEFORE INSERT ON test_users
            REFERENCING NEW AS n
            FOR EACH ROW
            BEGIN ATOMIC
                SET n.name = n.name;
            END
        """)

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

    except Exception as e:
        pytest.skip(f"Failed to setup Db2 database: {e}")

    yield DB2_DATABASE

    try:
        conn = ibm_db_dbi.connect(conn_str, "", "")
        cursor = conn.cursor()
        try:
            cursor.execute(f"SET CURRENT SCHEMA = {DB2_USER.upper()}")
        except Exception:
            pass
        for stmt in [
            "DROP VIEW test_user_emails",
            "DROP TRIGGER trg_test_users_audit",
            "DROP TABLE test_users",
            "DROP TABLE test_products",
            "DROP SEQUENCE test_sequence",
        ]:
            try:
                cursor.execute(stmt)
            except Exception:
                pass
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def db2_connection(db2_db: str) -> str:
    """Create a sqlit CLI connection for Db2 and clean up after test."""
    connection_name = f"test_db2_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "db2",
        "--name",
        connection_name,
        "--server",
        DB2_HOST,
        "--port",
        str(DB2_PORT),
        "--database",
        db2_db,
        "--username",
        DB2_USER,
        "--password",
        DB2_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "DB2_DATABASE",
    "DB2_HOST",
    "DB2_PASSWORD",
    "DB2_PORT",
    "DB2_USER",
    "db2_available",
    "db2_connection",
    "db2_db",
    "db2_server_ready",
]
