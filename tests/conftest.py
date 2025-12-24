"""Pytest fixtures for sqlit integration tests."""

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

_TEST_CONFIG_DIR = Path(tempfile.mkdtemp(prefix="sqlit-test-config-"))
os.environ.setdefault("SQLIT_CONFIG_DIR", str(_TEST_CONFIG_DIR))

# Enable plaintext credential storage for tests (no keyring in CI)
_settings_file = _TEST_CONFIG_DIR / "settings.json"
_settings_file.write_text('{"allow_plaintext_credentials": true}')


@pytest.fixture(autouse=True)
def _reset_mock_docker_containers():
    """Ensure mock Docker containers do not leak between tests."""
    from sqlit.mock_settings import set_mock_docker_containers

    set_mock_docker_containers(None)
    yield
    set_mock_docker_containers(None)


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    """Wait for a TCP port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(host, port):
            return True
        time.sleep(1)
    return False


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run sqlit CLI command and return result."""
    cmd = ["python", "-m", "sqlit.cli"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        stderr_clean = "\n".join(
            line
            for line in result.stderr.split("\n")
            if "RuntimeWarning" not in line and "unpredictable behaviour" not in line
        ).strip()
        if stderr_clean:
            raise RuntimeError(f"CLI command failed: {stderr_clean}")
    return result


def cleanup_connection(name: str) -> None:
    """Delete a connection if it exists, ignoring errors."""
    try:
        run_cli("connection", "delete", name, check=False)
    except Exception:
        pass


@pytest.fixture(scope="function")
def sqlite_db_path(tmp_path: Path) -> Path:
    """Create a temporary SQLite database file path."""
    return tmp_path / "test_database.db"


@pytest.fixture(scope="function")
def sqlite_db(sqlite_db_path: Path) -> Path:
    """Create a temporary SQLite database with test data."""
    conn = sqlite3.connect(sqlite_db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0
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
        BEGIN
            SELECT 1;
        END
    """)

    cursor.executemany(
        "INSERT INTO test_users (id, name, email) VALUES (?, ?, ?)",
        [
            (1, "Alice", "alice@example.com"),
            (2, "Bob", "bob@example.com"),
            (3, "Charlie", "charlie@example.com"),
        ],
    )

    cursor.executemany(
        "INSERT INTO test_products (id, name, price, stock) VALUES (?, ?, ?, ?)",
        [
            (1, "Widget", 9.99, 100),
            (2, "Gadget", 19.99, 50),
            (3, "Gizmo", 29.99, 25),
        ],
    )

    conn.commit()
    conn.close()

    return sqlite_db_path


@pytest.fixture(scope="function")
def sqlite_connection(sqlite_db: Path) -> str:
    """Create a sqlit CLI connection for SQLite and clean up after test."""
    connection_name = f"test_sqlite_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "sqlite",
        "--name",
        connection_name,
        "--file-path",
        str(sqlite_db),
    )

    yield connection_name

    cleanup_connection(connection_name)


MSSQL_HOST = os.environ.get("MSSQL_HOST", "localhost")
MSSQL_PORT = int(os.environ.get("MSSQL_PORT", "1433"))
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


POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.environ.get("POSTGRES_USER", "testuser")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "TestPassword123!")
POSTGRES_DATABASE = os.environ.get("POSTGRES_DATABASE", "test_sqlit")


def postgres_available() -> bool:
    """Check if PostgreSQL is available."""
    return is_port_open(POSTGRES_HOST, POSTGRES_PORT)


@pytest.fixture(scope="session")
def postgres_server_ready() -> bool:
    """Check if PostgreSQL is ready and return True/False."""
    if not postgres_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def postgres_db(postgres_server_ready: bool) -> str:
    """Set up PostgreSQL test database."""
    if not postgres_server_ready:
        pytest.skip("PostgreSQL is not available")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed")

    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")

        cursor.execute("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
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

        # Create test index for integration tests
        cursor.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

        # Create test trigger for integration tests
        cursor.execute("""
            CREATE OR REPLACE FUNCTION test_audit_func() RETURNS TRIGGER AS $$
            BEGIN
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        cursor.execute("""
            CREATE TRIGGER trg_test_users_audit
            AFTER INSERT ON test_users
            FOR EACH ROW EXECUTE FUNCTION test_audit_func()
        """)

        # Create test sequence for integration tests
        cursor.execute("CREATE SEQUENCE test_sequence START 1")

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
        pytest.skip(f"Failed to setup PostgreSQL database: {e}")

    yield POSTGRES_DATABASE

    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        cursor.execute("DROP SEQUENCE IF EXISTS test_sequence")
        cursor.execute("DROP FUNCTION IF EXISTS test_audit_func")
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def postgres_connection(postgres_db: str) -> str:
    """Create a sqlit CLI connection for PostgreSQL and clean up after test."""
    connection_name = f"test_postgres_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "postgresql",
        "--name",
        connection_name,
        "--server",
        POSTGRES_HOST,
        "--port",
        str(POSTGRES_PORT),
        "--database",
        postgres_db,
        "--username",
        POSTGRES_USER,
        "--password",
        POSTGRES_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


FIREBIRD_HOST = os.environ.get("FIREBIRD_HOST", "localhost")
FIREBIRD_PORT = int(os.environ.get("FIREBIRD_PORT", "3050"))
FIREBIRD_USER = os.environ.get("FIREBIRD_USER", "testuser")
FIREBIRD_PASSWORD = os.environ.get("FIREBIRD_PASSWORD", "TestPassword123!")
FIREBIRD_DATABASE = os.environ.get("FIREBIRD_DATABASE", "/var/lib/firebird/data/test_sqlit.fdb")


def firebird_available() -> bool:
    """Check if Firebird is available."""
    return is_port_open(FIREBIRD_HOST, FIREBIRD_PORT)


@pytest.fixture(scope="session")
def firebird_server_ready() -> bool:
    """Check if Firebird is ready and return True/False."""
    if not firebird_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def firebird_db(firebird_server_ready: bool) -> str:
    """Set up Firebird test database."""
    if not firebird_server_ready:
        pytest.skip("Firebird is not available")

    try:
        import firebirdsql
    except ImportError:
        pytest.skip("firebirdsql is not installed")

    try:
        conn = firebirdsql.connect(
            host=FIREBIRD_HOST,
            port=FIREBIRD_PORT,
            database=FIREBIRD_DATABASE,
            user=FIREBIRD_USER,
            password=FIREBIRD_PASSWORD,
        )
    except Exception as e:
        pytest.skip(f"cannot connect to database: {e}")

    cursor = conn.cursor()
    try:
        for cleanup in [
            "DROP VIEW test_user_emails",
        ]:
            try:
                cursor.execute(cleanup)
            except firebirdsql.DatabaseError:
                pass
        conn.commit()

        cursor.execute("""
            RECREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
            )
        """)

        cursor.execute("""
            RECREATE TABLE test_products (
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
            RECREATE TRIGGER trg_test_users_audit FOR test_users
            BEFORE INSERT
            AS
            BEGIN
                NEW.email = LOWER(NEW.email);
            END
        """)

        cursor.execute("RECREATE GENERATOR test_sequence START WITH 1 INCREMENT 1")

        conn.commit()

        # Firebird doesn't support bulk inserts with VALUES
        for insert in [
            "INSERT INTO test_users (id, name, email) VALUES (1, 'Alice', 'alice@example.com')",
            "INSERT INTO test_users (id, name, email) VALUES (2, 'Bob', 'bob@example.com')",
            "INSERT INTO test_users (id, name, email) VALUES (3, 'Charlie', 'charlie@example.com')",
            "INSERT INTO test_products (id, name, price, stock) VALUES (1, 'Widget', 9.99, 100)",
            "INSERT INTO test_products (id, name, price, stock) VALUES (2, 'Gadget', 19.99, 50)",
            "INSERT INTO test_products (id, name, price, stock) VALUES (3, 'Gizmo', 29.99, 25)",
        ]:
            cursor.execute(insert)

        conn.commit()
    except Exception as e:
        pytest.skip(f"Failed to setup Firebird database: {e}")
    finally:
        conn.close()

    yield FIREBIRD_DATABASE

    try:
        conn = firebirdsql.connect(
            host=FIREBIRD_HOST,
            port=FIREBIRD_PORT,
            database=FIREBIRD_DATABASE,
            user=FIREBIRD_USER,
            password=FIREBIRD_PASSWORD,
        )
    except Exception as e:
        pytest.skip(f"Failed to connect to Firebird database for teardown: {e}")

    cursor = conn.cursor()
    try:
        for cleanup in [
            "DROP VIEW test_user_emails",
            "DROP TABLE test_users",
            "DROP TABLE test_products",
            "DROP TRIGGER trg_test_users_audit",
            "DROP SEQUENCE test_sequence",
        ]:
            try:
                cursor.execute(cleanup)
            except firebirdsql.DatabaseError:
                pass
    finally:
        conn.commit()
        conn.close()


@pytest.fixture(scope="function")
def firebird_connection(firebird_db: str) -> str:
    """Create a sqlit CLI connection for Firebird and clean up after test."""
    connection_name = f"test_firebird_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "firebird",
        "--name",
        connection_name,
        "--server",
        FIREBIRD_HOST,
        "--port",
        str(FIREBIRD_PORT),
        "--database",
        firebird_db,
        "--username",
        FIREBIRD_USER,
        "--password",
        FIREBIRD_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


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
        import mysql.connector
    except ImportError:
        pytest.skip("mysql-connector-python is not installed")

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            connection_timeout=10,
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
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DATABASE,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            connection_timeout=10,
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


# =============================================================================
# Oracle Fixtures
# =============================================================================

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

        # Create test index for integration tests
        cursor.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

        # Create test trigger for integration tests
        cursor.execute("""
            CREATE OR REPLACE TRIGGER trg_test_users_audit
            AFTER INSERT ON test_users
            FOR EACH ROW
            BEGIN
                NULL;
            END;
        """)

        # Create test sequence for integration tests
        cursor.execute("CREATE SEQUENCE test_sequence START WITH 1 INCREMENT BY 1")

        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES (1, 'Alice', 'alice@example.com')
        """)
        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES (2, 'Bob', 'bob@example.com')
        """)
        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES (3, 'Charlie', 'charlie@example.com')
        """)

        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES (1, 'Widget', 9.99, 100)
        """)
        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES (2, 'Gadget', 19.99, 50)
        """)
        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES (3, 'Gizmo', 29.99, 25)
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


# =============================================================================
# MariaDB Fixtures
# =============================================================================

# Note: Using 127.0.0.1 instead of localhost to force TCP connection (localhost uses Unix socket)
MARIADB_HOST = os.environ.get("MARIADB_HOST", "127.0.0.1")
MARIADB_PORT = int(os.environ.get("MARIADB_PORT", "3307"))
MARIADB_USER = os.environ.get("MARIADB_USER", "root")
MARIADB_PASSWORD = os.environ.get("MARIADB_PASSWORD", "TestPassword123!")
MARIADB_DATABASE = os.environ.get("MARIADB_DATABASE", "test_sqlit")


def mariadb_available() -> bool:
    """Check if MariaDB is available."""
    return is_port_open(MARIADB_HOST, MARIADB_PORT)


@pytest.fixture(scope="session")
def mariadb_server_ready() -> bool:
    """Check if MariaDB is ready and return True/False."""
    if not mariadb_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def mariadb_db(mariadb_server_ready: bool) -> str:
    """Set up MariaDB test database."""
    if not mariadb_server_ready:
        pytest.skip("MariaDB is not available")

    try:
        import mariadb
    except ImportError:
        pytest.skip("mariadb is not installed")

    try:
        conn = mariadb.connect(
            host=MARIADB_HOST,
            port=MARIADB_PORT,
            database=MARIADB_DATABASE,
            user=MARIADB_USER,
            password=MARIADB_PASSWORD,
            connect_timeout=10,
        )
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS test_users")
        cursor.execute("DROP TABLE IF EXISTS test_products")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        cursor.execute("DROP SEQUENCE IF EXISTS test_sequence")

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

        # Create test sequence for integration tests (MariaDB 10.3+)
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
        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup MariaDB database: {e}")

    yield MARIADB_DATABASE

    try:
        conn = mariadb.connect(
            host=MARIADB_HOST,
            port=MARIADB_PORT,
            database=MARIADB_DATABASE,
            user=MARIADB_USER,
            password=MARIADB_PASSWORD,
            connect_timeout=10,
        )
        cursor = conn.cursor()
        cursor.execute("DROP TRIGGER IF EXISTS trg_test_users_audit")
        cursor.execute("DROP TABLE IF EXISTS test_users")
        cursor.execute("DROP TABLE IF EXISTS test_products")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        cursor.execute("DROP SEQUENCE IF EXISTS test_sequence")
        conn.commit()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def mariadb_connection(mariadb_db: str) -> str:
    """Create a sqlit CLI connection for MariaDB and clean up after test."""
    connection_name = f"test_mariadb_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mariadb",
        "--name",
        connection_name,
        "--server",
        MARIADB_HOST,
        "--port",
        str(MARIADB_PORT),
        "--database",
        mariadb_db,
        "--username",
        MARIADB_USER,
        "--password",
        MARIADB_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


# =============================================================================
# DuckDB Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def duckdb_db_path(tmp_path: Path) -> Path:
    """Create a temporary DuckDB database file path."""
    return tmp_path / "test_database.duckdb"


@pytest.fixture(scope="function")
def duckdb_db(duckdb_db_path: Path) -> Path:
    """Create a temporary DuckDB database with test data."""
    try:
        import duckdb
    except ImportError:
        pytest.skip("duckdb is not installed")

    conn = duckdb.connect(str(duckdb_db_path))

    conn.execute("""
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            email VARCHAR UNIQUE
        )
    """)

    conn.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            price DECIMAL(10,2) NOT NULL,
            stock INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE VIEW test_user_emails AS
        SELECT id, name, email FROM test_users WHERE email IS NOT NULL
    """)

    # Create test index for integration tests
    conn.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

    # Create test sequence for integration tests
    conn.execute("CREATE SEQUENCE test_sequence START 1")

    # Note: DuckDB doesn't support triggers

    conn.execute("""
        INSERT INTO test_users (id, name, email) VALUES
        (1, 'Alice', 'alice@example.com'),
        (2, 'Bob', 'bob@example.com'),
        (3, 'Charlie', 'charlie@example.com')
    """)

    conn.execute("""
        INSERT INTO test_products (id, name, price, stock) VALUES
        (1, 'Widget', 9.99, 100),
        (2, 'Gadget', 19.99, 50),
        (3, 'Gizmo', 29.99, 25)
    """)

    conn.close()

    return duckdb_db_path


@pytest.fixture(scope="function")
def duckdb_connection(duckdb_db: Path) -> str:
    """Create a sqlit CLI connection for DuckDB and clean up after test."""
    connection_name = f"test_duckdb_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "duckdb",
        "--name",
        connection_name,
        "--file-path",
        str(duckdb_db),
    )

    yield connection_name

    cleanup_connection(connection_name)


# =============================================================================
# CockroachDB Fixtures
# =============================================================================

# CockroachDB connection settings for Docker
COCKROACHDB_HOST = os.environ.get("COCKROACHDB_HOST", "localhost")
COCKROACHDB_PORT = int(os.environ.get("COCKROACHDB_PORT", "26257"))
COCKROACHDB_USER = os.environ.get("COCKROACHDB_USER", "root")
COCKROACHDB_PASSWORD = os.environ.get("COCKROACHDB_PASSWORD", "")
COCKROACHDB_DATABASE = os.environ.get("COCKROACHDB_DATABASE", "test_sqlit")


def cockroachdb_available() -> bool:
    """Check if CockroachDB is available."""
    return is_port_open(COCKROACHDB_HOST, COCKROACHDB_PORT)


@pytest.fixture(scope="session")
def cockroachdb_server_ready() -> bool:
    """Check if CockroachDB is ready and return True/False."""
    if not cockroachdb_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def cockroachdb_db(cockroachdb_server_ready: bool) -> str:
    """Set up CockroachDB test database."""
    if not cockroachdb_server_ready:
        pytest.skip("CockroachDB is not available")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed")

    try:
        conn = psycopg2.connect(
            host=COCKROACHDB_HOST,
            port=COCKROACHDB_PORT,
            database="defaultdb",
            user=COCKROACHDB_USER,
            password=COCKROACHDB_PASSWORD or None,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Database creation requires a connection to an existing DB (e.g. `defaultdb`).
        cursor.execute(f"DROP DATABASE IF EXISTS {COCKROACHDB_DATABASE}")
        cursor.execute(f"CREATE DATABASE {COCKROACHDB_DATABASE}")
        conn.close()

        conn = psycopg2.connect(
            host=COCKROACHDB_HOST,
            port=COCKROACHDB_PORT,
            database=COCKROACHDB_DATABASE,
            user=COCKROACHDB_USER,
            password=COCKROACHDB_PASSWORD or None,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

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

        # Create test sequence for integration tests
        cursor.execute("CREATE SEQUENCE test_sequence START 1")

        # Create test trigger for integration tests (CockroachDB 24.3+)
        # Note: CockroachDB has limited trigger support, using simple AFTER trigger
        try:
            cursor.execute("""
                CREATE OR REPLACE FUNCTION test_audit_func() RETURNS TRIGGER AS $$
                BEGIN
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            cursor.execute("""
                CREATE TRIGGER trg_test_users_audit
                AFTER INSERT ON test_users
                FOR EACH ROW EXECUTE FUNCTION test_audit_func()
            """)
        except Exception:
            pass  # Triggers may not be supported in older CockroachDB versions

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
        pytest.skip(f"Failed to setup CockroachDB database: {e}")

    yield COCKROACHDB_DATABASE

    try:
        conn = psycopg2.connect(
            host=COCKROACHDB_HOST,
            port=COCKROACHDB_PORT,
            database="defaultdb",
            user=COCKROACHDB_USER,
            password=COCKROACHDB_PASSWORD or None,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS {COCKROACHDB_DATABASE}")
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def cockroachdb_connection(cockroachdb_db: str) -> str:
    """Create a sqlit CLI connection for CockroachDB and clean up after test."""
    connection_name = f"test_cockroachdb_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "cockroachdb",
        "--name",
        connection_name,
        "--server",
        COCKROACHDB_HOST,
        "--port",
        str(COCKROACHDB_PORT),
        "--database",
        cockroachdb_db,
        "--username",
        COCKROACHDB_USER,
    ]
    if COCKROACHDB_PASSWORD:
        args.extend(["--password", COCKROACHDB_PASSWORD])
    else:
        args.extend(["--password", ""])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


# =============================================================================
# Turso (libSQL) Fixtures
# =============================================================================

# Turso connection settings for Docker (libsql-server)
TURSO_HOST = os.environ.get("TURSO_HOST", "localhost")
TURSO_PORT = int(os.environ.get("TURSO_PORT", "8081"))


def turso_available() -> bool:
    """Check if Turso (libsql-server) is available."""
    return is_port_open(TURSO_HOST, TURSO_PORT)


@pytest.fixture(scope="session")
def turso_server_ready() -> bool:
    """Check if Turso is ready and return True/False."""
    if not turso_available():
        return False

    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def turso_db(turso_server_ready: bool) -> str:
    """Set up Turso test database."""
    if not turso_server_ready:
        pytest.skip("Turso (libsql-server) is not available")

    try:
        from libsql import connect
    except ImportError:
        pytest.skip("libsql is not installed")

    turso_url = f"http://{TURSO_HOST}:{TURSO_PORT}"

    try:
        client = connect(turso_url)

        client.execute("DROP TABLE IF EXISTS test_users")
        client.execute("DROP TABLE IF EXISTS test_products")
        client.execute("DROP VIEW IF EXISTS test_user_emails")

        client.execute("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            )
        """)

        client.execute("""
            CREATE TABLE test_products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER DEFAULT 0
            )
        """)

        client.execute("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """)

        # Create test index for integration tests
        client.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

        # Create test trigger for integration tests
        client.execute("""
            CREATE TRIGGER trg_test_users_audit
            AFTER INSERT ON test_users
            BEGIN
                SELECT 1;
            END
        """)

        # Note: Turso (libSQL/SQLite) doesn't support sequences

        client.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
        """)

        client.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
        """)

        client.close()

    except Exception as e:
        pytest.skip(f"Failed to setup Turso database: {e}")

    yield turso_url

    try:
        client = connect(turso_url)
        client.execute("DROP TRIGGER IF EXISTS trg_test_users_audit")
        client.execute("DROP INDEX IF EXISTS idx_test_users_email")
        client.execute("DROP TABLE IF EXISTS test_users")
        client.execute("DROP TABLE IF EXISTS test_products")
        client.execute("DROP VIEW IF EXISTS test_user_emails")
        client.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def turso_connection(turso_db: str) -> str:
    """Create a sqlit CLI connection for Turso and clean up after test."""
    connection_name = f"test_turso_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "turso",
        "--name",
        connection_name,
        "--server",
        turso_db,
        "--password",
        "",  # No auth token for local server.
    )

    yield connection_name

    cleanup_connection(connection_name)


# =============================================================================
# D1 Fixtures
# =============================================================================

# D1 connection settings for Docker (miniflare)
D1_HOST = os.environ.get("D1_HOST", "localhost")
D1_PORT = int(os.environ.get("D1_PORT", "8787"))
D1_ACCOUNT_ID = "test-account"
D1_DATABASE = "test-d1"
D1_API_TOKEN = "test-token"
os.environ["D1_API_BASE_URL"] = f"http://{D1_HOST}:{D1_PORT}"


def d1_available() -> bool:
    """Check if D1 (miniflare) is available."""
    return is_port_open(D1_HOST, D1_PORT)


@pytest.fixture(scope="session")
def d1_server_ready() -> bool:
    """Check if D1 is ready and return True/False."""
    if not d1_available():
        return False
    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def d1_db(d1_server_ready: bool) -> str:
    """Set up D1 test database."""
    if not d1_server_ready:
        pytest.skip("D1 (miniflare) is not available")

    from sqlit.db.adapters.d1 import D1Adapter

    adapter = D1Adapter()
    config = {
        "name": "d1-temp-setup",
        "db_type": "d1",
        "server": D1_ACCOUNT_ID,
        "password": D1_API_TOKEN,
        "database": D1_DATABASE,
    }
    from sqlit.config import ConnectionConfig

    conn_config = ConnectionConfig(**config)
    try:
        conn = adapter.connect(conn_config)

        adapter.execute_non_query(conn, "DROP TABLE IF EXISTS test_users")
        adapter.execute_non_query(conn, "DROP TABLE IF EXISTS test_products")
        adapter.execute_non_query(conn, "DROP VIEW IF EXISTS test_user_emails")

        adapter.execute_non_query(
            conn,
            """
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            )
        """,
        )
        adapter.execute_non_query(
            conn,
            """
            CREATE TABLE test_products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER DEFAULT 0
            )
        """,
        )
        adapter.execute_non_query(
            conn,
            """
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """,
        )

        # Create test index for integration tests
        adapter.execute_non_query(conn, "CREATE INDEX idx_test_users_email ON test_users(email)")

        # Create test trigger for integration tests
        adapter.execute_non_query(
            conn,
            """
            CREATE TRIGGER trg_test_users_audit
            AFTER INSERT ON test_users
            BEGIN
                SELECT 1;
            END
        """,
        )

        # Note: D1 (SQLite-based) doesn't support sequences

        adapter.execute_non_query(
            conn,
            "INSERT INTO test_users (id, name, email) VALUES (1, 'Alice', 'alice@example.com')",
        )
        adapter.execute_non_query(
            conn,
            "INSERT INTO test_users (id, name, email) VALUES (2, 'Bob', 'bob@example.com')",
        )
        adapter.execute_non_query(
            conn,
            "INSERT INTO test_users (id, name, email) VALUES (3, 'Charlie', 'charlie@example.com')",
        )
        adapter.execute_non_query(
            conn,
            "INSERT INTO test_products (id, name, price, stock) VALUES (1, 'Widget', 9.99, 100)",
        )
        adapter.execute_non_query(
            conn,
            "INSERT INTO test_products (id, name, price, stock) VALUES (2, 'Gadget', 19.99, 50)",
        )
        adapter.execute_non_query(
            conn,
            "INSERT INTO test_products (id, name, price, stock) VALUES (3, 'Gizmo', 29.99, 25)",
        )
    except Exception as e:
        pytest.skip(f"Failed to setup D1 database: {e}")

    yield D1_DATABASE


@pytest.fixture(scope="function")
def d1_connection(d1_db: str) -> str:
    """Create a sqlit CLI connection for D1 and clean up after test."""
    connection_name = f"test_d1_{os.getpid()}"
    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "d1",
        "--name",
        connection_name,
        "--host",
        D1_ACCOUNT_ID,
        "--password",
        D1_API_TOKEN,
        "--database",
        d1_db,
    )

    yield connection_name
    cleanup_connection(connection_name)


# =============================================================================
# ClickHouse Fixtures
# =============================================================================

CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "test_sqlit")


def clickhouse_available() -> bool:
    """Check if ClickHouse is available."""
    return is_port_open(CLICKHOUSE_HOST, CLICKHOUSE_PORT)


@pytest.fixture(scope="session")
def clickhouse_server_ready() -> bool:
    """Check if ClickHouse is ready and return True/False."""
    if not clickhouse_available():
        return False

    time.sleep(2)
    return True


@pytest.fixture(scope="function")
def clickhouse_db(clickhouse_server_ready: bool) -> str:
    """Set up ClickHouse test database."""
    if not clickhouse_server_ready:
        pytest.skip("ClickHouse is not available")

    try:
        import clickhouse_connect
    except ImportError:
        pytest.skip("clickhouse-connect is not installed")

    try:
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )

        # Create test database
        client.command(f"DROP DATABASE IF EXISTS {CLICKHOUSE_DATABASE}")
        client.command(f"CREATE DATABASE {CLICKHOUSE_DATABASE}")

        # Connect to test database
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
            database=CLICKHOUSE_DATABASE,
        )

        client.command("""
            CREATE TABLE test_users (
                id UInt32,
                name String,
                email String
            ) ENGINE = MergeTree()
            ORDER BY id
        """)

        client.command("""
            CREATE TABLE test_products (
                id UInt32,
                name String,
                price Float64,
                stock UInt32
            ) ENGINE = MergeTree()
            ORDER BY id
        """)

        client.command("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email != ''
        """)

        # Create test data skipping index for integration tests
        client.command("""
            ALTER TABLE test_users ADD INDEX idx_test_users_email email TYPE set(100) GRANULARITY 1
        """)

        # Note: ClickHouse doesn't support triggers or sequences

        client.command("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
        """)

        client.command("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
        """)

    except Exception as e:
        pytest.skip(f"Failed to setup ClickHouse database: {e}")

    yield CLICKHOUSE_DATABASE

    try:
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )
        client.command(f"DROP DATABASE IF EXISTS {CLICKHOUSE_DATABASE}")
    except Exception:
        pass


@pytest.fixture(scope="function")
def clickhouse_connection(clickhouse_db: str) -> str:
    """Create a sqlit CLI connection for ClickHouse and clean up after test."""
    connection_name = f"test_clickhouse_{os.getpid()}"

    cleanup_connection(connection_name)

    args = [
        "connections",
        "add",
        "clickhouse",
        "--name",
        connection_name,
        "--server",
        CLICKHOUSE_HOST,
        "--port",
        str(CLICKHOUSE_PORT),
        "--database",
        clickhouse_db,
        "--username",
        CLICKHOUSE_USER,
    ]
    if CLICKHOUSE_PASSWORD:
        args.extend(["--password", CLICKHOUSE_PASSWORD])
    else:
        args.extend(["--password", ""])

    run_cli(*args)

    yield connection_name

    cleanup_connection(connection_name)


# =============================================================================
# SSH Tunnel Fixtures
# =============================================================================

# SSH connection settings for Docker
SSH_HOST = os.environ.get("SSH_HOST", "localhost")
SSH_PORT = int(os.environ.get("SSH_PORT", "2222"))
SSH_USER = os.environ.get("SSH_USER", "testuser")
SSH_PASSWORD = os.environ.get("SSH_PASSWORD", "testpass")
# The PostgreSQL host as seen from the SSH server (docker network)
SSH_REMOTE_DB_HOST = os.environ.get("SSH_REMOTE_DB_HOST", "postgres-ssh")
SSH_REMOTE_DB_PORT = int(os.environ.get("SSH_REMOTE_DB_PORT", "5432"))


def ssh_available() -> bool:
    """Check if SSH server is available."""
    return is_port_open(SSH_HOST, SSH_PORT)


@pytest.fixture(scope="session")
def ssh_server_ready() -> bool:
    """Check if SSH server is ready and return True/False."""
    if not ssh_available():
        return False
    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def ssh_postgres_db(ssh_server_ready: bool) -> str:
    """Set up PostgreSQL test database accessible via SSH tunnel."""
    if not ssh_server_ready:
        pytest.skip("SSH server is not available")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed")

    # postgres-ssh container is accessible on port 5433
    pg_host = os.environ.get("SSH_DIRECT_PG_HOST", "localhost")
    pg_port = int(os.environ.get("SSH_DIRECT_PG_PORT", "5433"))

    try:
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")

        cursor.execute("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
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
        pytest.skip(f"Failed to setup PostgreSQL database for SSH test: {e}")

    yield POSTGRES_DATABASE

    try:
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def ssh_connection(ssh_postgres_db: str) -> str:
    """Create a sqlit CLI connection for PostgreSQL via SSH tunnel."""
    connection_name = f"test_ssh_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "postgresql",
        "--name",
        connection_name,
        "--server",
        SSH_REMOTE_DB_HOST,
        "--port",
        str(SSH_REMOTE_DB_PORT),
        "--database",
        ssh_postgres_db,
        "--username",
        POSTGRES_USER,
        "--password",
        POSTGRES_PASSWORD,
        "--ssh-enabled",
        "--ssh-host",
        SSH_HOST,
        "--ssh-port",
        str(SSH_PORT),
        "--ssh-username",
        SSH_USER,
        "--ssh-auth-type",
        "password",
        "--ssh-password",
        SSH_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def cli_runner():
    """Provide the CLI runner function."""
    return run_cli
