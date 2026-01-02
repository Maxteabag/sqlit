"""Tests for CREATE INDEX statement autocomplete suggestions."""

import pytest

from sqlit.domains.query.completion import get_completions


class TestCreateIndexStatements:
    """Tests for CREATE INDEX autocomplete suggestions."""

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

    def test_create_index_on_suggests_tables(self, schema):
        """CREATE INDEX name ON should suggest table names."""
        sql = "CREATE INDEX idx_user_email ON "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions
        assert "products" in completions

    def test_create_index_on_partial_table(self, schema):
        """Typing partial table name should filter."""
        sql = "CREATE INDEX idx_user_email ON us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" not in completions

    def test_create_unique_index_on_suggests_tables(self, schema):
        """CREATE UNIQUE INDEX name ON should suggest table names."""
        sql = "CREATE UNIQUE INDEX idx_user_email ON "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_create_index_table_paren_suggests_columns(self, schema):
        """CREATE INDEX name ON table ( should suggest columns."""
        sql = "CREATE INDEX idx_user_email ON users ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "email" in completions
        assert "created_at" in completions

    def test_create_index_partial_column(self, schema):
        """Typing partial column name should filter."""
        sql = "CREATE INDEX idx_user_email ON users (em"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "email" in completions
        assert "id" not in completions

    def test_create_index_second_column(self, schema):
        """After first column and comma, should suggest more columns."""
        sql = "CREATE INDEX idx_composite ON users (name, "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "email" in completions

    def test_create_index_after_name_suggests_on(self, schema):
        """After index name, should suggest ON keyword."""
        sql = "CREATE INDEX idx_user_email "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ON" in completions

    def test_create_unique_index_after_name_suggests_on(self, schema):
        """After UNIQUE INDEX name, should suggest ON keyword."""
        sql = "CREATE UNIQUE INDEX idx_user_email "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ON" in completions

    def test_create_index_unknown_table(self, schema):
        """CREATE INDEX on unknown table should return empty columns."""
        sql = "CREATE INDEX idx_test ON unknown_table ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert completions == []

    def test_create_index_different_table(self, schema):
        """CREATE INDEX on orders should suggest orders columns."""
        sql = "CREATE INDEX idx_order_status ON orders ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "user_id" in completions
        assert "total" in completions
        assert "status" in completions
        # Should not have users columns
        assert "email" not in completions
