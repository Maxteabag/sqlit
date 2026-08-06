"""Integration tests for FK introspection against real database engines.

Each test connects to a Docker-Compose service (or in-process driver), builds
a tiny FK graph, and exercises the adapter's `get_foreign_keys` and
`get_referencing_foreign_keys` directly. Tests skip cleanly when the
service or driver isn't available, so local runs don't need every engine up.

Schema used everywhere:

    users(id PK)
    blog_post(id PK, author_id FK -> users.id)
    comments(id PK, post_id FK -> blog_post.id, author_id FK -> users.id)

These give us:
- outgoing FKs of blog_post: 1 (author_id -> users.id)
- outgoing FKs of comments: 2 (post_id, author_id)
- incoming refs to users: 2 (from blog_post + comments)
- incoming refs to blog_post: 1 (from comments)
"""

from __future__ import annotations

import os
import socket

import pytest


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ----------------------------------------------------------------------------
# SQLite — no Docker, just a temp DB
# ----------------------------------------------------------------------------

class TestSQLiteForeignKeysIntegration:
    """The unit-tests file already covers SQLite; this is a sanity duplicate
    to ensure the integration suite's expectations hold for the reference impl."""

    @pytest.fixture
    def conn(self, tmp_path):
        import sqlite3

        path = tmp_path / "fk.db"
        c = sqlite3.connect(str(path))
        c.executescript(_SQLITE_SCHEMA)
        c.commit()
        yield c
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter

        fks = SQLiteAdapter().get_foreign_keys(conn, "comments")
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("post_id", "blog_post"),
            ("author_id", "users"),
        }

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter

        fks = SQLiteAdapter().get_referencing_foreign_keys(conn, "users")
        assert len(fks) == 2
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("blog_post", "author_id"),
            ("comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# DuckDB — pure Python lib, no Docker
# ----------------------------------------------------------------------------

class TestDuckDBForeignKeysIntegration:
    @pytest.fixture
    def conn(self, tmp_path):
        try:
            import duckdb
        except ImportError:
            pytest.skip("duckdb not installed")
        path = tmp_path / "fk.duckdb"
        c = duckdb.connect(str(path))
        c.execute(_GENERIC_DDL_USERS)
        c.execute(_GENERIC_DDL_BLOG_POST)
        c.execute(_GENERIC_DDL_COMMENTS)
        yield c
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

        fks = DuckDBAdapter().get_foreign_keys(conn, "comments")
        # DuckDB may bundle a composite FK into one row; we expand per-column.
        actual = {(fk.column, fk.referenced_table) for fk in fks}
        assert actual == {("post_id", "blog_post"), ("author_id", "users")}

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

        fks = DuckDBAdapter().get_referencing_foreign_keys(conn, "users")
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("blog_post", "author_id"),
            ("comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# PostgreSQL — Docker compose: postgres service
# ----------------------------------------------------------------------------

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.environ.get("POSTGRES_USER", "testuser")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "TestPassword123!")
POSTGRES_DB = os.environ.get("POSTGRES_DATABASE", "test_sqlit")


class TestPostgresForeignKeysIntegration:
    @pytest.fixture
    def conn(self):
        if not _port_open(POSTGRES_HOST, POSTGRES_PORT):
            pytest.skip("postgres service not reachable")
        try:
            import psycopg2
        except ImportError:
            pytest.skip("psycopg2 not installed")
        c = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB,
        )
        c.autocommit = True
        cur = c.cursor()
        cur.execute("DROP TABLE IF EXISTS fk_comments CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_users CASCADE")
        cur.execute("CREATE TABLE fk_users (id INT PRIMARY KEY, name TEXT)")
        cur.execute(
            "CREATE TABLE fk_blog_post ("
            "  id INT PRIMARY KEY, title TEXT, "
            "  author_id INT REFERENCES fk_users(id))"
        )
        cur.execute(
            "CREATE TABLE fk_comments ("
            "  id INT PRIMARY KEY, "
            "  post_id INT REFERENCES fk_blog_post(id), "
            "  author_id INT REFERENCES fk_users(id), "
            "  body TEXT)"
        )
        yield c
        cur.execute("DROP TABLE IF EXISTS fk_comments CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_users CASCADE")
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        fks = PostgreSQLAdapter().get_foreign_keys(conn, "fk_comments")
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("post_id", "fk_blog_post"),
            ("author_id", "fk_users"),
        }
        for fk in fks:
            assert fk.referenced_column == "id"

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        fks = PostgreSQLAdapter().get_referencing_foreign_keys(conn, "fk_users")
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("fk_blog_post", "author_id"),
            ("fk_comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# MySQL — Docker compose: mysql service
# ----------------------------------------------------------------------------

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "testuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "TestPassword123!")
MYSQL_DB = os.environ.get("MYSQL_DATABASE", "test_sqlit")


class TestMySQLForeignKeysIntegration:
    @pytest.fixture
    def conn(self):
        if not _port_open(MYSQL_HOST, MYSQL_PORT):
            pytest.skip("mysql service not reachable")
        try:
            import pymysql
        except ImportError:
            pytest.skip("pymysql not installed")
        c = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
        )
        cur = c.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS fk_comments")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post")
        cur.execute("DROP TABLE IF EXISTS fk_users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cur.execute("CREATE TABLE fk_users (id INT PRIMARY KEY, name VARCHAR(100)) ENGINE=InnoDB")
        cur.execute(
            "CREATE TABLE fk_blog_post ("
            "  id INT PRIMARY KEY, title VARCHAR(100), "
            "  author_id INT, FOREIGN KEY (author_id) REFERENCES fk_users(id)"
            ") ENGINE=InnoDB"
        )
        cur.execute(
            "CREATE TABLE fk_comments ("
            "  id INT PRIMARY KEY, post_id INT, author_id INT, body TEXT, "
            "  FOREIGN KEY (post_id) REFERENCES fk_blog_post(id), "
            "  FOREIGN KEY (author_id) REFERENCES fk_users(id)"
            ") ENGINE=InnoDB"
        )
        c.commit()
        yield c
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS fk_comments")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post")
        cur.execute("DROP TABLE IF EXISTS fk_users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        c.commit()
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter

        fks = MySQLAdapter().get_foreign_keys(conn, "fk_comments", database=MYSQL_DB)
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("post_id", "fk_blog_post"),
            ("author_id", "fk_users"),
        }

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter

        fks = MySQLAdapter().get_referencing_foreign_keys(
            conn, "fk_users", database=MYSQL_DB
        )
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("fk_blog_post", "author_id"),
            ("fk_comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# MariaDB — Docker compose: mariadb (port 3307)
# ----------------------------------------------------------------------------

MARIADB_HOST = os.environ.get("MARIADB_HOST", "127.0.0.1")
MARIADB_PORT = int(os.environ.get("MARIADB_PORT", "3307"))
MARIADB_USER = os.environ.get("MARIADB_USER", "root")
MARIADB_PASSWORD = os.environ.get("MARIADB_PASSWORD", "TestPassword123!")
MARIADB_DB = os.environ.get("MARIADB_DATABASE", "test_sqlit")


class TestMariaDBForeignKeysIntegration:
    @pytest.fixture
    def conn(self):
        if not _port_open(MARIADB_HOST, MARIADB_PORT):
            pytest.skip("mariadb service not reachable")
        try:
            import pymysql
        except ImportError:
            pytest.skip("pymysql not installed")
        c = pymysql.connect(
            host=MARIADB_HOST,
            port=MARIADB_PORT,
            user=MARIADB_USER,
            password=MARIADB_PASSWORD,
            database=MARIADB_DB,
        )
        cur = c.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS fk_comments")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post")
        cur.execute("DROP TABLE IF EXISTS fk_users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cur.execute("CREATE TABLE fk_users (id INT PRIMARY KEY, name VARCHAR(100))")
        cur.execute(
            "CREATE TABLE fk_blog_post ("
            "  id INT PRIMARY KEY, title VARCHAR(100), "
            "  author_id INT, FOREIGN KEY (author_id) REFERENCES fk_users(id))"
        )
        cur.execute(
            "CREATE TABLE fk_comments ("
            "  id INT PRIMARY KEY, post_id INT, author_id INT, body TEXT, "
            "  FOREIGN KEY (post_id) REFERENCES fk_blog_post(id), "
            "  FOREIGN KEY (author_id) REFERENCES fk_users(id))"
        )
        c.commit()
        yield c
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS fk_comments")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post")
        cur.execute("DROP TABLE IF EXISTS fk_users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        c.commit()
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.mariadb.adapter import MariaDBAdapter

        fks = MariaDBAdapter().get_foreign_keys(conn, "fk_comments", database=MARIADB_DB)
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("post_id", "fk_blog_post"),
            ("author_id", "fk_users"),
        }

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.mariadb.adapter import MariaDBAdapter

        fks = MariaDBAdapter().get_referencing_foreign_keys(
            conn, "fk_users", database=MARIADB_DB
        )
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("fk_blog_post", "author_id"),
            ("fk_comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# MSSQL — Docker compose: mssql service (port 1434)
# ----------------------------------------------------------------------------

MSSQL_HOST = os.environ.get("MSSQL_HOST", "127.0.0.1")
MSSQL_PORT = int(os.environ.get("MSSQL_PORT", "1434"))
MSSQL_USER = os.environ.get("MSSQL_USER", "sa")
MSSQL_PASSWORD = os.environ.get("MSSQL_PASSWORD", "TestPassword123!")


class TestMSSQLForeignKeysIntegration:
    @pytest.fixture
    def conn(self):
        if not _port_open(MSSQL_HOST, MSSQL_PORT):
            pytest.skip("mssql service not reachable")
        try:
            import mssql_python
        except ImportError:
            pytest.skip("mssql_python not installed")
        connection_string = (
            f"Server={MSSQL_HOST},{MSSQL_PORT};"
            f"Database=master;"
            f"UID={MSSQL_USER};PWD={MSSQL_PASSWORD};"
            f"Encrypt=no;TrustServerCertificate=yes;"
        )
        c = mssql_python.connect(connection_string)
        cur = c.cursor()
        cur.execute("IF OBJECT_ID('dbo.fk_comments') IS NOT NULL DROP TABLE dbo.fk_comments")
        cur.execute("IF OBJECT_ID('dbo.fk_blog_post') IS NOT NULL DROP TABLE dbo.fk_blog_post")
        cur.execute("IF OBJECT_ID('dbo.fk_users') IS NOT NULL DROP TABLE dbo.fk_users")
        cur.execute("CREATE TABLE dbo.fk_users (id INT PRIMARY KEY, name NVARCHAR(100))")
        cur.execute(
            "CREATE TABLE dbo.fk_blog_post ("
            "  id INT PRIMARY KEY, title NVARCHAR(100), "
            "  author_id INT FOREIGN KEY REFERENCES dbo.fk_users(id))"
        )
        cur.execute(
            "CREATE TABLE dbo.fk_comments ("
            "  id INT PRIMARY KEY, "
            "  post_id INT FOREIGN KEY REFERENCES dbo.fk_blog_post(id), "
            "  author_id INT FOREIGN KEY REFERENCES dbo.fk_users(id), "
            "  body NVARCHAR(MAX))"
        )
        c.commit()
        yield c
        cur.execute("IF OBJECT_ID('dbo.fk_comments') IS NOT NULL DROP TABLE dbo.fk_comments")
        cur.execute("IF OBJECT_ID('dbo.fk_blog_post') IS NOT NULL DROP TABLE dbo.fk_blog_post")
        cur.execute("IF OBJECT_ID('dbo.fk_users') IS NOT NULL DROP TABLE dbo.fk_users")
        c.commit()
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        fks = SQLServerAdapter().get_foreign_keys(conn, "fk_comments")
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("post_id", "fk_blog_post"),
            ("author_id", "fk_users"),
        }

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        fks = SQLServerAdapter().get_referencing_foreign_keys(conn, "fk_users")
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("fk_blog_post", "author_id"),
            ("fk_comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# CockroachDB — Docker compose: cockroachdb (port 26257)
# ----------------------------------------------------------------------------

COCKROACH_HOST = os.environ.get("COCKROACHDB_HOST", "127.0.0.1")
COCKROACH_PORT = int(os.environ.get("COCKROACHDB_PORT", "26257"))


class TestCockroachDBForeignKeysIntegration:
    @pytest.fixture
    def conn(self):
        if not _port_open(COCKROACH_HOST, COCKROACH_PORT):
            pytest.skip("cockroachdb service not reachable")
        try:
            import psycopg2
        except ImportError:
            pytest.skip("psycopg2 not installed")
        c = psycopg2.connect(
            host=COCKROACH_HOST,
            port=COCKROACH_PORT,
            user="root",
            database="defaultdb",
        )
        c.autocommit = True
        cur = c.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS test_fk_sqlit")
        c.close()
        c = psycopg2.connect(
            host=COCKROACH_HOST,
            port=COCKROACH_PORT,
            user="root",
            database="test_fk_sqlit",
        )
        c.autocommit = True
        cur = c.cursor()
        cur.execute("DROP TABLE IF EXISTS fk_comments CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_users CASCADE")
        cur.execute("CREATE TABLE fk_users (id INT PRIMARY KEY, name STRING)")
        cur.execute(
            "CREATE TABLE fk_blog_post ("
            "  id INT PRIMARY KEY, title STRING, "
            "  author_id INT REFERENCES fk_users(id))"
        )
        cur.execute(
            "CREATE TABLE fk_comments ("
            "  id INT PRIMARY KEY, "
            "  post_id INT REFERENCES fk_blog_post(id), "
            "  author_id INT REFERENCES fk_users(id), "
            "  body STRING)"
        )
        yield c
        cur.execute("DROP TABLE IF EXISTS fk_comments CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_blog_post CASCADE")
        cur.execute("DROP TABLE IF EXISTS fk_users CASCADE")
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.cockroachdb.adapter import CockroachDBAdapter

        fks = CockroachDBAdapter().get_foreign_keys(conn, "fk_comments")
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("post_id", "fk_blog_post"),
            ("author_id", "fk_users"),
        }

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.cockroachdb.adapter import CockroachDBAdapter

        fks = CockroachDBAdapter().get_referencing_foreign_keys(conn, "fk_users")
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("fk_blog_post", "author_id"),
            ("fk_comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# Turso — Docker compose: libsql-server on port 8081
# ----------------------------------------------------------------------------

TURSO_URL = os.environ.get("TURSO_URL", "http://127.0.0.1:8081")


class TestTursoForeignKeysIntegration:
    @pytest.fixture
    def conn(self):
        import urllib.parse

        parsed = urllib.parse.urlparse(TURSO_URL)
        if not _port_open(parsed.hostname or "127.0.0.1", parsed.port or 8081):
            pytest.skip("turso service not reachable")
        try:
            import libsql
        except ImportError:
            pytest.skip("libsql not installed")
        c = libsql.connect(TURSO_URL, auth_token="")
        c.execute("DROP TABLE IF EXISTS fk_comments")
        c.execute("DROP TABLE IF EXISTS fk_blog_post")
        c.execute("DROP TABLE IF EXISTS fk_users")
        c.execute("CREATE TABLE fk_users (id INTEGER PRIMARY KEY, name TEXT)")
        c.execute(
            "CREATE TABLE fk_blog_post ("
            "  id INTEGER PRIMARY KEY, title TEXT, "
            "  author_id INTEGER REFERENCES fk_users(id))"
        )
        c.execute(
            "CREATE TABLE fk_comments ("
            "  id INTEGER PRIMARY KEY, "
            "  post_id INTEGER REFERENCES fk_blog_post(id), "
            "  author_id INTEGER REFERENCES fk_users(id), "
            "  body TEXT)"
        )
        c.commit()
        yield c
        c.execute("DROP TABLE IF EXISTS fk_comments")
        c.execute("DROP TABLE IF EXISTS fk_blog_post")
        c.execute("DROP TABLE IF EXISTS fk_users")
        c.commit()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.turso.adapter import TursoAdapter

        fks = TursoAdapter().get_foreign_keys(conn, "fk_comments")
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("post_id", "fk_blog_post"),
            ("author_id", "fk_users"),
        }

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.turso.adapter import TursoAdapter

        fks = TursoAdapter().get_referencing_foreign_keys(conn, "fk_users")
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("fk_blog_post", "author_id"),
            ("fk_comments", "author_id"),
        }


# ----------------------------------------------------------------------------
# Firebird — Docker compose: firebird (port 3050)
# ----------------------------------------------------------------------------

FIREBIRD_HOST = os.environ.get("FIREBIRD_HOST", "127.0.0.1")
FIREBIRD_PORT = int(os.environ.get("FIREBIRD_PORT", "3050"))
FIREBIRD_USER = os.environ.get("FIREBIRD_USER", "testuser")
FIREBIRD_PASSWORD = os.environ.get("FIREBIRD_PASSWORD", "TestPassword123!")
FIREBIRD_DB = os.environ.get("FIREBIRD_DATABASE", "/var/lib/firebird/data/test_sqlit.fdb")


class TestFirebirdForeignKeysIntegration:
    @pytest.fixture
    def conn(self):
        if not _port_open(FIREBIRD_HOST, FIREBIRD_PORT):
            pytest.skip("firebird service not reachable")
        try:
            import firebirdsql
        except ImportError:
            pytest.skip("firebirdsql not installed")
        c = firebirdsql.connect(
            host=FIREBIRD_HOST,
            port=FIREBIRD_PORT,
            database=FIREBIRD_DB,
            user=FIREBIRD_USER,
            password=FIREBIRD_PASSWORD,
        )
        cur = c.cursor()
        # Firebird needs each statement committed; drop-with-cascade-equivalent
        # isn't available, so drop child tables first.
        for tbl in ("FK_COMMENTS", "FK_BLOG_POST", "FK_USERS"):
            try:
                cur.execute(f"DROP TABLE {tbl}")
                c.commit()
            except Exception:
                c.rollback()
        cur.execute("CREATE TABLE FK_USERS (ID INTEGER NOT NULL PRIMARY KEY, NAME VARCHAR(100))")
        c.commit()
        cur.execute(
            "CREATE TABLE FK_BLOG_POST ("
            "  ID INTEGER NOT NULL PRIMARY KEY, TITLE VARCHAR(100), "
            "  AUTHOR_ID INTEGER REFERENCES FK_USERS(ID))"
        )
        c.commit()
        cur.execute(
            "CREATE TABLE FK_COMMENTS ("
            "  ID INTEGER NOT NULL PRIMARY KEY, "
            "  POST_ID INTEGER REFERENCES FK_BLOG_POST(ID), "
            "  AUTHOR_ID INTEGER REFERENCES FK_USERS(ID), "
            "  BODY VARCHAR(500))"
        )
        c.commit()
        yield c
        for tbl in ("FK_COMMENTS", "FK_BLOG_POST", "FK_USERS"):
            try:
                cur.execute(f"DROP TABLE {tbl}")
                c.commit()
            except Exception:
                c.rollback()
        c.close()

    def test_outgoing(self, conn):
        from sqlit.domains.connections.providers.firebird.adapter import FirebirdAdapter

        fks = FirebirdAdapter().get_foreign_keys(conn, "FK_COMMENTS")
        assert {(fk.column, fk.referenced_table) for fk in fks} == {
            ("POST_ID", "FK_BLOG_POST"),
            ("AUTHOR_ID", "FK_USERS"),
        }

    def test_incoming(self, conn):
        from sqlit.domains.connections.providers.firebird.adapter import FirebirdAdapter

        fks = FirebirdAdapter().get_referencing_foreign_keys(conn, "FK_USERS")
        assert {(fk.owner_table, fk.column) for fk in fks} == {
            ("FK_BLOG_POST", "AUTHOR_ID"),
            ("FK_COMMENTS", "AUTHOR_ID"),
        }


# ----------------------------------------------------------------------------
# ClickHouse — engine doesn't support FKs; verify the base default returns []
# ----------------------------------------------------------------------------

CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))


class TestClickHouseNoForeignKeysIntegration:
    """ClickHouse has no FK metadata — adapter should report unsupported & return []."""

    def test_capability_off(self):
        from sqlit.domains.connections.providers.clickhouse.adapter import ClickHouseAdapter

        assert ClickHouseAdapter().supports_foreign_keys is False

    def test_methods_return_empty_without_connection(self):
        from sqlit.domains.connections.providers.clickhouse.adapter import ClickHouseAdapter

        adapter = ClickHouseAdapter()
        # The base-class default doesn't touch the connection — pass None.
        assert adapter.get_foreign_keys(None, "anything") == []
        assert adapter.get_referencing_foreign_keys(None, "anything") == []


# ----------------------------------------------------------------------------
# Reusable schema constants
# ----------------------------------------------------------------------------

_SQLITE_SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE blog_post (
    id INTEGER PRIMARY KEY,
    title TEXT,
    author_id INTEGER REFERENCES users(id)
);
CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    post_id INTEGER REFERENCES blog_post(id),
    author_id INTEGER REFERENCES users(id),
    body TEXT
);
"""

_GENERIC_DDL_USERS = "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR)"
_GENERIC_DDL_BLOG_POST = (
    "CREATE TABLE blog_post ("
    "  id INTEGER PRIMARY KEY, title VARCHAR, "
    "  author_id INTEGER REFERENCES users(id))"
)
_GENERIC_DDL_COMMENTS = (
    "CREATE TABLE comments ("
    "  id INTEGER PRIMARY KEY, "
    "  post_id INTEGER REFERENCES blog_post(id), "
    "  author_id INTEGER REFERENCES users(id), "
    "  body VARCHAR)"
)
