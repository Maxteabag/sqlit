"""Tests for ALTER TABLE statement autocomplete suggestions."""

import pytest

from sqlit.sql_completion import (
    ALTER_OPERATIONS,
    SQL_CONSTRAINTS,
    SQL_DATA_TYPES,
    get_completions,
)


class TestAlterTableStatements:
    """Tests for ALTER TABLE autocomplete suggestions."""

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

    def test_alter_table_suggests_tables(self, schema):
        """ALTER TABLE should suggest table names."""
        sql = "ALTER TABLE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions
        assert "products" in completions

    def test_alter_table_partial_table(self, schema):
        """Typing partial table name should filter."""
        sql = "ALTER TABLE us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" not in completions

    def test_alter_table_after_table_suggests_operations(self, schema):
        """After table name, should suggest ALTER operations."""
        sql = "ALTER TABLE users "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ADD" in completions
        assert "DROP" in completions
        assert "ALTER" in completions
        assert "MODIFY" in completions
        assert "RENAME" in completions

    def test_alter_table_partial_operation(self, schema):
        """Typing partial operation should filter."""
        sql = "ALTER TABLE users AD"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ADD" in completions
        assert "ADD COLUMN" in completions
        assert "DROP" not in completions

    def test_alter_table_drop_column_suggests_columns(self, schema):
        """DROP COLUMN should suggest existing columns."""
        sql = "ALTER TABLE users DROP COLUMN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "email" in completions

    def test_alter_table_drop_without_column_keyword(self, schema):
        """DROP (without COLUMN) should suggest existing columns."""
        sql = "ALTER TABLE users DROP "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_alter_table_alter_column_suggests_columns(self, schema):
        """ALTER COLUMN should suggest existing columns."""
        sql = "ALTER TABLE orders ALTER COLUMN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "user_id" in completions
        assert "total" in completions

    def test_alter_table_modify_column_suggests_columns(self, schema):
        """MODIFY COLUMN should suggest existing columns."""
        sql = "ALTER TABLE products MODIFY COLUMN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "price" in completions

    def test_alter_table_rename_column_suggests_columns(self, schema):
        """RENAME COLUMN should suggest existing columns."""
        sql = "ALTER TABLE users RENAME COLUMN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "email" in completions

    def test_alter_table_add_column_type(self, schema):
        """ADD COLUMN name should suggest data types."""
        sql = "ALTER TABLE users ADD COLUMN age "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "INT" in completions
        assert "VARCHAR" in completions
        assert "TEXT" in completions

    def test_alter_table_add_without_column_keyword(self, schema):
        """ADD name (without COLUMN) should suggest data types."""
        sql = "ALTER TABLE users ADD age "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "INT" in completions
        assert "VARCHAR" in completions

    def test_alter_table_add_column_constraint(self, schema):
        """After data type, should suggest constraints."""
        sql = "ALTER TABLE users ADD COLUMN age INT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "NOT NULL" in completions
        assert "DEFAULT" in completions
        assert "UNIQUE" in completions

    def test_alter_table_references_suggests_tables(self, schema):
        """REFERENCES should suggest table names."""
        sql = "ALTER TABLE orders ADD COLUMN product_id INT REFERENCES "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "products" in completions
        assert "users" in completions

    def test_alter_table_references_table_paren_suggests_columns(self, schema):
        """REFERENCES table( should suggest columns from that table."""
        sql = "ALTER TABLE orders ADD COLUMN product_id INT REFERENCES products("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "price" in completions

    def test_alter_table_partial_column_filter(self, schema):
        """Typing partial column name should filter."""
        sql = "ALTER TABLE users DROP COLUMN em"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "email" in completions
        assert "id" not in completions

    def test_alter_table_unknown_table(self, schema):
        """ALTER TABLE with unknown table should return empty columns."""
        sql = "ALTER TABLE unknown_table DROP COLUMN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should return empty list since table doesn't exist
        assert completions == []


class TestAlterOperations:
    """Tests for ALTER_OPERATIONS list."""

    def test_alter_operations_not_empty(self):
        """Should have ALTER operations defined."""
        assert len(ALTER_OPERATIONS) > 10
        assert "ADD" in ALTER_OPERATIONS
        assert "DROP" in ALTER_OPERATIONS
        assert "ALTER" in ALTER_OPERATIONS
        assert "MODIFY" in ALTER_OPERATIONS
        assert "RENAME" in ALTER_OPERATIONS
