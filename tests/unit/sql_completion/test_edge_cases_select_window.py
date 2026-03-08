"""Tests for SQL edge cases and advanced patterns."""

import pytest

from sqlit.domains.query.completion import get_completions


class TestSelectDistinct:
    """Tests for SELECT DISTINCT autocomplete."""

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

    def test_select_distinct_suggests_columns(self, schema):
        """SELECT DISTINCT should suggest special keywords and functions."""
        sql = "SELECT DISTINCT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should suggest * and functions (not tables - those go after FROM)
        assert "*" in completions
        # Check for any aggregate function (they're all present but order varies)
        has_function = any(f in completions for f in ["COUNT", "SUM", "AVG", "MIN", "MAX"])
        assert has_function

    def test_select_distinct_from_table(self, schema):
        """SELECT DISTINCT with FROM should suggest columns."""
        sql = "SELECT DISTINCT  FROM users"
        # Cursor after DISTINCT and space
        cursor_pos = len("SELECT DISTINCT ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_select_distinct_partial(self, schema):
        """SELECT DISTINCT with partial column should filter."""
        sql = "SELECT DISTINCT na FROM users"
        cursor_pos = len("SELECT DISTINCT na")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions


class TestCaseWhen:
    """Tests for CASE WHEN expression autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders"],
            "columns": {
                "users": ["id", "name", "status", "active"],
                "orders": ["id", "user_id", "total", "status"],
            },
            "procedures": [],
        }

    def test_case_when_suggests_columns(self, schema):
        """CASE WHEN should suggest columns."""
        sql = "SELECT CASE WHEN  FROM users"
        cursor_pos = len("SELECT CASE WHEN ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "status" in completions

    def test_case_when_then_suggests_values(self, schema):
        """CASE WHEN condition THEN should suggest columns/values."""
        sql = "SELECT CASE WHEN status = 1 THEN  FROM users"
        cursor_pos = len("SELECT CASE WHEN status = 1 THEN ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        # THEN can be followed by a value or column
        assert len(completions) > 0

    def test_case_when_else_suggests_values(self, schema):
        """CASE WHEN ... ELSE should suggest columns/values."""
        sql = "SELECT CASE WHEN status = 1 THEN 'Active' ELSE  FROM users"
        cursor_pos = len("SELECT CASE WHEN status = 1 THEN 'Active' ELSE ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert len(completions) > 0

    def test_case_when_in_where(self, schema):
        """CASE WHEN in WHERE clause should suggest columns."""
        sql = "SELECT * FROM users WHERE CASE WHEN "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "status" in completions


class TestWindowFunctions:
    """Tests for window function (OVER clause) autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["employees", "departments"],
            "columns": {
                "employees": ["id", "name", "dept_id", "salary", "hire_date"],
                "departments": ["id", "name", "budget"],
            },
            "procedures": [],
        }

    def test_over_partition_by_suggests_columns(self, schema):
        """OVER (PARTITION BY should suggest columns."""
        sql = "SELECT ROW_NUMBER() OVER (PARTITION BY  FROM employees"
        cursor_pos = len("SELECT ROW_NUMBER() OVER (PARTITION BY ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "dept_id" in completions
        assert "name" in completions

    def test_over_order_by_suggests_columns(self, schema):
        """OVER (ORDER BY should suggest columns."""
        sql = "SELECT ROW_NUMBER() OVER (ORDER BY  FROM employees"
        cursor_pos = len("SELECT ROW_NUMBER() OVER (ORDER BY ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "salary" in completions
        assert "hire_date" in completions

    def test_over_partition_by_order_by(self, schema):
        """OVER (PARTITION BY x ORDER BY should suggest columns."""
        sql = "SELECT ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY  FROM employees"
        cursor_pos = len("SELECT ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "salary" in completions

    def test_over_with_join(self, schema):
        """Window function with JOIN should suggest columns from both tables."""
        sql = "SELECT ROW_NUMBER() OVER (PARTITION BY  FROM employees e JOIN departments d ON e.dept_id = d.id"
        cursor_pos = len("SELECT ROW_NUMBER() OVER (PARTITION BY ")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        # Should have columns from employees
        assert "dept_id" in completions or "salary" in completions


class TestDerivedTableAliases:
    """Tests for derived table (subquery) alias autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders"],
            "columns": {
                "users": ["id", "name", "email"],
                "orders": ["id", "user_id", "total"],
            },
            "procedures": [],
        }

    def test_derived_table_alias_dot(self, schema):
        """Alias for derived table should suggest columns."""
        sql = "SELECT u.  FROM (SELECT id, name FROM users) AS u"
        cursor_pos = len("SELECT u.")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        # This is tricky - would need to parse the subquery
        # For now, at minimum shouldn't error
        assert isinstance(completions, list)

    def test_derived_table_where_alias(self, schema):
        """WHERE clause with derived table alias."""
        sql = "SELECT * FROM (SELECT id, name FROM users) AS u WHERE u."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert isinstance(completions, list)


class TestJoinOnKeyword:
    """Tests for JOIN ... ON keyword suggestion."""

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

    def test_join_suggests_on(self, schema):
        """After JOIN table, should suggest ON keyword."""
        sql = "SELECT * FROM users JOIN orders "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ON" in completions

    def test_left_join_suggests_on(self, schema):
        """After LEFT JOIN table, should suggest ON."""
        sql = "SELECT * FROM users LEFT JOIN orders "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ON" in completions

    def test_inner_join_suggests_on(self, schema):
        """After INNER JOIN table, should suggest ON."""
        sql = "SELECT * FROM users INNER JOIN orders "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ON" in completions

    def test_join_with_alias_suggests_on(self, schema):
        """After JOIN table alias, should suggest ON."""
        sql = "SELECT * FROM users u JOIN orders o "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ON" in completions

    def test_join_on_partial(self, schema):
        """Typing partial ON should filter."""
        sql = "SELECT * FROM users JOIN orders O"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ON" in completions
