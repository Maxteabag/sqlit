"""MySQL charset fixtures for testing legacy encodings (TIS-620, Latin1, etc.)."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# TIS-620 (Thai) MySQL
MYSQL_TIS620_HOST = os.environ.get("MYSQL_TIS620_HOST", "localhost")
MYSQL_TIS620_PORT = int(os.environ.get("MYSQL_TIS620_PORT", "3308"))

# Latin1 MySQL
MYSQL_LATIN1_HOST = os.environ.get("MYSQL_LATIN1_HOST", "localhost")
MYSQL_LATIN1_PORT = int(os.environ.get("MYSQL_LATIN1_PORT", "3309"))

# Common credentials (same as other MySQL containers)
MYSQL_CHARSET_USER = os.environ.get("MYSQL_CHARSET_USER", "root")
MYSQL_CHARSET_PASSWORD = os.environ.get("MYSQL_CHARSET_PASSWORD", "TestPassword123!")
MYSQL_CHARSET_DATABASE = os.environ.get("MYSQL_CHARSET_DATABASE", "test_sqlit")


def mysql_tis620_available() -> bool:
    """Check if MySQL TIS-620 is available."""
    return is_port_open(MYSQL_TIS620_HOST, MYSQL_TIS620_PORT)


def mysql_latin1_available() -> bool:
    """Check if MySQL Latin1 is available."""
    return is_port_open(MYSQL_LATIN1_HOST, MYSQL_LATIN1_PORT)


@pytest.fixture(scope="session")
def mysql_tis620_server_ready() -> bool:
    """Check if MySQL TIS-620 is ready and return True/False."""
    if not mysql_tis620_available():
        return False
    time.sleep(1)
    return True


@pytest.fixture(scope="session")
def mysql_latin1_server_ready() -> bool:
    """Check if MySQL Latin1 is ready and return True/False."""
    if not mysql_latin1_available():
        return False
    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def mysql_tis620_db(mysql_tis620_server_ready: bool) -> str:
    """Set up MySQL TIS-620 test database with Thai data."""
    if not mysql_tis620_server_ready:
        pytest.skip("MySQL TIS-620 is not available")

    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL is not installed")

    try:
        # Connect with tis620 charset to match server charset
        conn = pymysql.connect(
            host=MYSQL_TIS620_HOST,
            port=MYSQL_TIS620_PORT,
            database=MYSQL_CHARSET_DATABASE,
            user=MYSQL_CHARSET_USER,
            password=MYSQL_CHARSET_PASSWORD,
            connect_timeout=10,
            charset="tis620",
        )
        cursor = conn.cursor()

        # Create table and insert Thai data
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
        pytest.skip(f"Failed to setup MySQL TIS-620 database: {e}")

    yield MYSQL_CHARSET_DATABASE

    # Cleanup
    try:
        conn = pymysql.connect(
            host=MYSQL_TIS620_HOST,
            port=MYSQL_TIS620_PORT,
            database=MYSQL_CHARSET_DATABASE,
            user=MYSQL_CHARSET_USER,
            password=MYSQL_CHARSET_PASSWORD,
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
def mysql_latin1_db(mysql_latin1_server_ready: bool) -> str:
    """Set up MySQL Latin1 test database with accented Latin characters."""
    if not mysql_latin1_server_ready:
        pytest.skip("MySQL Latin1 is not available")

    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL is not installed")

    try:
        # Connect with latin1 charset to match server charset
        conn = pymysql.connect(
            host=MYSQL_LATIN1_HOST,
            port=MYSQL_LATIN1_PORT,
            database=MYSQL_CHARSET_DATABASE,
            user=MYSQL_CHARSET_USER,
            password=MYSQL_CHARSET_PASSWORD,
            connect_timeout=10,
            charset="latin1",
        )
        cursor = conn.cursor()

        # Create table and insert Latin1 data
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
        pytest.skip(f"Failed to setup MySQL Latin1 database: {e}")

    yield MYSQL_CHARSET_DATABASE

    # Cleanup
    try:
        conn = pymysql.connect(
            host=MYSQL_LATIN1_HOST,
            port=MYSQL_LATIN1_PORT,
            database=MYSQL_CHARSET_DATABASE,
            user=MYSQL_CHARSET_USER,
            password=MYSQL_CHARSET_PASSWORD,
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
def mysql_tis620_connection(mysql_tis620_db: str) -> str:
    """Create a sqlit CLI connection for MySQL TIS-620."""
    connection_name = f"test_mysql_tis620_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mysql",
        "--name",
        connection_name,
        "--server",
        MYSQL_TIS620_HOST,
        "--port",
        str(MYSQL_TIS620_PORT),
        "--database",
        mysql_tis620_db,
        "--username",
        MYSQL_CHARSET_USER,
        "--password",
        MYSQL_CHARSET_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


@pytest.fixture(scope="function")
def mysql_latin1_connection(mysql_latin1_db: str) -> str:
    """Create a sqlit CLI connection for MySQL Latin1."""
    connection_name = f"test_mysql_latin1_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "mysql",
        "--name",
        connection_name,
        "--server",
        MYSQL_LATIN1_HOST,
        "--port",
        str(MYSQL_LATIN1_PORT),
        "--database",
        mysql_latin1_db,
        "--username",
        MYSQL_CHARSET_USER,
        "--password",
        MYSQL_CHARSET_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "MYSQL_CHARSET_DATABASE",
    "MYSQL_CHARSET_PASSWORD",
    "MYSQL_CHARSET_USER",
    "MYSQL_LATIN1_HOST",
    "MYSQL_LATIN1_PORT",
    "MYSQL_TIS620_HOST",
    "MYSQL_TIS620_PORT",
    "mysql_latin1_available",
    "mysql_latin1_connection",
    "mysql_latin1_db",
    "mysql_latin1_server_ready",
    "mysql_tis620_available",
    "mysql_tis620_connection",
    "mysql_tis620_db",
    "mysql_tis620_server_ready",
]
