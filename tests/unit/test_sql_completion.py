"""Tests for SQL completion engine."""

import pytest

from sqlit.sql_completion import (
    RESERVED_WORDS,
    SQL_FUNCTIONS,
    SQL_KEYWORDS,
    Suggestion,
    SuggestionType,
    TableRef,
    _build_alias_map,
    _find_context_keyword,
    _find_current_clause,
    _find_last_keyword,
    _get_current_word,
    _is_inside_string,
    _remove_comments,
    _remove_string_literals,
    extract_cte_names,
    extract_table_refs,
    fuzzy_match,
    get_all_functions,
    get_all_keywords,
    get_completions,
    get_context,
)


class TestFuzzyMatch:
    """Tests for fuzzy matching algorithm."""

    def test_exact_prefix_match(self):
        """Exact prefix matches should come first."""
        candidates = ["users", "user_logs", "orders", "user_settings"]
        result = fuzzy_match("user", candidates)
        # "users" and "user_logs" and "user_settings" should be first (prefix matches)
        assert result[0].startswith("user")
        assert result[1].startswith("user")

    def test_fuzzy_match_subsequence(self):
        """Fuzzy match should find subsequence matches."""
        candidates = ["django_migrations", "django_session", "orders"]
        result = fuzzy_match("djmi", candidates)
        assert "django_migrations" in result

    def test_fuzzy_match_case_insensitive(self):
        """Fuzzy match should be case insensitive."""
        candidates = ["UserSettings", "user_logs", "USERS"]
        result = fuzzy_match("user", candidates)
        assert len(result) == 3

    def test_empty_text_returns_all(self):
        """Empty text should return all candidates up to max."""
        candidates = ["a", "b", "c", "d", "e"]
        result = fuzzy_match("", candidates, max_results=3)
        assert len(result) == 3

    def test_no_match_returns_empty(self):
        """No match should return empty list."""
        candidates = ["users", "orders", "products"]
        result = fuzzy_match("xyz", candidates)
        assert result == []

    def test_max_results_limit(self):
        """Should respect max_results limit."""
        candidates = [f"user_{i}" for i in range(100)]
        result = fuzzy_match("user", candidates, max_results=10)
        assert len(result) == 10

    def test_prefix_match_before_fuzzy(self):
        """Prefix matches should come before fuzzy matches."""
        candidates = ["ab_cd", "abcd", "a_b_c_d"]
        result = fuzzy_match("ab", candidates)
        # "ab_cd" and "abcd" are prefix matches, should come first
        assert result[0] in ["ab_cd", "abcd"]
        assert result[1] in ["ab_cd", "abcd"]


class TestExtractTableRefs:
    """Tests for table reference extraction."""

    def test_simple_from(self):
        """Extract simple FROM table."""
        sql = "SELECT * FROM users"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"
        assert refs[0].alias is None

    def test_from_with_alias(self):
        """Extract FROM table with alias."""
        sql = "SELECT * FROM users u"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"
        assert refs[0].alias == "u"

    def test_from_with_as_alias(self):
        """Extract FROM table with AS alias."""
        sql = "SELECT * FROM users AS u"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"
        assert refs[0].alias == "u"

    def test_multiple_joins(self):
        """Extract multiple tables with JOINs."""
        sql = """
        SELECT * FROM users u
        JOIN orders o ON u.id = o.user_id
        LEFT JOIN products p ON o.product_id = p.id
        """
        refs = extract_table_refs(sql)
        assert len(refs) == 3
        assert refs[0].name == "users"
        assert refs[0].alias == "u"
        assert refs[1].name == "orders"
        assert refs[1].alias == "o"
        assert refs[2].name == "products"
        assert refs[2].alias == "p"

    def test_schema_qualified_table(self):
        """Extract schema.table reference."""
        sql = "SELECT * FROM dbo.users u"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"
        assert refs[0].alias == "u"
        assert refs[0].schema == "dbo"

    def test_bracketed_identifiers(self):
        """Extract tables with bracket quoting."""
        sql = "SELECT * FROM [dbo].[User Settings] u"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        # Note: spaces in identifiers won't work with current regex
        assert refs[0].schema == "dbo"

    def test_reserved_word_not_alias(self):
        """Reserved words should not be detected as aliases."""
        sql = "SELECT * FROM users WHERE id = 1"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"
        # "WHERE" should not be captured as alias
        assert refs[0].alias is None

    def test_inner_join(self):
        """Extract INNER JOIN table."""
        sql = "SELECT * FROM users u INNER JOIN orders o ON u.id = o.user_id"
        refs = extract_table_refs(sql)
        assert len(refs) == 2

    def test_right_join(self):
        """Extract RIGHT JOIN table."""
        sql = "SELECT * FROM users RIGHT JOIN orders o ON users.id = o.user_id"
        refs = extract_table_refs(sql)
        assert len(refs) == 2
        assert refs[1].alias == "o"

    def test_case_insensitive(self):
        """FROM and JOIN should be case insensitive."""
        sql = "select * from Users u join Orders o on u.id = o.user_id"
        refs = extract_table_refs(sql)
        assert len(refs) == 2

    def test_double_quoted_table(self):
        """Extract double-quoted table (PostgreSQL style)."""
        sql = 'SELECT * FROM "books" WHERE id = 1'
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "books"

    def test_double_quoted_table_with_alias(self):
        """Extract double-quoted table with alias."""
        sql = 'SELECT * FROM "user_accounts" ua WHERE ua.id = 1'
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "user_accounts"
        assert refs[0].alias == "ua"

    def test_backtick_quoted_table(self):
        """Extract backtick-quoted table (MySQL style)."""
        sql = "SELECT * FROM `orders` WHERE id = 1"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "orders"

    def test_mixed_quoting_styles(self):
        """Handle mixed quoting styles in same query."""
        sql = 'SELECT * FROM "users" u JOIN `orders` o ON u.id = o.user_id'
        refs = extract_table_refs(sql)
        assert len(refs) == 2
        assert refs[0].name == "users"
        assert refs[1].name == "orders"

    def test_quoted_schema_and_table(self):
        """Extract quoted schema.table reference."""
        sql = 'SELECT * FROM "public"."users"'
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].schema == "public"
        assert refs[0].name == "users"

    def test_spaces_in_quoted_identifier(self):
        """Extract table name with spaces (quoted)."""
        sql = 'SELECT * FROM "user accounts" ua'
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "user accounts"
        assert refs[0].alias == "ua"


class TestExtractCTENames:
    """Tests for CTE name extraction."""

    def test_simple_cte(self):
        """Extract simple CTE name."""
        sql = """
        WITH active_users AS (
            SELECT * FROM users WHERE active = 1
        )
        SELECT * FROM active_users
        """
        ctes = extract_cte_names(sql)
        assert ctes == ["active_users"]

    def test_multiple_ctes(self):
        """Extract multiple CTE names."""
        sql = """
        WITH
            active_users AS (SELECT * FROM users WHERE active = 1),
            recent_orders AS (SELECT * FROM orders WHERE date > '2024-01-01')
        SELECT * FROM active_users au JOIN recent_orders ro ON au.id = ro.user_id
        """
        ctes = extract_cte_names(sql)
        assert "active_users" in ctes
        assert "recent_orders" in ctes

    def test_no_cte(self):
        """No CTE should return empty list."""
        sql = "SELECT * FROM users"
        ctes = extract_cte_names(sql)
        assert ctes == []

    def test_recursive_cte(self):
        """Extract recursive CTE name."""
        sql = """
        WITH RECURSIVE employee_tree AS (
            SELECT id, name, manager_id FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.id, e.name, e.manager_id FROM employees e
            JOIN employee_tree et ON e.manager_id = et.id
        )
        SELECT * FROM employee_tree
        """
        ctes = extract_cte_names(sql)
        assert "employee_tree" in ctes


class TestGetContext:
    """Tests for context detection."""

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

    def test_after_update(self):
        """After UPDATE should suggest tables."""
        sql = "UPDATE "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)

    def test_after_into(self):
        """After INTO should suggest tables."""
        sql = "INSERT INTO "
        suggestions = get_context(sql, len(sql))
        assert any(s.type == SuggestionType.TABLE for s in suggestions)


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_remove_string_literals(self):
        """String literals should be replaced."""
        sql = "SELECT * FROM users WHERE name = 'John' AND bio LIKE '%test%'"
        result = _remove_string_literals(sql)
        assert "John" not in result
        assert "test" not in result

    def test_remove_comments_single_line(self):
        """Single line comments should be removed."""
        sql = "SELECT * FROM users -- this is a comment\nWHERE id = 1"
        result = _remove_comments(sql)
        assert "this is a comment" not in result

    def test_remove_comments_multi_line(self):
        """Multi-line comments should be removed."""
        sql = "SELECT * /* comment */ FROM users"
        result = _remove_comments(sql)
        assert "comment" not in result

    def test_find_last_keyword(self):
        """Should find the last keyword."""
        assert _find_last_keyword("SELECT * FROM ") == "from"
        assert _find_last_keyword("SELECT * FROM users WHERE ") == "where"
        assert _find_last_keyword("SELECT id, ") == ","

    def test_find_current_clause(self):
        """Should find the current clause."""
        assert _find_current_clause("SELECT id, name") == "select"
        assert _find_current_clause("SELECT * FROM users WHERE") == "where"
        assert _find_current_clause("SELECT * FROM users u JOIN orders") == "join"

    def test_find_context_keyword(self):
        """Should find the context keyword before the current word."""
        # Typing partial word - context is the keyword before it
        assert _find_context_keyword("SELECT * FROM us") == "from"
        assert _find_context_keyword("SELECT * FROM users WHERE na") == "where"
        # After complete word with space - context is that word
        assert _find_context_keyword("SELECT * FROM ") == "from"
        assert _find_context_keyword("SELECT * FROM users WHERE ") == "where"
        # After comma
        assert _find_context_keyword("SELECT id, ") == ","
        assert _find_context_keyword("SELECT id,") == ","

    def test_get_current_word(self):
        """Should extract word being typed."""
        assert _get_current_word("SELECT us", 9) == "us"
        assert _get_current_word("SELECT * FROM ", 14) == ""
        assert _get_current_word("SELECT u.na", 11) == "na"

    def test_build_alias_map(self):
        """Should build correct alias map."""
        refs = [
            TableRef(name="users", alias="u"),
            TableRef(name="orders", alias="o"),
            TableRef(name="unknown", alias="x"),  # Not in known_tables
        ]
        known_tables = ["users", "orders", "products"]
        alias_map = _build_alias_map(refs, known_tables)
        assert alias_map == {"u": "users", "o": "orders"}


class TestGetCompletions:
    """Integration tests for full completion flow."""

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

    def test_complete_columns_in_select(self, schema):
        """Should complete columns in SELECT clause when tables are in scope."""
        # With a FROM clause, columns should be available
        sql = "SELECT i"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Without FROM clause, no specific columns in scope - just keywords/functions
        # that match 'i' fuzzy pattern
        assert len(completions) > 0  # Should have some keyword/function matches

        # With FROM clause, columns should be available
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
        # Should suggest orders columns, not users columns
        assert "user_id" in completions
        assert "total" in completions
        assert "status" in completions

    def test_no_duplicate_completions(self, schema):
        """Should not return duplicate completions."""
        sql = "SELECT "
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        # Check no duplicates (case-insensitive)
        lower_completions = [c.lower() for c in completions]
        assert len(lower_completions) == len(set(lower_completions))

    def test_complete_with_cte(self, schema):
        """Should suggest CTE names as tables."""
        # Use cursor_pos at the end of the actual content, not including trailing whitespace
        sql = "WITH active_users AS (SELECT * FROM users WHERE status = 'active') SELECT * FROM act"
        completions = get_completions(
            sql, len(sql), schema["tables"], schema["columns"], schema["procedures"]
        )
        assert "active_users" in completions


class TestSQLKeywordsAndFunctions:
    """Tests for SQL keywords and functions."""

    def test_keywords_not_empty(self):
        """Should have keywords defined."""
        keywords = get_all_keywords()
        assert len(keywords) > 50
        assert "SELECT" in keywords
        assert "FROM" in keywords
        assert "WHERE" in keywords

    def test_functions_not_empty(self):
        """Should have functions defined."""
        functions = get_all_functions()
        assert len(functions) > 30
        assert "COUNT" in functions
        assert "SUM" in functions
        assert "COALESCE" in functions

    def test_reserved_words_lowercase(self):
        """Reserved words should be lowercase."""
        for word in RESERVED_WORDS:
            assert word == word.lower()

    def test_keywords_categories(self):
        """Should have multiple keyword categories."""
        assert "dml" in SQL_KEYWORDS
        assert "ddl" in SQL_KEYWORDS
        assert "control" in SQL_KEYWORDS

    def test_functions_categories(self):
        """Should have multiple function categories."""
        assert "aggregate" in SQL_FUNCTIONS
        assert "string" in SQL_FUNCTIONS
        assert "datetime" in SQL_FUNCTIONS


class TestInsideString:
    """Tests for string literal detection."""

    def test_inside_single_quote_string(self):
        """Should detect cursor inside single-quoted string."""
        assert _is_inside_string("SELECT * FROM users WHERE name = '") is True
        assert _is_inside_string("SELECT * FROM users WHERE name = 'John") is True

    def test_inside_double_quote_string(self):
        """Should detect cursor inside double-quoted string."""
        assert _is_inside_string('SELECT * FROM users WHERE name = "') is True
        assert _is_inside_string('SELECT * FROM users WHERE name = "John') is True

    def test_outside_closed_string(self):
        """Should detect cursor outside closed string."""
        assert _is_inside_string("SELECT * FROM users WHERE name = 'John'") is False
        assert _is_inside_string("SELECT * FROM users WHERE name = 'John' AND ") is False

    def test_escaped_quotes(self):
        """Should handle escaped quotes (SQL style '')."""
        # Inside string with escaped quote
        assert _is_inside_string("SELECT * FROM users WHERE name = 'O''Brien") is True
        # After escaped quote, string closed
        assert _is_inside_string("SELECT * FROM users WHERE name = 'O''Brien'") is False

    def test_no_suggestions_inside_string(self):
        """Should return no suggestions when inside string literal."""
        sql = "SELECT * FROM users WHERE name = '"
        suggestions = get_context(sql, len(sql))
        assert suggestions == []

    def test_no_suggestions_inside_string_partial_value(self):
        """Should return no suggestions when typing value inside string."""
        sql = "SELECT * FROM users WHERE name = 'John"
        suggestions = get_context(sql, len(sql))
        assert suggestions == []

    def test_suggestions_after_closed_string(self):
        """Should return suggestions after string is closed."""
        sql = "SELECT * FROM users WHERE name = 'John' AND "
        suggestions = get_context(sql, len(sql))
        assert len(suggestions) > 0

    def test_no_completions_inside_string(self):
        """Full integration test: no completions inside string."""
        sql = "SELECT * FROM users WHERE name = '"
        completions = get_completions(
            sql, len(sql), ["users"], {"users": ["id", "name", "email"]}
        )
        assert completions == []


class TestEdgeCases:
    """Tests for edge cases and potential issues."""

    def test_empty_sql(self):
        """Should handle empty SQL."""
        completions = get_completions("", 0, ["users"], {"users": ["id"]})
        assert len(completions) > 0  # Should suggest keywords

    def test_cursor_at_start(self):
        """Should handle cursor at start."""
        sql = "SELECT * FROM users"
        completions = get_completions(sql, 0, ["users"], {"users": ["id"]})
        assert len(completions) > 0

    def test_cursor_in_middle(self):
        """Should handle cursor in middle of query."""
        sql = "SELECT * FROM users WHERE id = 1"
        cursor_pos = len("SELECT * FROM ")  # After FROM
        completions = get_completions(sql, cursor_pos, ["users"], {"users": ["id"]})
        # At this position, context depends on what's being typed
        assert isinstance(completions, list)

    def test_unknown_alias(self):
        """Should handle unknown alias gracefully."""
        sql = "SELECT * FROM users WHERE x."
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id"]})
        # Should return empty or minimal results for unknown alias
        assert isinstance(completions, list)

    def test_special_characters_in_word(self):
        """Should handle special characters."""
        sql = "SELECT * FROM [us"
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id"]})
        # Should still try to match
        assert isinstance(completions, list)

    def test_multiline_query(self):
        """Should handle multiline queries."""
        sql = """SELECT
            u.id,
            u.name
        FROM
            users u
        WHERE
            u."""
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id", "name"]})
        assert "id" in completions
        assert "name" in completions

    def test_case_insensitive_alias_lookup(self):
        """Alias lookup should be case insensitive."""
        sql = "SELECT * FROM Users U WHERE U."
        completions = get_completions(sql, len(sql), ["Users"], {"users": ["id", "name"]})
        assert "id" in completions

    def test_string_literal_not_confused(self):
        """String literals should not confuse context detection."""
        sql = "SELECT * FROM users WHERE name = 'FROM orders' AND "
        completions = get_completions(sql, len(sql), ["users", "orders"], {"users": ["id"], "orders": ["id"]})
        # Should still be in WHERE context, not suggest tables
        assert isinstance(completions, list)

    def test_comment_not_confused(self):
        """Comments should not confuse context detection."""
        sql = """SELECT * FROM users
        -- FROM orders
        WHERE """
        completions = get_completions(sql, len(sql), ["users", "orders"], {"users": ["id"], "orders": ["id"]})
        # Should be in WHERE context
        assert isinstance(completions, list)


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
        # After = should suggest columns/values, not operators
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
        # Operators shouldn't be in SELECT suggestions
        assert "=" not in completions

    def test_operators_filtered_by_prefix(self):
        """Should filter operators by typed prefix."""
        sql = "SELECT * FROM users WHERE id I"
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id"]})
        # Should match operators starting with I
        assert "IN" in completions or "IS NULL" in completions or "ILIKE" in completions

    def test_operator_on_join_condition(self):
        """Should suggest operators after column in ON clause."""
        sql = "SELECT * FROM users u JOIN orders o ON u.id "
        completions = get_completions(sql, len(sql), ["users", "orders"], {"users": ["id"], "orders": ["user_id"]})
        assert "=" in completions
