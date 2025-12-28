"""Tests for TRUNCATE TABLE statement autocomplete suggestions."""

import pytest

from sqlit.sql_completion import get_completions


class TestTruncateStatements:
    """Tests for TRUNCATE TABLE autocomplete suggestions."""

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

    def test_truncate_suggests_table_keyword_and_tables(self, schema):
        """TRUNCATE should suggest TABLE keyword and table names."""
        sql = "TRUNCATE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "TABLE" in completions
        assert "users" in completions
        assert "orders" in completions

    def test_truncate_partial_table_keyword(self, schema):
        """Typing partial TABLE should filter."""
        sql = "TRUNCATE TAB"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "TABLE" in completions
        assert "users" not in completions  # Filtered out by fuzzy match

    def test_truncate_table_suggests_tables(self, schema):
        """TRUNCATE TABLE should suggest table names."""
        sql = "TRUNCATE TABLE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions
        assert "products" in completions

    def test_truncate_table_partial_name(self, schema):
        """Typing partial table name should filter."""
        sql = "TRUNCATE TABLE us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" not in completions

    def test_truncate_partial_table_name_directly(self, schema):
        """TRUNCATE with partial table name directly should filter."""
        sql = "TRUNCATE ord"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions
        assert "users" not in completions

    def test_truncate_lowercase(self, schema):
        """truncate (lowercase) should work the same."""
        sql = "truncate table "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions
