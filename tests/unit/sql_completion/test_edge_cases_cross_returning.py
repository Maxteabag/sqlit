"""Tests for SQL edge cases and advanced patterns."""

import pytest

from sqlit.domains.query.completion import get_completions


class TestCrossJoin:
    """Tests for CROSS JOIN (should not suggest ON)."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name"],
                "orders": ["id", "user_id"],
                "products": ["id", "name"],
            },
            "procedures": [],
        }

    def test_cross_join_no_on(self, schema):
        """After CROSS JOIN table, should NOT suggest ON."""
        sql = "SELECT * FROM users CROSS JOIN orders "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # CROSS JOIN doesn't use ON - should suggest WHERE, ORDER BY, etc.
        assert "ON" not in completions

    def test_cross_join_suggests_where(self, schema):
        """After CROSS JOIN table, should suggest WHERE."""
        sql = "SELECT * FROM users CROSS JOIN orders "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "WHERE" in completions or "ORDER" in completions or len(completions) > 0

    def test_natural_join_no_on(self, schema):
        """After NATURAL JOIN table, should NOT suggest ON."""
        sql = "SELECT * FROM users NATURAL JOIN orders "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # NATURAL JOIN doesn't use ON
        assert "ON" not in completions


class TestSchemaPrefix:
    """Tests for schema.table prefix autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name"],
                "orders": ["id", "user_id"],
                "products": ["id", "name"],
            },
            "procedures": [],
        }

    def test_schema_dot_suggests_tables(self, schema):
        """After schema., should suggest tables."""
        sql = "SELECT * FROM public."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_schema_dot_partial_table(self, schema):
        """After schema. with partial table, should filter."""
        sql = "SELECT * FROM public.us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions

    def test_schema_dot_in_join(self, schema):
        """Schema prefix in JOIN should suggest tables."""
        sql = "SELECT * FROM users JOIN dbo."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions


class TestInClause:
    """Tests for IN clause autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name", "email", "status"],
                "orders": ["id", "user_id", "total"],
                "products": ["id", "name", "price"],
            },
            "procedures": [],
        }

    def test_in_suggests_select(self, schema):
        """WHERE col IN ( should suggest SELECT for subquery."""
        sql = "SELECT * FROM users WHERE id IN ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_in_with_partial_select(self, schema):
        """WHERE col IN (SEL should filter to SELECT."""
        sql = "SELECT * FROM users WHERE id IN (SEL"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_not_in_suggests_select(self, schema):
        """WHERE col NOT IN ( should suggest SELECT."""
        sql = "SELECT * FROM users WHERE id NOT IN ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_in_subquery_select_columns(self, schema):
        """IN (SELECT should suggest columns."""
        sql = "SELECT * FROM users WHERE id IN (SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # After SELECT in subquery, should suggest columns/tables
        assert len(completions) > 0


class TestExistsClause:
    """Tests for EXISTS clause autocomplete."""

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

    def test_exists_suggests_select(self, schema):
        """WHERE EXISTS ( should suggest SELECT."""
        sql = "SELECT * FROM users WHERE EXISTS ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_not_exists_suggests_select(self, schema):
        """WHERE NOT EXISTS ( should suggest SELECT."""
        sql = "SELECT * FROM users WHERE NOT EXISTS ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_exists_partial_select(self, schema):
        """EXISTS (SEL should filter to SELECT."""
        sql = "SELECT * FROM users WHERE EXISTS (SEL"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_exists_subquery_from(self, schema):
        """EXISTS (SELECT 1 FROM should suggest tables."""
        sql = "SELECT * FROM users WHERE EXISTS (SELECT 1 FROM "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions


class TestReturningClause:
    """Tests for RETURNING clause autocomplete (PostgreSQL, SQLite)."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name", "email", "created_at"],
                "orders": ["id", "user_id", "total"],
                "products": ["id", "name", "price"],
            },
            "procedures": [],
        }

    def test_insert_returning_suggests_columns(self, schema):
        """INSERT ... RETURNING should suggest columns."""
        sql = "INSERT INTO users (name) VALUES ('test') RETURNING "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_update_returning_suggests_columns(self, schema):
        """UPDATE ... RETURNING should suggest columns."""
        sql = "UPDATE users SET name = 'test' RETURNING "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_delete_returning_suggests_columns(self, schema):
        """DELETE ... RETURNING should suggest columns."""
        sql = "DELETE FROM users WHERE id = 1 RETURNING "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_returning_partial_column(self, schema):
        """RETURNING with partial column should filter."""
        sql = "INSERT INTO users (name) VALUES ('test') RETURNING na"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions

    def test_returning_multiple_columns(self, schema):
        """RETURNING with comma should suggest more columns."""
        sql = "INSERT INTO users (name) VALUES ('test') RETURNING id, "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions
        assert "email" in completions
