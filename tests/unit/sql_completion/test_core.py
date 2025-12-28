"""Tests for core SQL completion utilities."""

import pytest

from sqlit.sql_completion import (
    RESERVED_WORDS,
    SQL_FUNCTIONS,
    SQL_KEYWORDS,
    TableRef,
    build_alias_map,
    extract_cte_names,
    extract_table_refs,
    find_context_keyword,
    find_current_clause,
    find_last_keyword,
    fuzzy_match,
    get_all_functions,
    get_all_keywords,
    get_completions,
    get_current_word,
    is_inside_string,
    remove_comments,
    remove_string_literals,
)


class TestFuzzyMatch:
    """Tests for fuzzy matching algorithm."""

    def test_exact_prefix_match(self):
        """Exact prefix matches should come first."""
        candidates = ["users", "user_logs", "orders", "user_settings"]
        result = fuzzy_match("user", candidates)
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
        assert refs[0].schema == "dbo"

    def test_reserved_word_not_alias(self):
        """Reserved words should not be detected as aliases."""
        sql = "SELECT * FROM users WHERE id = 1"
        refs = extract_table_refs(sql)
        assert len(refs) == 1
        assert refs[0].name == "users"
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


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_remove_string_literals(self):
        """String literals should be replaced."""
        sql = "SELECT * FROM users WHERE name = 'John' AND bio LIKE '%test%'"
        result = remove_string_literals(sql)
        assert "John" not in result
        assert "test" not in result

    def test_remove_comments_single_line(self):
        """Single line comments should be removed."""
        sql = "SELECT * FROM users -- this is a comment\nWHERE id = 1"
        result = remove_comments(sql)
        assert "this is a comment" not in result

    def test_remove_comments_multi_line(self):
        """Multi-line comments should be removed."""
        sql = "SELECT * /* comment */ FROM users"
        result = remove_comments(sql)
        assert "comment" not in result

    def test_find_last_keyword(self):
        """Should find the last keyword."""
        assert find_last_keyword("SELECT * FROM ") == "from"
        assert find_last_keyword("SELECT * FROM users WHERE ") == "where"
        assert find_last_keyword("SELECT id, ") == ","

    def test_find_current_clause(self):
        """Should find the current clause."""
        assert find_current_clause("SELECT id, name") == "select"
        assert find_current_clause("SELECT * FROM users WHERE") == "where"
        assert find_current_clause("SELECT * FROM users u JOIN orders") == "join"

    def test_find_context_keyword(self):
        """Should find the context keyword before the current word."""
        assert find_context_keyword("SELECT * FROM us") == "from"
        assert find_context_keyword("SELECT * FROM users WHERE na") == "where"
        assert find_context_keyword("SELECT * FROM ") == "from"
        assert find_context_keyword("SELECT * FROM users WHERE ") == "where"
        assert find_context_keyword("SELECT id, ") == ","
        assert find_context_keyword("SELECT id,") == ","

    def test_get_current_word(self):
        """Should extract word being typed."""
        assert get_current_word("SELECT us", 9) == "us"
        assert get_current_word("SELECT * FROM ", 14) == ""
        assert get_current_word("SELECT u.na", 11) == "na"

    def test_build_alias_map(self):
        """Should build correct alias map."""
        refs = [
            TableRef(name="users", alias="u"),
            TableRef(name="orders", alias="o"),
            TableRef(name="unknown", alias="x"),
        ]
        known_tables = ["users", "orders", "products"]
        alias_map = build_alias_map(refs, known_tables)
        assert alias_map == {"u": "users", "o": "orders"}


class TestInsideString:
    """Tests for string literal detection."""

    def test_inside_single_quote_string(self):
        """Should detect cursor inside single-quoted string."""
        assert is_inside_string("SELECT * FROM users WHERE name = '") is True
        assert is_inside_string("SELECT * FROM users WHERE name = 'John") is True

    def test_inside_double_quote_string(self):
        """Should detect cursor inside double-quoted string."""
        assert is_inside_string('SELECT * FROM users WHERE name = "') is True
        assert is_inside_string('SELECT * FROM users WHERE name = "John') is True

    def test_outside_closed_string(self):
        """Should detect cursor outside closed string."""
        assert is_inside_string("SELECT * FROM users WHERE name = 'John'") is False
        assert is_inside_string("SELECT * FROM users WHERE name = 'John' AND ") is False

    def test_escaped_quotes(self):
        """Should handle escaped quotes (SQL style '')."""
        assert is_inside_string("SELECT * FROM users WHERE name = 'O''Brien") is True
        assert is_inside_string("SELECT * FROM users WHERE name = 'O''Brien'") is False


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


class TestEdgeCases:
    """Tests for edge cases and potential issues."""

    def test_empty_sql(self):
        """Should return nothing for empty SQL (no context yet)."""
        completions = get_completions("", 0, ["users"], {"users": ["id"]})
        assert len(completions) == 0

    def test_cursor_at_start(self):
        """Should return nothing when cursor is at start (no context yet)."""
        sql = "SELECT * FROM users"
        completions = get_completions(sql, 0, ["users"], {"users": ["id"]})
        assert len(completions) == 0

    def test_cursor_in_middle(self):
        """Should handle cursor in middle of query."""
        sql = "SELECT * FROM users WHERE id = 1"
        cursor_pos = len("SELECT * FROM ")
        completions = get_completions(sql, cursor_pos, ["users"], {"users": ["id"]})
        assert isinstance(completions, list)

    def test_unknown_alias(self):
        """Should handle unknown alias gracefully."""
        sql = "SELECT * FROM users WHERE x."
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id"]})
        assert isinstance(completions, list)

    def test_special_characters_in_word(self):
        """Should handle special characters."""
        sql = "SELECT * FROM [us"
        completions = get_completions(sql, len(sql), ["users"], {"users": ["id"]})
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
        assert isinstance(completions, list)

    def test_comment_not_confused(self):
        """Comments should not confuse context detection."""
        sql = """SELECT * FROM users
        -- FROM orders
        WHERE """
        completions = get_completions(sql, len(sql), ["users", "orders"], {"users": ["id"], "orders": ["id"]})
        assert isinstance(completions, list)
