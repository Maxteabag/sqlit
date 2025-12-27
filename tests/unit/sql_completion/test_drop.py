"""Tests for DROP statement autocomplete suggestions."""

import pytest

from sqlit.sql_completion import (
    DROP_OBJECTS,
    get_completions,
)


class TestDropStatements:
    """Tests for DROP autocomplete suggestions."""

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
            "procedures": ["get_user", "update_order", "calculate_total"],
        }

    def test_drop_suggests_object_types(self, schema):
        """DROP should suggest object types."""
        sql = "DROP "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "TABLE" in completions
        assert "VIEW" in completions
        assert "INDEX" in completions
        assert "DATABASE" in completions
        assert "PROCEDURE" in completions

    def test_drop_partial_object_type(self, schema):
        """Typing partial object type should filter."""
        sql = "DROP TAB"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "TABLE" in completions
        assert "VIEW" not in completions

    def test_drop_table_suggests_tables(self, schema):
        """DROP TABLE should suggest table names."""
        sql = "DROP TABLE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions
        assert "products" in completions

    def test_drop_table_partial_name(self, schema):
        """Typing partial table name should filter."""
        sql = "DROP TABLE us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" not in completions

    def test_drop_table_if_exists_suggests_tables(self, schema):
        """DROP TABLE IF EXISTS should suggest table names."""
        sql = "DROP TABLE IF EXISTS "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_drop_table_if_exists_partial(self, schema):
        """DROP TABLE IF EXISTS with partial name should filter."""
        sql = "DROP TABLE IF EXISTS ord"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions
        assert "users" not in completions

    def test_drop_view_suggests_tables(self, schema):
        """DROP VIEW should suggest tables (views mixed with tables)."""
        sql = "DROP VIEW "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_drop_view_if_exists(self, schema):
        """DROP VIEW IF EXISTS should suggest tables."""
        sql = "DROP VIEW IF EXISTS "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions

    def test_drop_procedure_suggests_procedures(self, schema):
        """DROP PROCEDURE should suggest procedure names."""
        sql = "DROP PROCEDURE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "get_user" in completions
        assert "update_order" in completions
        assert "calculate_total" in completions

    def test_drop_procedure_partial_name(self, schema):
        """Typing partial procedure name should filter."""
        sql = "DROP PROCEDURE get"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "get_user" in completions
        assert "update_order" not in completions

    def test_drop_procedure_if_exists(self, schema):
        """DROP PROCEDURE IF EXISTS should suggest procedures."""
        sql = "DROP PROCEDURE IF EXISTS "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "get_user" in completions
        assert "update_order" in completions

    def test_drop_function_suggests_procedures(self, schema):
        """DROP FUNCTION should suggest procedures (treated same as procedures)."""
        sql = "DROP FUNCTION "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "get_user" in completions
        assert "calculate_total" in completions

    def test_drop_function_if_exists(self, schema):
        """DROP FUNCTION IF EXISTS should suggest procedures."""
        sql = "DROP FUNCTION IF EXISTS "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "get_user" in completions

    def test_drop_no_procedures(self, schema):
        """DROP PROCEDURE with no procedures should return empty."""
        sql = "DROP PROCEDURE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], None
        )
        assert completions == []


class TestDropObjects:
    """Tests for DROP_OBJECTS list."""

    def test_drop_objects_not_empty(self):
        """Should have DROP object types defined."""
        assert len(DROP_OBJECTS) > 5
        assert "TABLE" in DROP_OBJECTS
        assert "VIEW" in DROP_OBJECTS
        assert "INDEX" in DROP_OBJECTS
        assert "DATABASE" in DROP_OBJECTS
        assert "PROCEDURE" in DROP_OBJECTS
        assert "FUNCTION" in DROP_OBJECTS
