"""Tests for UPDATE statement autocomplete suggestions."""

import pytest

from sqlit.domains.query.completion import (
    SuggestionType,
    get_completions,
    get_context,
)


class TestUpdateStatements:
    """Tests for UPDATE statement autocomplete suggestions."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name", "email", "created_at", "status"],
                "orders": ["id", "user_id", "total", "status"],
                "products": ["id", "name", "price", "category"],
            },
            "procedures": [],
        }

    def test_update_suggests_tables(self, schema):
        """After UPDATE, should suggest table names."""
        sql = "UPDATE "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_update_partial_table(self, schema):
        """Typing partial table name after UPDATE."""
        sql = "UPDATE us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions

    def test_update_set_suggests_columns(self, schema):
        """After UPDATE table SET, should suggest columns for that table."""
        sql = "UPDATE users SET "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions
        assert "email" in completions
        assert "status" in completions

    def test_update_set_partial_column(self, schema):
        """Typing partial column name after SET."""
        sql = "UPDATE users SET na"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions

    def test_update_set_equals_suggests_columns(self, schema):
        """After SET column =, should suggest columns/values."""
        sql = "UPDATE users SET name = "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "email" in completions or len(completions) > 0

    def test_update_set_comma_suggests_more_columns(self, schema):
        """After SET col = value,, should suggest more columns."""
        sql = "UPDATE users SET name = 'John', "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "email" in completions
        assert "status" in completions

    def test_update_where_suggests_columns(self, schema):
        """After UPDATE ... WHERE, should suggest columns."""
        sql = "UPDATE users SET name = 'John' WHERE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_update_where_partial_column(self, schema):
        """Typing partial column in WHERE clause."""
        sql = "UPDATE users SET name = 'John' WHERE st"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "status" in completions

    def test_update_with_alias_set(self, schema):
        """UPDATE with alias should suggest columns via alias."""
        sql = "UPDATE users u SET u."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions
        assert "email" in completions

    def test_update_with_alias_where(self, schema):
        """UPDATE with alias in WHERE clause."""
        sql = "UPDATE users u SET name = 'John' WHERE u."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "status" in completions

    def test_update_no_suggestions_in_string(self, schema):
        """Inside string literal, should NOT suggest anything."""
        sql = "UPDATE users SET name = '"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert completions == []

    def test_update_from_join_suggests_tables(self, schema):
        """UPDATE ... FROM ... JOIN (SQL Server style) should suggest tables."""
        sql = "UPDATE u SET u.name = o.status FROM users u JOIN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions
