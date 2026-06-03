"""Tests for foreign-key introspection (issue #167)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sqlit.domains.connections.providers.adapters.base import ForeignKeyInfo
from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter


@pytest.fixture
def blog_db(tmp_path: Path) -> sqlite3.Connection:
    """SQLite DB with users / blog_post / comments — a small FK graph."""
    db = tmp_path / "blog.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE blog_post (
            id INTEGER PRIMARY KEY,
            title TEXT,
            user_id INTEGER REFERENCES users(id)
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY,
            post_id INTEGER REFERENCES blog_post(id),
            user_id INTEGER REFERENCES users(id),
            body TEXT
        );
        """
    )
    conn.commit()
    return conn


class TestSQLiteForeignKeys:
    def test_capability_flag(self):
        assert SQLiteAdapter().supports_foreign_keys is True

    def test_outgoing_fks_on_blog_post(self, blog_db: sqlite3.Connection):
        fks = SQLiteAdapter().get_foreign_keys(blog_db, "blog_post")
        assert len(fks) == 1
        fk = fks[0]
        assert fk.owner_table == "blog_post"
        assert fk.column == "user_id"
        assert fk.referenced_table == "users"
        assert fk.referenced_column == "id"
        assert fk.ordinal == 1

    def test_no_outgoing_fks_on_users(self, blog_db: sqlite3.Connection):
        assert SQLiteAdapter().get_foreign_keys(blog_db, "users") == []

    def test_incoming_refs_to_users(self, blog_db: sqlite3.Connection):
        fks = SQLiteAdapter().get_referencing_foreign_keys(blog_db, "users")
        # Both blog_post.user_id and comments.user_id point at users.id
        owners = sorted((fk.owner_table, fk.column) for fk in fks)
        assert owners == [("blog_post", "user_id"), ("comments", "user_id")]
        for fk in fks:
            assert fk.referenced_table == "users"
            assert fk.referenced_column == "id"

    def test_incoming_refs_to_blog_post(self, blog_db: sqlite3.Connection):
        fks = SQLiteAdapter().get_referencing_foreign_keys(blog_db, "blog_post")
        assert len(fks) == 1
        assert fks[0].owner_table == "comments"
        assert fks[0].column == "post_id"
        assert fks[0].referenced_table == "blog_post"
        assert fks[0].referenced_column == "id"

    def test_incoming_refs_to_isolated_table(self, blog_db: sqlite3.Connection):
        # comments has no incoming refs in this schema
        assert SQLiteAdapter().get_referencing_foreign_keys(blog_db, "comments") == []


class TestForeignKeyInfo:
    def test_minimum_fields(self):
        fk = ForeignKeyInfo(
            owner_table="orders",
            column="customer_id",
            referenced_table="customers",
            referenced_column="id",
        )
        assert fk.owner_table == "orders"
        assert fk.referenced_schema == ""
        assert fk.referenced_database == ""
        assert fk.ordinal == 1


class TestQuoteLiteral:
    def setup_method(self):
        self.adapter = SQLiteAdapter()

    def test_int(self):
        assert self.adapter.quote_literal(42) == "42"

    def test_float(self):
        assert self.adapter.quote_literal(1.5) == "1.5"

    def test_str_plain(self):
        assert self.adapter.quote_literal("hello") == "'hello'"

    def test_str_with_single_quote(self):
        assert self.adapter.quote_literal("O'Brien") == "'O''Brien'"

    def test_none(self):
        assert self.adapter.quote_literal(None) == "NULL"

    def test_bool_true(self):
        assert self.adapter.quote_literal(True) == "TRUE"

    def test_bool_false(self):
        assert self.adapter.quote_literal(False) == "FALSE"

    def test_bytes(self):
        assert self.adapter.quote_literal(b"\x00\xff") == "X'00ff'"


class TestBuildFkNavigationQuery:
    """The free function used by the FK-jump action — verifies dialect-aware composition."""

    def test_sqlite_int_value(self):
        from sqlit.domains.results.ui.mixins.results import build_fk_navigation_query

        q = build_fk_navigation_query(
            adapter=SQLiteAdapter(),
            ref_table="users",
            ref_column="id",
            value=42,
        )
        assert q == 'SELECT * FROM "users" WHERE "id" = 42 LIMIT 100'

    def test_sqlite_str_value_escapes_quotes(self):
        from sqlit.domains.results.ui.mixins.results import build_fk_navigation_query

        q = build_fk_navigation_query(
            adapter=SQLiteAdapter(),
            ref_table="users",
            ref_column="name",
            value="O'Brien",
        )
        assert q == 'SELECT * FROM "users" WHERE "name" = \'O\'\'Brien\' LIMIT 100'

    def test_postgres_qualifies_with_schema(self):
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter
        from sqlit.domains.results.ui.mixins.results import build_fk_navigation_query

        q = build_fk_navigation_query(
            adapter=PostgreSQLAdapter(),
            ref_table="users",
            ref_column="id",
            value=7,
            ref_schema="public",
        )
        assert q == 'SELECT * FROM "public"."users" WHERE "id" = 7 LIMIT 100'

    def test_mysql_uses_backticks(self):
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter
        from sqlit.domains.results.ui.mixins.results import build_fk_navigation_query

        q = build_fk_navigation_query(
            adapter=MySQLAdapter(),
            ref_table="users",
            ref_column="id",
            value=7,
        )
        assert q == "SELECT * FROM `users` WHERE `id` = 7 LIMIT 100"

    def test_custom_limit(self):
        from sqlit.domains.results.ui.mixins.results import build_fk_navigation_query

        q = build_fk_navigation_query(
            adapter=SQLiteAdapter(),
            ref_table="t",
            ref_column="c",
            value=1,
            limit=5,
        )
        assert q.endswith("LIMIT 5")


class TestBaseAdapterDefaults:
    """The base adapter has no FK support unless overridden — defaults return []."""

    def test_supports_foreign_keys_default(self):
        # DatabaseAdapter is abstract; check the default class attribute via SQLiteAdapter's
        # behavior is to override to True. We can verify the base property by reading from
        # a sibling adapter that doesn't override.
        from sqlit.domains.connections.providers.clickhouse.adapter import ClickHouseAdapter

        assert ClickHouseAdapter().supports_foreign_keys is False

    def test_default_methods_return_empty(self):
        from sqlit.domains.connections.providers.clickhouse.adapter import ClickHouseAdapter

        adapter = ClickHouseAdapter()
        # Pass None as conn — defaults shouldn't even touch it.
        assert adapter.get_foreign_keys(None, "t") == []
        assert adapter.get_referencing_foreign_keys(None, "t") == []
