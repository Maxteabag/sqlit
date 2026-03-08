"""Tests for SQL edge cases and advanced patterns."""

import pytest

from sqlit.domains.query.completion import get_completions


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
