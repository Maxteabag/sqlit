"""Tests for SELECT statement autocomplete suggestions."""

import pytest

from sqlit.sql_completion import (
    SuggestionType,
    get_completions,
    get_context,
)


class TestSelectContext:
    """Tests for SELECT context detection."""

    def test_after_from(self):
        """After FROM should suggest tables."""
        sql = "SELECT * FROM "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

    def test_after_join(self):
        """After JOIN should suggest tables."""
        sql = "SELECT * FROM users u JOIN "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

    def test_after_left_join(self):
        """After LEFT JOIN should suggest tables."""
        sql = "SELECT * FROM users u LEFT JOIN "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

    def test_after_select(self):
        """After SELECT should suggest columns."""
        sql = "SELECT "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.COLUMN for s in suggestions)

    def test_after_where(self):
        """After WHERE should suggest columns."""
        sql = "SELECT * FROM users WHERE "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.COLUMN for s in suggestions)

    def test_after_and(self):
        """After AND should suggest columns."""
        sql = "SELECT * FROM users WHERE id = 1 AND "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.COLUMN for s in suggestions)

    def test_table_dot_pattern(self):
        """table. pattern should suggest columns for that table."""
        sql = "SELECT * FROM users u WHERE u."
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.ALIAS_COLUMN for s in suggestions)
        alias_suggestion = next(s for s in suggestions if s.type == SuggestionType.ALIAS_COLUMN)
        assert alias_suggestion.table_scope == "u"

    def test_after_order_by(self):
        """After ORDER BY should suggest columns."""
        sql = "SELECT * FROM users ORDER BY "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.COLUMN for s in suggestions)

    def test_after_group_by(self):
        """After GROUP BY should suggest columns."""
        sql = "SELECT * FROM users GROUP BY "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.COLUMN for s in suggestions)

    def test_after_exec(self):
        """After EXEC should suggest procedures."""
        sql = "EXEC "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.PROCEDURE for s in suggestions)

    def test_comma_in_select(self):
        """Comma in SELECT should suggest columns."""
        sql = "SELECT id, "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.COLUMN for s in suggestions)

    def test_comma_in_from(self):
        """Comma in FROM should suggest tables."""
        sql = "SELECT * FROM users, "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

    def test_start_of_query(self):
        """Start of query should suggest keywords."""
        sql = ""
        suggestions = get_context(sql, 0)
        assert any(s.type == SuggestionType.KEYWORD for s in suggestions)


class TestSelectCompletions:
    """Integration tests for SELECT completion flow."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders", "products", "order_items"],
            "columns": {
                "users": ["id", "name", "email", "created_at"],
                "orders": ["id", "user_id", "total", "status", "created_at"],
                "products": ["id", "name", "price", "category"],
                "order_items": ["id", "order_id", "product_id", "quantity"],
            },
            "procedures": ["sp_get_user", "sp_create_order", "sp_update_inventory"],
        }

    def test_complete_table_after_from(self, schema):
        """Should complete table names after FROM."""
        sql = "SELECT * FROM us"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "users" in completions

    def test_complete_table_fuzzy(self, schema):
        """Should fuzzy match table names."""
        sql = "SELECT * FROM ord"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions
        assert "order_items" in completions

    def test_complete_column_with_alias(self, schema):
        """Should complete columns for aliased table."""
        sql = "SELECT * FROM users u WHERE u."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions
        assert "email" in completions

    def test_complete_column_with_alias_partial(self, schema):
        """Should complete partial column for aliased table."""
        sql = "SELECT * FROM users u WHERE u.na"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "name" in completions

    def test_complete_column_direct_table(self, schema):
        """Should complete columns for direct table reference."""
        sql = "SELECT * FROM users WHERE users."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions
        assert "name" in completions

    def test_complete_columns_in_where(self, schema):
        """Should complete columns in WHERE clause."""
        sql = "SELECT * FROM users WHERE i"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "id" in completions

    def test_complete_procedure_after_exec(self, schema):
        """Should complete procedures after EXEC."""
        sql = "EXEC sp_"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "sp_get_user" in completions
        assert "sp_create_order" in completions

    def test_complete_includes_keywords(self, schema):
        """Should include keywords when appropriate."""
        sql = "SEL"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "SELECT" in completions

    def test_complete_includes_functions(self, schema):
        """Should include functions in SELECT context."""
        sql = "SELECT COU"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "COUNT" in completions

    def test_complete_join_table(self, schema):
        """Should complete table after JOIN."""
        sql = "SELECT * FROM users u JOIN ord"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "orders" in completions

    def test_complete_multiple_aliases(self, schema):
        """Should handle multiple aliases correctly."""
        sql = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE o."
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "user_id" in completions
        assert "total" in completions
        assert "status" in completions

    def test_no_duplicate_completions(self, schema):
        """Should not return duplicate completions."""
        sql = "SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        lower_completions = [c.lower() for c in completions]
        assert len(lower_completions) == len(set(lower_completions))

    def test_complete_with_cte(self, schema):
        """Should suggest CTE names as tables."""
        sql = "WITH active_users AS (SELECT * FROM users WHERE status = 'active') SELECT * FROM act"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "active_users" in completions


class TestSelectClauseSuggestions:
    """Tests for SELECT clause special suggestions (*, DISTINCT, TOP)."""

    @pytest.fixture
    def schema(self):
        """Sample database schema."""
        return {
            "tables": ["users", "orders"],
            "columns": {
                "users": ["id", "name", "email"],
                "orders": ["id", "user_id", "total"],
            },
        }

    def test_star_suggested_after_select(self, schema):
        """Should suggest * after SELECT."""
        sql = "SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"]
        )
        assert "*" in completions

    def test_distinct_suggested_after_select(self, schema):
        """Should suggest DISTINCT after SELECT."""
        sql = "SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"]
        )
        assert "DISTINCT" in completions

    def test_top_suggested_after_select(self, schema):
        """Should suggest TOP after SELECT (SQL Server syntax)."""
        sql = "SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"]
        )
        assert "TOP" in completions

    def test_star_filtered_by_prefix(self, schema):
        """Should filter * when typing."""
        sql = "SELECT *"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"]
        )
        # When typing *, it should match
        assert "*" in completions or len(completions) == 0  # Either matches or nothing

    def test_distinct_filtered_by_prefix(self, schema):
        """Should filter DISTINCT when typing D."""
        sql = "SELECT D"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"]
        )
        assert "DISTINCT" in completions

    def test_top_filtered_by_prefix(self, schema):
        """Should filter TOP when typing T."""
        sql = "SELECT T"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"]
        )
        assert "TOP" in completions


class TestOperatorSuggestions:
    """Tests for operator suggestions using sqlparse."""

    def test_operator_after_column_in_where(self):
        """Should suggest operators after column name in WHERE clause."""
        sql = "SELECT * FROM users WHERE id "
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id", "name"]})
        assert "=" in completions
        assert "!=" in completions
        assert "IS NULL" in completions
        assert "LIKE" in completions

    def test_operator_after_column_in_having(self):
        """Should suggest operators after column name in HAVING clause."""
        sql = "SELECT COUNT(*) FROM users GROUP BY status HAVING COUNT(*) "
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id", "status"]})
        assert ">" in completions
        assert ">=" in completions
        assert "<" in completions

    def test_operator_after_aliased_column(self):
        """Should suggest operators after aliased column in WHERE."""
        sql = "SELECT * FROM users u WHERE u.id "
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id", "name"]})
        assert "=" in completions
        assert "IN" in completions
        assert "BETWEEN" in completions

    def test_column_after_operator(self):
        """Should suggest columns after comparison operator."""
        sql = "SELECT * FROM users WHERE id = "
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id", "name"]})
        assert "id" in completions

    def test_no_operators_after_from(self):
        """Should NOT suggest operators after FROM keyword."""
        sql = "SELECT * FROM "
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id"]})
        assert "=" not in completions
        assert "users" in completions

    def test_no_operators_in_select(self):
        """Should NOT suggest operators in SELECT clause."""
        sql = "SELECT "
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id", "name"]})
        assert "=" not in completions

    def test_operators_filtered_by_prefix(self):
        """Should filter operators by typed prefix."""
        sql = "SELECT * FROM users WHERE id I"
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id"]})
        assert "IN" in completions or "IS NULL" in completions or "ILIKE" in completions

    def test_operator_on_join_condition(self):
        """Should suggest operators after column in ON clause."""
        sql = "SELECT * FROM users u JOIN orders o ON u.id "
        completions = get_completions(sql, len(sql), ["users", "orders"], {"users": ["id"], "orders": ["user_id"]})
        assert "=" in completions
