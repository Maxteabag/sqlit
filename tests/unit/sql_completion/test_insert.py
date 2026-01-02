"""Tests for INSERT statement autocomplete suggestions."""

import pytest

from sqlit.domains.query.completion import (
    SuggestionType,
    get_completions,
    get_context,
)


class TestInsertStatements:
    """Tests for INSERT statement autocomplete suggestions."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name", "email", "created_at"],
                "orders": ["id", "user_id", "total", "status"],
                "products": ["id", "name", "price", "category"],
            },
            "procedures": [],
        }

    def test_insert_into_suggests_tables(self, schema):
        """After INSERT INTO, should suggest table names."""
        sql = "INSERT INTO "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_insert_into_partial_table(self, schema):
        """Typing partial table name after INSERT INTO."""
        sql = "INSERT INTO us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions

    def test_insert_into_table_opening_paren_suggests_columns(self, schema):
        """After INSERT INTO table (, should suggest columns for that table."""
        sql = "INSERT INTO users ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "email" in completions

    def test_insert_into_table_comma_suggests_more_columns(self, schema):
        """After INSERT INTO table (col1, should suggest more columns."""
        sql = "INSERT INTO users (id, "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions
        assert "email" in completions

    def test_insert_into_partial_column(self, schema):
        """Typing partial column name in INSERT column list."""
        sql = "INSERT INTO users (na"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions

    def test_insert_values_no_column_suggestions(self, schema):
        """Inside VALUES clause, should NOT suggest columns."""
        sql = "INSERT INTO users (id, name) VALUES ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" not in completions or len(completions) == 0

    def test_insert_values_string_literal_no_suggestions(self, schema):
        """Inside string literal in VALUES, should NOT suggest anything."""
        sql = "INSERT INTO users (id, name) VALUES (1, '"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert completions == []

    def test_insert_select_suggests_columns(self, schema):
        """INSERT ... SELECT should suggest columns in SELECT clause."""
        sql = "INSERT INTO users (id, name) SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert len(completions) > 0

    def test_insert_select_from_suggests_tables(self, schema):
        """INSERT ... SELECT ... FROM should suggest tables."""
        sql = "INSERT INTO users (id, name) SELECT id, name FROM "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions
        assert "products" in completions
