"""Oracle 11g legacy fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

ORACLE11G_HOST = os.environ.get("ORACLE11G_HOST", "localhost")
ORACLE11G_PORT = int(os.environ.get("ORACLE11G_PORT", "1522"))
ORACLE11G_USER = os.environ.get("ORACLE11G_USER", "system")
ORACLE11G_PASSWORD = os.environ.get("ORACLE11G_PASSWORD", "oracle")
ORACLE11G_SERVICE = os.environ.get("ORACLE11G_SERVICE", "XE")
ORACLE11G_CLIENT_MODE = os.environ.get("ORACLE11G_CLIENT_MODE", "thick")
ORACLE11G_CLIENT_LIB_DIR = os.environ.get("ORACLE11G_CLIENT_LIB_DIR", "")
ORACLE11G_RUN_TESTS = os.environ.get("ORACLE11G_RUN_TESTS", "").strip().lower() in {"1", "true", "yes"}


def oracle11g_available() -> bool:
    """Check if Oracle 11g is available."""
    if not ORACLE11G_RUN_TESTS:
        return False
    return is_port_open(ORACLE11G_HOST, ORACLE11G_PORT)


def _init_oracle_client(oracledb) -> None:
    mode = ORACLE11G_CLIENT_MODE.strip().lower() or "thick"
    if mode == "thin":
        pytest.skip("Oracle 11g requires thick client mode")
    try:
        if ORACLE11G_CLIENT_LIB_DIR:
            oracledb.init_oracle_client(lib_dir=ORACLE11G_CLIENT_LIB_DIR)
        else:
            oracledb.init_oracle_client()
    except Exception as exc:
        message = str(exc).lower()
        if "already initialized" in message:
            return
        pytest.skip(f"Oracle thick client initialization failed: {exc}")


@pytest.fixture(scope="session")
def oracle11g_server_ready() -> bool:
    """Check if Oracle 11g is ready and return True/False."""
    if not oracle11g_available():
        return False

    time.sleep(3)
    return True


@pytest.fixture(scope="function")
def oracle11g_db(oracle11g_server_ready: bool) -> str:
    """Set up Oracle 11g test schema."""
    if not ORACLE11G_RUN_TESTS:
        pytest.skip("Oracle 11g tests are disabled. Set ORACLE11G_RUN_TESTS=1 to enable.")
    if not oracle11g_server_ready:
        pytest.skip("Oracle 11g is not available")

    try:
        import oracledb
    except ImportError:
        pytest.skip("oracledb is not installed")

    _init_oracle_client(oracledb)

    try:
        dsn = f"{ORACLE11G_HOST}:{ORACLE11G_PORT}/{ORACLE11G_SERVICE}"
        conn = oracledb.connect(
            user=ORACLE11G_USER,
            password=ORACLE11G_PASSWORD,
            dsn=dsn,
        )
        cursor = conn.cursor()

        for table in ["test_users", "test_products"]:
            try:
                cursor.execute(f"DROP TABLE {table} CASCADE CONSTRAINTS")
            except oracledb.DatabaseError:
                pass

        try:
            cursor.execute("DROP VIEW test_user_emails")
        except oracledb.DatabaseError:
            pass

        try:
            cursor.execute("DROP SEQUENCE test_sequence")
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
        pytest.skip(f"Failed to setup Oracle 11g database: {e}")

    yield ORACLE11G_SERVICE

    try:
        conn = oracledb.connect(
            user=ORACLE11G_USER,
            password=ORACLE11G_PASSWORD,
            dsn=f"{ORACLE11G_HOST}:{ORACLE11G_PORT}/{ORACLE11G_SERVICE}",
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
def oracle11g_connection(oracle11g_db: str) -> str:
    """Create a sqlit CLI connection for Oracle 11g and clean up after test."""
    connection_name = f"test_oracle11g_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "oracle_legacy",
        "--name",
        connection_name,
        "--server",
        ORACLE11G_HOST,
        "--port",
        str(ORACLE11G_PORT),
        "--database",
        oracle11g_db,
        "--username",
        ORACLE11G_USER,
        "--password",
        ORACLE11G_PASSWORD,
        "--oracle-client-mode",
        ORACLE11G_CLIENT_MODE,
    ]
    if ORACLE11G_CLIENT_LIB_DIR:
        args.extend(["--oracle-client-lib-dir", ORACLE11G_CLIENT_LIB_DIR])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "ORACLE11G_CLIENT_LIB_DIR",
    "ORACLE11G_CLIENT_MODE",
    "ORACLE11G_HOST",
    "ORACLE11G_PASSWORD",
    "ORACLE11G_PORT",
    "ORACLE11G_SERVICE",
    "ORACLE11G_USER",
    "oracle11g_available",
    "oracle11g_connection",
    "oracle11g_db",
    "oracle11g_server_ready",
]
