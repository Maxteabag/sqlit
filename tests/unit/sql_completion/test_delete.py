"""Tests for DELETE statement autocomplete suggestions."""

import pytest

from sqlit.sql_completion import (
    SuggestionType,
    extract_delete_table_refs,
    get_completions,
    get_context,
)


class TestDeleteStatements:
    """Tests for DELETE statement autocomplete suggestions."""

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

    def test_delete_from_suggests_tables(self, schema):
        """After DELETE FROM, should suggest table names."""
        sql = "DELETE FROM "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_delete_from_partial_table(self, schema):
        """Typing partial table name after DELETE FROM."""
        sql = "DELETE FROM us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions

    def test_delete_where_suggests_columns(self, schema):
        """After DELETE FROM table WHERE, should suggest columns."""
        sql = "DELETE FROM users WHERE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "status" in completions

    def test_delete_where_partial_column(self, schema):
        """Typing partial column in WHERE clause."""
        sql = "DELETE FROM users WHERE st"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "status" in completions

    def test_delete_where_with_alias_dot(self, schema):
        """DELETE with alias should suggest columns via alias."""
        sql = "DELETE FROM users u WHERE u."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "status" in completions

    def test_delete_where_operator_after_column(self, schema):
        """After column name in DELETE WHERE, should suggest operators."""
        sql = "DELETE FROM users WHERE id "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "=" in completions
        assert "IN" in completions
        assert "IS NULL" in completions

    def test_delete_where_and_suggests_columns(self, schema):
        """After AND in DELETE WHERE, should suggest columns."""
        sql = "DELETE FROM users WHERE id = 1 AND "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions
        assert "status" in completions

    def test_delete_no_suggestions_in_string(self, schema):
        """Inside string literal, should NOT suggest anything."""
        sql = "DELETE FROM users WHERE name = '"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert completions == []

    def test_delete_subquery_from_suggests_tables(self, schema):
        """DELETE with subquery FROM should suggest tables."""
        sql = "DELETE FROM users WHERE id IN (SELECT user_id FROM "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions

    def test_delete_join_suggests_tables(self, schema):
        """DELETE with JOIN should suggest tables (MySQL/SQL Server style)."""
        sql = "DELETE u FROM users u JOIN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions

    def test_delete_using_suggests_tables(self, schema):
        """DELETE USING should suggest tables (PostgreSQL style)."""
        sql = "DELETE FROM users USING "
        suggestions = get_context(sql, len(sql))
        # USING should trigger table suggestions (falls back to keyword detection)
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should have some completions
        assert len(completions) > 0


class TestExtractDeleteTableRefs:
    """Tests for DELETE table reference extraction."""

    def test_simple_delete(self):
        """Extract table from simple DELETE."""
        sql = "DELETE FROM users WHERE id = 1"
        refs = extract_delete_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"

    def test_delete_with_alias(self):
        """Extract table with alias from DELETE."""
        sql = "DELETE FROM users u WHERE u.id = 1"
        refs = extract_delete_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"
        assert refs[0].alias == "u"

    def test_delete_with_schema(self):
        """Extract schema-qualified table from DELETE."""
        sql = "DELETE FROM dbo.users WHERE id = 1"
        refs = extract_delete_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].schema == "dbo"
        assert refs[0].name == "users"

    def test_delete_quoted_table(self):
        """Extract quoted table from DELETE."""
        sql = 'DELETE FROM "user_accounts" WHERE id = 1'
        refs = extract_delete_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "user_accounts"

    def test_delete_no_where(self):
        """Extract table from DELETE without WHERE."""
        sql = "DELETE FROM temp_data"
        refs = extract_delete_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "temp_data"

    def test_delete_reserved_word_not_alias(self):
        """Reserved words should not be captured as aliases."""
        sql = "DELETE FROM users WHERE id = 1"
        refs = extract_delete_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].alias is None
