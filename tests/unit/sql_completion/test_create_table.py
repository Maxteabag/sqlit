"""Tests for CREATE TABLE statement autocomplete suggestions."""

import pytest

from sqlit.sql_completion import (
    SQL_CONSTRAINTS,
    SQL_DATA_TYPES,
    get_completions,
)


class TestCreateTableStatements:
    """Tests for CREATE TABLE autocomplete suggestions."""

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

    def test_create_table_column_name_no_suggestions(self, schema):
        """After CREATE TABLE name (, should not suggest (user types column name)."""
        sql = "CREATE TABLE new_table ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # No suggestions - user needs to type column name
        assert completions == []

    def test_create_table_after_column_name_suggests_types(self, schema):
        """After column name, should suggest data types."""
        sql = "CREATE TABLE new_table (id "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "INT" in completions
        assert "VARCHAR" in completions
        assert "TEXT" in completions
        assert "BOOLEAN" in completions

    def test_create_table_partial_type(self, schema):
        """Typing partial data type should filter."""
        sql = "CREATE TABLE new_table (id INT"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "INT" in completions
        assert "INTEGER" in completions

    def test_create_table_after_type_suggests_constraints(self, schema):
        """After data type, should suggest constraints."""
        sql = "CREATE TABLE new_table (id INT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "PRIMARY KEY" in completions
        assert "NOT NULL" in completions
        assert "UNIQUE" in completions
        assert "DEFAULT" in completions

    def test_create_table_after_type_with_size_suggests_constraints(self, schema):
        """After data type with size, should suggest constraints."""
        sql = "CREATE TABLE new_table (name VARCHAR(255) "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "NOT NULL" in completions
        assert "DEFAULT" in completions

    def test_create_table_partial_constraint(self, schema):
        """Typing partial constraint should filter."""
        sql = "CREATE TABLE new_table (id INT NOT"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "NOT NULL" in completions

    def test_create_table_second_column_no_suggestions(self, schema):
        """After comma, should not suggest (user types column name)."""
        sql = "CREATE TABLE new_table (id INT PRIMARY KEY, "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert completions == []

    def test_create_table_second_column_type(self, schema):
        """Second column should also get type suggestions."""
        sql = "CREATE TABLE new_table (id INT, name "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "VARCHAR" in completions
        assert "TEXT" in completions

    def test_create_table_references_suggests_tables(self, schema):
        """REFERENCES should suggest table names."""
        sql = "CREATE TABLE new_table (user_id INT REFERENCES "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_create_table_references_table_paren_suggests_columns(self, schema):
        """REFERENCES table( should suggest columns from that table."""
        sql = "CREATE TABLE new_table (user_id INT REFERENCES users("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "email" in completions

    def test_create_table_references_partial_column(self, schema):
        """Typing partial column in REFERENCES should filter."""
        sql = "CREATE TABLE new_table (user_id INT REFERENCES users(i"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions

    def test_create_table_foreign_key_references_suggests_tables(self, schema):
        """FOREIGN KEY ... REFERENCES should suggest tables."""
        sql = "CREATE TABLE new_table (id INT, FOREIGN KEY (user_id) REFERENCES "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions

    def test_create_table_multiline(self, schema):
        """Should work with multiline CREATE TABLE."""
        sql = """CREATE TABLE new_table (
            id INT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            user_id INT REFERENCES """
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions


class TestDataTypesAndConstraints:
    """Tests for data type and constraint lists."""

    def test_data_types_not_empty(self):
        """Should have data types defined."""
        assert len(SQL_DATA_TYPES) > 20
        assert "INT" in SQL_DATA_TYPES
        assert "VARCHAR" in SQL_DATA_TYPES
        assert "BOOLEAN" in SQL_DATA_TYPES

    def test_constraints_not_empty(self):
        """Should have constraints defined."""
        assert len(SQL_CONSTRAINTS) > 5
        assert "PRIMARY KEY" in SQL_CONSTRAINTS
        assert "NOT NULL" in SQL_CONSTRAINTS
        assert "UNIQUE" in SQL_CONSTRAINTS
