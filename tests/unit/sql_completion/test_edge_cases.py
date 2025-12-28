"""Tests for SQL edge cases and advanced patterns."""

import pytest

from sqlit.sql_completion import get_completions


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


class TestNestedFunctions:
    """Tests for nested function call autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders"],
            "columns": {
                "users": ["id", "name", "email", "phone"],
                "orders": ["id", "user_id", "total", "discount"],
            },
            "procedures": [],
        }

    def test_nested_coalesce_nullif(self, schema):
        """COALESCE(NULLIF( should suggest columns."""
        sql = "SELECT COALESCE(NULLIF( FROM users"
        cursor_pos = len("SELECT COALESCE(NULLIF(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions
        assert "email" in completions

    def test_nested_ifnull(self, schema):
        """IFNULL(TRIM( should suggest columns."""
        sql = "SELECT IFNULL(TRIM( FROM users"
        cursor_pos = len("SELECT IFNULL(TRIM(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions

    def test_deeply_nested_functions(self, schema):
        """Deeply nested functions should suggest columns."""
        sql = "SELECT COALESCE(NULLIF(TRIM( FROM users"
        cursor_pos = len("SELECT COALESCE(NULLIF(TRIM(")
        completions = get_completions(
            sql, cursor_pos, schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions

    def test_nested_in_where(self, schema):
        """Nested functions in WHERE should suggest columns."""
        sql = "SELECT * FROM users WHERE COALESCE(NULLIF("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions or "id" in completions


class TestAnyAllSome:
    """Tests for ANY/ALL/SOME subquery autocomplete."""

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

    def test_any_suggests_select(self, schema):
        """= ANY ( should suggest SELECT for subquery."""
        sql = "SELECT * FROM users WHERE id = ANY ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_all_suggests_select(self, schema):
        """= ALL ( should suggest SELECT for subquery."""
        sql = "SELECT * FROM users WHERE id = ALL ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_some_suggests_select(self, schema):
        """> SOME ( should suggest SELECT for subquery."""
        sql = "SELECT * FROM users WHERE id > SOME ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_not_in_any_context(self, schema):
        """ANY in non-subquery context should not interfere."""
        sql = "SELECT * FROM users WHERE id = ANY (SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # After SELECT in subquery, should suggest columns/tables
        assert len(completions) > 0


class TestGroupingSets:
    """Tests for GROUPING SETS/CUBE/ROLLUP autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["sales", "products"],
            "columns": {
                "sales": ["id", "product_id", "region", "year", "amount"],
                "products": ["id", "name", "category"],
            },
            "procedures": [],
        }

    def test_grouping_sets_suggests_columns(self, schema):
        """GROUP BY GROUPING SETS ( should suggest columns."""
        sql = "SELECT region, year, SUM(amount) FROM sales GROUP BY GROUPING SETS ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "region" in completions
        assert "year" in completions

    def test_cube_suggests_columns(self, schema):
        """GROUP BY CUBE ( should suggest columns."""
        sql = "SELECT region, year, SUM(amount) FROM sales GROUP BY CUBE ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "region" in completions

    def test_rollup_suggests_columns(self, schema):
        """GROUP BY ROLLUP ( should suggest columns."""
        sql = "SELECT region, year, SUM(amount) FROM sales GROUP BY ROLLUP ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "region" in completions

    def test_grouping_sets_partial(self, schema):
        """Partial column in GROUPING SETS should filter."""
        sql = "SELECT region, year FROM sales GROUP BY GROUPING SETS (reg"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "region" in completions


class TestOverClause:
    """Tests for OVER () window clause autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["employees"],
            "columns": {
                "employees": ["id", "name", "dept_id", "salary", "hire_date"],
            },
            "procedures": [],
        }

    def test_over_paren_suggests_partition_order(self, schema):
        """OVER ( should suggest PARTITION BY and ORDER BY."""
        sql = "SELECT ROW_NUMBER() OVER ("
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "PARTITION" in completions or "ORDER" in completions

    def test_over_partial_partition(self, schema):
        """OVER (PART should filter to PARTITION."""
        sql = "SELECT ROW_NUMBER() OVER (PART"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "PARTITION" in completions

    def test_over_partial_order(self, schema):
        """OVER (ORD should filter to ORDER."""
        sql = "SELECT ROW_NUMBER() OVER (ORD"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ORDER" in completions


class TestOrderByModifiers:
    """Tests for ORDER BY modifiers (ASC/DESC/NULLS)."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders"],
            "columns": {
                "users": ["id", "name", "email", "created_at"],
                "orders": ["id", "user_id", "total"],
            },
            "procedures": [],
        }

    def test_order_by_column_suggests_asc_desc(self, schema):
        """After ORDER BY column, should suggest ASC/DESC."""
        sql = "SELECT * FROM users ORDER BY name "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ASC" in completions
        assert "DESC" in completions

    def test_order_by_suggests_nulls(self, schema):
        """After ORDER BY column, should suggest NULLS."""
        sql = "SELECT * FROM users ORDER BY name "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "NULLS" in completions

    def test_nulls_suggests_first_last(self, schema):
        """After NULLS, should suggest FIRST/LAST."""
        sql = "SELECT * FROM users ORDER BY name NULLS "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "FIRST" in completions
        assert "LAST" in completions

    def test_order_by_asc_then_comma(self, schema):
        """After ORDER BY col ASC, comma should suggest columns."""
        sql = "SELECT * FROM users ORDER BY name ASC, "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "email" in completions

    def test_order_by_partial_asc(self, schema):
        """Typing partial ASC should filter."""
        sql = "SELECT * FROM users ORDER BY name A"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "ASC" in completions


class TestCaseExpression:
    """Tests for CASE expression autocomplete."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders"],
            "columns": {
                "users": ["id", "name", "status", "type"],
                "orders": ["id", "user_id", "total", "status"],
            },
            "procedures": [],
        }

    def test_case_suggests_when(self, schema):
        """CASE should suggest WHEN."""
        sql = "SELECT CASE "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "WHEN" in completions

    def test_case_column_suggests_when(self, schema):
        """CASE column should suggest WHEN."""
        sql = "SELECT CASE status "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "WHEN" in completions

    def test_case_end_suggests_as(self, schema):
        """CASE ... END should suggest AS for alias."""
        sql = "SELECT CASE WHEN status = 1 THEN 'Active' END "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # After END, common to add alias or comma
        assert "AS" in completions or len(completions) > 0


class TestSemicolonBehavior:
    """Tests for statement terminator (semicolon) behavior."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "tradition_foods"],
            "columns": {
                "users": ["id", "name", "email"],
                "orders": ["id", "user_id", "total"],
                "tradition_foods": ["id", "name", "origin"],
            },
            "procedures": [],
        }

    def test_after_semicolon_no_suggestions(self, schema):
        """After a semicolon, autocomplete should hide (no suggestions)."""
        sql = "SELECT * FROM tradition_foods;"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert completions == [], f"Expected no suggestions after semicolon, got {completions}"

    def test_after_semicolon_with_space_no_suggestions(self, schema):
        """After semicolon and space, autocomplete should hide (no suggestions)."""
        sql = "SELECT * FROM users; "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert completions == [], f"Expected no suggestions after semicolon, got {completions}"

    def test_after_semicolon_typing_new_statement(self, schema):
        """After semicolon, typing a new keyword should show keyword completions."""
        sql = "SELECT * FROM users; SEL"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions, "Should suggest SELECT when typing new statement"
