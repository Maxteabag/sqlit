"""MariaDB charset fixtures for testing legacy encodings (TIS-620, Latin1, etc.)."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_binary_port_open, run_cli

# TIS-620 (Thai) MariaDB
MARIADB_TIS620_HOST = os.environ.get("MARIADB_TIS620_HOST", "127.0.0.1")
MARIADB_TIS620_PORT = int(os.environ.get("MARIADB_TIS620_PORT", "3310"))

# Latin1 MariaDB
MARIADB_LATIN1_HOST = os.environ.get("MARIADB_LATIN1_HOST", "127.0.0.1")
MARIADB_LATIN1_PORT = int(os.environ.get("MARIADB_LATIN1_PORT", "3311"))

# Common credentials (same as other MariaDB containers)
MARIADB_CHARSET_USER = os.environ.get("MARIADB_CHARSET_USER", "root")
MARIADB_CHARSET_PASSWORD = os.environ.get("MARIADB_CHARSET_PASSWORD", "TestPassword123!")
MARIADB_CHARSET_DATABASE = os.environ.get("MARIADB_CHARSET_DATABASE", "test_sqlit")


def mariadb_tis620_available() -> bool:
    """Check if MariaDB TIS-620 is available."""
    return is_binary_port_open(MARIADB_TIS620_HOST, MARIADB_TIS620_PORT)


def mariadb_latin1_available() -> bool:
    """Check if MariaDB Latin1 is available."""
    return is_binary_port_open(MARIADB_LATIN1_HOST, MARIADB_LATIN1_PORT)


@pytest.fixture(scope="session")
def mariadb_tis620_server_ready() -> bool:
    """Check if MariaDB TIS-620 is ready and return True/False."""
    if not mariadb_tis620_available():
        return False
    time.sleep(1)
    return True


@pytest.fixture(scope="session")
def mariadb_latin1_server_ready() -> bool:
    """Check if MariaDB Latin1 is ready and return True/False."""
    if not mariadb_latin1_available():
        return False
    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def mariadb_tis620_db(mariadb_tis620_server_ready: bool) -> str:
    """Set up MariaDB TIS-620 test database with Thai data."""
    if not mariadb_tis620_server_ready:
        pytest.skip("MariaDB TIS-620 is not available")

    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL is not installed")

    try:
        conn = pymysql.connect(
            host=MARIADB_TIS620_HOST,
            port=MARIADB_TIS620_PORT,
            database=MARIADB_CHARSET_DATABASE,
            user=MARIADB_CHARSET_USER,
            password=MARIADB_CHARSET_PASSWORD,
            connect_timeout=10,
            charset="tis620",
        )
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS charset_test")
        cursor.execute(
            "CREATE TABLE charset_test (id INT PRIMARY KEY, content TEXT) "
            "CHARACTER SET tis620 COLLATE tis620_thai_ci"
        )

        cursor.execute("INSERT INTO charset_test VALUES (1, 'สวัสดีครับ')")
        cursor.execute("INSERT INTO charset_test VALUES (2, 'ภาษาไทย')")
        cursor.execute("INSERT INTO charset_test VALUES (3, 'กรุงเทพมหานคร')")

        conn.commit()
        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup MariaDB TIS-620 database: {e}")

    yield MARIADB_CHARSET_DATABASE

    try:
        conn = pymysql.connect(
            host=MARIADB_TIS620_HOST,
            port=MARIADB_TIS620_PORT,
            database=MARIADB_CHARSET_DATABASE,
            user=MARIADB_CHARSET_USER,
            password=MARIADB_CHARSET_PASSWORD,
            connect_timeout=10,
            charset="tis620",
        )
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS charset_test")
        conn.commit()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def mariadb_latin1_db(mariadb_latin1_server_ready: bool) -> str:
    """Set up MariaDB Latin1 test database with accented Latin characters."""
    if not mariadb_latin1_server_ready:
        pytest.skip("MariaDB Latin1 is not available")

    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL is not installed")

    try:
        conn = pymysql.connect(
            host=MARIADB_LATIN1_HOST,
            port=MARIADB_LATIN1_PORT,
            database=MARIADB_CHARSET_DATABASE,
            user=MARIADB_CHARSET_USER,
            password=MARIADB_CHARSET_PASSWORD,
            connect_timeout=10,
            charset="latin1",
        )
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS charset_test")
        cursor.execute(
            "CREATE TABLE charset_test (id INT PRIMARY KEY, content TEXT) "
            "CHARACTER SET latin1 COLLATE latin1_swedish_ci"
        )

        cursor.execute("INSERT INTO charset_test VALUES (1, 'café')")
        cursor.execute("INSERT INTO charset_test VALUES (2, 'naïve')")
        cursor.execute("INSERT INTO charset_test VALUES (3, 'Müller')")
        cursor.execute("INSERT INTO charset_test VALUES (4, 'señor')")

        conn.commit()
        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup MariaDB Latin1 database: {e}")

    yield MARIADB_CHARSET_DATABASE

    try:
        conn = pymysql.connect(
            host=MARIADB_LATIN1_HOST,
            port=MARIADB_LATIN1_PORT,
            database=MARIADB_CHARSET_DATABASE,
            user=MARIADB_CHARSET_USER,
            password=MARIADB_CHARSET_PASSWORD,
            connect_timeout=10,
            charset="latin1",
        )
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS charset_test")
        conn.commit()
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def mariadb_tis620_connection(mariadb_tis620_db: str) -> str:
    """Create a sqlit CLI connection for MariaDB TIS-620."""
    connection_name = f"test_mariadb_tis620_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mariadb",
        "--name",
        connection_name,
        "--server",
        MARIADB_TIS620_HOST,
        "--port",
        str(MARIADB_TIS620_PORT),
        "--database",
        mariadb_tis620_db,
        "--username",
        MARIADB_CHARSET_USER,
        "--password",
        MARIADB_CHARSET_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


@pytest.fixture(scope="function")
def mariadb_latin1_connection(mariadb_latin1_db: str) -> str:
    """Create a sqlit CLI connection for MariaDB Latin1."""
    connection_name = f"test_mariadb_latin1_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mariadb",
        "--name",
        connection_name,
        "--server",
        MARIADB_LATIN1_HOST,
        "--port",
        str(MARIADB_LATIN1_PORT),
        "--database",
        mariadb_latin1_db,
        "--username",
        MARIADB_CHARSET_USER,
        "--password",
        MARIADB_CHARSET_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "MARIADB_CHARSET_DATABASE",
    "MARIADB_CHARSET_PASSWORD",
    "MARIADB_CHARSET_USER",
    "MARIADB_LATIN1_HOST",
    "MARIADB_LATIN1_PORT",
    "MARIADB_TIS620_HOST",
    "MARIADB_TIS620_PORT",
    "mariadb_latin1_available",
    "mariadb_latin1_connection",
    "mariadb_latin1_db",
    "mariadb_latin1_server_ready",
    "mariadb_tis620_available",
    "mariadb_tis620_connection",
    "mariadb_tis620_db",
    "mariadb_tis620_server_ready",
]
