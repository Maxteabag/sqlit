"""Tests for CREATE VIEW statement autocomplete suggestions."""

import pytest

from sqlit.sql_completion import get_completions


class TestCreateViewStatements:
    """Tests for CREATE VIEW autocomplete suggestions."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name", "email"],
                "orders": ["id", "user_id", "total"],
                "products": ["id", "name", "price"],
            },
            "procedures": [],
        }

    def test_create_view_as_suggests_select(self, schema):
        """CREATE VIEW name AS should suggest SELECT."""
        sql = "CREATE VIEW user_emails AS "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_create_view_as_partial_select(self, schema):
        """Typing partial SELECT should filter."""
        sql = "CREATE VIEW user_emails AS SEL"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_create_or_replace_view_as_suggests_select(self, schema):
        """CREATE OR REPLACE VIEW name AS should suggest SELECT."""
        sql = "CREATE OR REPLACE VIEW user_emails AS "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_create_view_after_name_suggests_as(self, schema):
        """After view name, should suggest AS."""
        sql = "CREATE VIEW user_emails "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "AS" in completions

    def test_create_view_select_from_suggests_tables(self, schema):
        """CREATE VIEW ... AS SELECT ... FROM should suggest tables."""
        sql = "CREATE VIEW user_emails AS SELECT * FROM "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_create_view_select_suggests_columns(self, schema):
        """CREATE VIEW ... AS SELECT should suggest columns."""
        sql = "CREATE VIEW user_emails AS SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should fall through to normal SELECT handling
        # Which suggests special SELECT keywords and functions (not tables)
        assert "*" in completions  # SELECT clause special keyword
        assert "DISTINCT" in completions  # SELECT clause special keyword

    def test_create_view_select_from_table_where(self, schema):
        """CREATE VIEW with full SELECT should work normally."""
        sql = "CREATE VIEW active_users AS SELECT * FROM users WHERE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should suggest columns from users table
        assert "id" in completions
        assert "name" in completions
        assert "email" in completions

    def test_create_or_replace_view_after_name_suggests_as(self, schema):
        """After OR REPLACE VIEW name, should suggest AS."""
        sql = "CREATE OR REPLACE VIEW user_emails "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "AS" in completions
