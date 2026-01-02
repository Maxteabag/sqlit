"""Tests for SQL edge cases and advanced patterns."""

import pytest

from sqlit.domains.query.completion import get_completions


class TestUnionContext:
    """Tests for UNION/INTERSECT/EXCEPT autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "admins", "guests"],
            "columns": {
                "users": ["id", "name", "email"],
                "admins": ["id", "name", "role"],
                "guests": ["id", "name", "expires"],
            },
            "procedures": [],
        }

    def test_union_suggests_select(self, schema):
        """After UNION, should suggest SELECT."""
        sql = "SELECT * FROM users UNION "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_union_all_suggests_select(self, schema):
        """After UNION ALL, should suggest SELECT."""
        sql = "SELECT * FROM users UNION ALL "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_intersect_suggests_select(self, schema):
        """After INTERSECT, should suggest SELECT."""
        sql = "SELECT * FROM users INTERSECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_except_suggests_select(self, schema):
        """After EXCEPT, should suggest SELECT."""
        sql = "SELECT * FROM users EXCEPT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_union_partial_select(self, schema):
        """Typing partial SELECT after UNION should filter."""
        sql = "SELECT * FROM users UNION SEL"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions


class TestBetweenContext:
    """Tests for BETWEEN clause autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "products"],
            "columns": {
                "users": ["id", "name", "age", "created_at"],
                "products": ["id", "name", "price", "stock"],
            },
            "procedures": [],
        }

    def test_between_suggests_columns(self, schema):
        """After BETWEEN, should suggest columns/values."""
        sql = "SELECT * FROM users WHERE age BETWEEN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should suggest columns (for comparing with another column) or allow typing value
        assert "id" in completions or len(completions) > 0

    def test_between_and_suggests_columns(self, schema):
        """After BETWEEN x AND, should suggest columns/values."""
        sql = "SELECT * FROM users WHERE age BETWEEN 18 AND "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # AND in BETWEEN context should suggest columns
        assert "id" in completions or "age" in completions

    def test_between_with_columns(self, schema):
        """BETWEEN with column references."""
        sql = "SELECT * FROM products WHERE price BETWEEN min_price AND "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert len(completions) > 0


class TestComplexSubqueries:
    """Tests for complex subquery scenarios."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name", "email"],
                "orders": ["id", "user_id", "product_id", "total"],
                "products": ["id", "name", "price"],
            },
            "procedures": [],
        }

    def test_nested_subquery_from(self, schema):
        """Nested subquery FROM should suggest tables."""
        sql = "SELECT * FROM (SELECT * FROM (SELECT * FROM "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions
        assert "orders" in completions

    def test_correlated_subquery_where(self, schema):
        """Correlated subquery in WHERE."""
        sql = "SELECT * FROM users u WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should suggest users columns for u.
        assert "id" in completions

    def test_subquery_in_select_list(self, schema):
        """Subquery in SELECT list."""
        sql = "SELECT id, (SELECT COUNT(*) FROM orders WHERE user_id = users."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions


class TestAggregateFunctions:
    """Tests for aggregate function argument autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products"],
            "columns": {
                "users": ["id", "name", "email", "age"],
                "orders": ["id", "user_id", "total", "quantity"],
                "products": ["id", "name", "price", "stock"],
            },
            "procedures": [],
        }

    def test_count_suggests_columns(self, schema):
        """COUNT( should suggest columns from tables in query."""
        sql = "SELECT COUNT( FROM users"
        cursor_pos = len("SELECT COUNT(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_sum_suggests_columns(self, schema):
        """SUM( should suggest columns."""
        sql = "SELECT SUM( FROM orders"
        cursor_pos = len("SELECT SUM(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "total" in completions
        assert "quantity" in completions

    def test_avg_suggests_columns(self, schema):
        """AVG( should suggest columns."""
        sql = "SELECT AVG( FROM products"
        cursor_pos = len("SELECT AVG(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "price" in completions
        assert "stock" in completions

    def test_max_suggests_columns(self, schema):
        """MAX( should suggest columns."""
        sql = "SELECT MAX( FROM users"
        cursor_pos = len("SELECT MAX(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "age" in completions

    def test_min_suggests_columns(self, schema):
        """MIN( should suggest columns."""
        sql = "SELECT MIN( FROM orders"
        cursor_pos = len("SELECT MIN(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "total" in completions

    def test_count_with_alias(self, schema):
        """COUNT( with table alias should suggest columns."""
        sql = "SELECT COUNT(u. FROM users u"
        cursor_pos = len("SELECT COUNT(u.")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_aggregate_in_having(self, schema):
        """Aggregate in HAVING should suggest columns."""
        sql = "SELECT dept FROM users GROUP BY dept HAVING COUNT( "
        cursor_pos = len("SELECT dept FROM users GROUP BY dept HAVING COUNT(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions


class TestCastExpression:
    """Tests for CAST expression autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders"],
            "columns": {
                "users": ["id", "name", "age"],
                "orders": ["id", "total", "created_at"],
            },
            "procedures": [],
        }

    def test_cast_as_suggests_types(self, schema):
        """CAST(col AS should suggest data types."""
        sql = "SELECT CAST(id AS  FROM users"
        cursor_pos = len("SELECT CAST(id AS ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "INT" in completions or "INTEGER" in completions
        assert "VARCHAR" in completions

    def test_cast_column_suggests_columns(self, schema):
        """CAST( should suggest columns."""
        sql = "SELECT CAST( FROM users"
        cursor_pos = len("SELECT CAST(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_convert_type_suggests_types(self, schema):
        """CONVERT with type argument should suggest types (SQL Server style)."""
        sql = "SELECT CONVERT( "
        cursor_pos = len("SELECT CONVERT(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        # CONVERT first arg is usually type in SQL Server
        assert "INT" in completions or "VARCHAR" in completions or len(completions) > 0
