"""Main SQL completion engine.

Orchestrates context detection and completion generation.
"""

from __future__ import annotations

import re

from .alter_table import get_alter_table_completions
from .core import (
    SQL_OPERATORS,
    Suggestion,
    SuggestionType,
    build_alias_map,
    extract_cte_names,
    extract_table_refs,
    find_context_keyword,
    find_current_clause,
    fuzzy_match,
    get_all_functions,
    get_all_keywords,
    get_current_word,
    get_last_token_info,
    is_inside_string,
    remove_comments,
    remove_string_literals,
)
from .create_index import get_create_index_completions
from .create_table import get_create_table_completions
from .create_view import get_create_view_completions
from .delete import extract_delete_table_refs, get_delete_context
from .drop import get_drop_completions
from .insert import get_insert_context
from .truncate import get_truncate_completions
from .update import get_update_context

# Special keywords for SELECT clause (before FROM)
SELECT_CLAUSE_KEYWORDS = ["*", "DISTINCT", "TOP", "ALL"]


def get_context(sql: str, cursor_pos: int) -> list[Suggestion]:
    """Determine what type of suggestions to provide based on cursor position.

    Uses statement-specific handlers and sqlparse for accurate context detection.

    Args:
        sql: The full SQL text
        cursor_pos: Position of cursor in the text

    Returns:
        List of Suggestion objects indicating what to suggest
    """
    before_cursor = sql[:cursor_pos]

    # Don't suggest anything if we're inside a string literal
    if is_inside_string(before_cursor):
        return []

    # Don't suggest anything after a statement terminator (semicolon)
    if before_cursor.rstrip().endswith(";"):
        return []

    # Check for table.column pattern (alias or table prefix)
    dot_match = re.search(r"(\w+)\.\w*$", before_cursor)
    if dot_match:
        prefix = dot_match.group(1)
        return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=prefix)]

    # Try statement-specific handlers
    for handler in [get_insert_context, get_update_context, get_delete_context]:
        result = handler(before_cursor)
        if result is not None:
            return result

    # Use sqlparse to detect operators - only when cursor is after whitespace
    if before_cursor and before_cursor[-1] in " \t\n":
        token_value, token_type = get_last_token_info(before_cursor.rstrip())

        if token_type:
            # After a comparison operator -> suggest columns/values
            if "Comparison" in token_type:
                return [Suggestion(type=SuggestionType.COLUMN)]

            # After a Name or ) in WHERE context -> suggest operators
            if token_type == "Token.Name" or (token_type == "Token.Punctuation" and token_value == ")"):
                clean_sql = remove_string_literals(before_cursor)
                clean_sql = remove_comments(clean_sql)
                clause = find_current_clause(clean_sql)
                if clause in ("where", "having", "on"):
                    return [Suggestion(type=SuggestionType.OPERATOR)]

    # Fall back to keyword-based context detection
    clean_sql = remove_string_literals(before_cursor)
    clean_sql = remove_comments(clean_sql)
    context_keyword = find_context_keyword(clean_sql)

    if context_keyword in ("from", "join", "inner", "left", "right", "outer", "cross", "full", "into", "update", "table"):
        return [Suggestion(type=SuggestionType.TABLE)]

    # DISTINCT should suggest columns (same as SELECT)
    if context_keyword == "distinct":
        return [Suggestion(type=SuggestionType.COLUMN)]

    # CASE/WHEN/THEN/ELSE expressions should suggest columns
    if context_keyword in ("when", "then", "else"):
        return [Suggestion(type=SuggestionType.COLUMN)]

    if context_keyword in ("select", "where", "and", "or", "on", "having", "set"):
        return [Suggestion(type=SuggestionType.COLUMN)]

    if context_keyword in ("order", "group"):
        if re.search(r"\b(ORDER|GROUP)\s+BY\s+\w*$", clean_sql, re.IGNORECASE):
            return [Suggestion(type=SuggestionType.COLUMN)]
        return [Suggestion(type=SuggestionType.KEYWORD)]

    if context_keyword in ("exec", "execute", "call"):
        return [Suggestion(type=SuggestionType.PROCEDURE)]

    if context_keyword == ",":
        clause = find_current_clause(clean_sql)
        if clause == "select":
            return [Suggestion(type=SuggestionType.COLUMN)]
        if clause in ("from", "join"):
            return [Suggestion(type=SuggestionType.TABLE)]
        if clause == "set":
            # After comma in SET clause, suggest columns
            return [Suggestion(type=SuggestionType.COLUMN)]
        return [Suggestion(type=SuggestionType.COLUMN)]

    if context_keyword in ("by",):
        return [Suggestion(type=SuggestionType.COLUMN)]

    # Default: suggest keywords
    return [Suggestion(type=SuggestionType.KEYWORD)]


def get_completions(
    sql: str,
    cursor_pos: int,
    tables: list[str],
    columns: dict[str, list[str]],
    procedures: list[str] | None = None,
    include_keywords: bool = True,
    include_functions: bool = True,
) -> list[str]:
    """Get completion suggestions for the given SQL and cursor position.

    Args:
        sql: The full SQL text
        cursor_pos: Position of cursor in the text
        tables: List of available table names
        columns: Dict mapping table names to column lists
        procedures: Optional list of stored procedure names
        include_keywords: Whether to include SQL keywords
        include_functions: Whether to include SQL functions

    Returns:
        List of completion suggestions
    """
    before_cursor = sql[:cursor_pos]
    current_word = get_current_word(sql, cursor_pos)

    # Don't suggest if inside string literal
    if is_inside_string(before_cursor):
        return []

    # Don't suggest if there's no SQL content yet (just whitespace)
    if not before_cursor.strip():
        return []

    # Try DDL-specific handlers first (they return completions directly)
    for ddl_handler in [
        get_create_table_completions,
        get_alter_table_completions,
        get_create_index_completions,
        get_create_view_completions,
    ]:
        result = ddl_handler(before_cursor, tables, columns)
        if result is not None:
            return fuzzy_match(current_word, result)

    # Try DROP handler (doesn't need columns)
    drop_result = get_drop_completions(before_cursor, tables, procedures)
    if drop_result is not None:
        return fuzzy_match(current_word, drop_result)

    # Try TRUNCATE handler (only needs tables)
    truncate_result = get_truncate_completions(before_cursor, tables)
    if truncate_result is not None:
        return fuzzy_match(current_word, truncate_result)

    # Handle specific patterns that need targeted suggestions
    clean_before = remove_string_literals(before_cursor)
    clean_before = remove_comments(clean_before)

    # After UNION/INTERSECT/EXCEPT [ALL] → suggest SELECT
    if re.search(r"\b(UNION|INTERSECT|EXCEPT)(\s+ALL)?\s+\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["SELECT", "ALL"])

    # After JOIN table_name [alias] → suggest ON keyword
    # But NOT for CROSS JOIN or NATURAL JOIN (they don't use ON)
    if re.search(r"\bJOIN\s+\w+(\s+(?:AS\s+)?\w+)?\s+\w*$", clean_before, re.IGNORECASE):
        if not re.search(r"\bJOIN\s+\w*$", clean_before, re.IGNORECASE):
            # Check if it's CROSS JOIN or NATURAL JOIN
            if re.search(r"\b(CROSS|NATURAL)\s+JOIN\b", clean_before, re.IGNORECASE):
                # CROSS/NATURAL JOIN don't use ON - suggest common follow-ups
                return fuzzy_match(current_word, ["WHERE", "ORDER", "GROUP", "LIMIT", "UNION"])
            else:
                return fuzzy_match(current_word, ["ON", "USING"])

    # CAST(col AS → suggest data types
    if re.search(r"\bCAST\s*\([^)]+\s+AS\s+\w*$", clean_before, re.IGNORECASE):
        from .create_table import SQL_DATA_TYPES
        return fuzzy_match(current_word, SQL_DATA_TYPES)

    # RETURNING clause → suggest columns from the target table
    # Works for INSERT, UPDATE, DELETE with RETURNING
    returning_match = re.search(r"\bRETURNING\s+(?:\w+\s*,\s*)*\w*$", clean_before, re.IGNORECASE)
    if returning_match:
        # Extract table from INSERT INTO, UPDATE, or DELETE FROM
        table_match = re.search(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)",
            clean_before,
            re.IGNORECASE,
        )
        if table_match:
            table_name = table_match.group(1).lower()
            if table_name in columns:
                return fuzzy_match(current_word, columns[table_name])

    # Inside function parens → suggest columns
    # Includes aggregates, string functions, date functions, etc.
    func_match = re.search(
        r"\b(COUNT|SUM|AVG|MAX|MIN|COALESCE|NULLIF|ISNULL|IFNULL|NVL|NVL2|"
        r"GROUP_CONCAT|STRING_AGG|ARRAY_AGG|CAST|"
        r"TRIM|LTRIM|RTRIM|UPPER|LOWER|LENGTH|LEN|SUBSTR|SUBSTRING|REPLACE|"
        r"CONCAT|LEFT|RIGHT|LPAD|RPAD|REVERSE|"
        r"ABS|ROUND|CEIL|CEILING|FLOOR|SIGN|SQRT|POWER|MOD|"
        r"DATE|YEAR|MONTH|DAY|HOUR|MINUTE|SECOND|"
        r"TO_CHAR|TO_DATE|TO_NUMBER|FORMAT)\s*\(\s*\w*$",
        clean_before,
        re.IGNORECASE,
    )
    if func_match:
        # Build column list from tables in the full SQL
        table_refs = extract_table_refs(sql)
        table_refs.extend(extract_delete_table_refs(sql))
        result_cols = []
        for ref in table_refs:
            table_key = ref.name.lower()
            if table_key in columns:
                result_cols.extend(columns[table_key])
        if result_cols:
            return fuzzy_match(current_word, result_cols)

    # Schema.table prefix → suggest tables after schema name
    # Pattern: FROM/JOIN schema. or schema.partial
    if re.search(r"\b(FROM|JOIN)\s+\w+\.\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, tables)

    # ANY/ALL/SOME ( → suggest SELECT for subquery
    if re.search(r"\b(ANY|ALL|SOME)\s*\(\s*\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["SELECT"])

    # IN ( or NOT IN ( → suggest SELECT for subquery
    if re.search(r"\bNOT\s+IN\s*\(\s*\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["SELECT"])
    if re.search(r"\bIN\s*\(\s*\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["SELECT"])

    # EXISTS ( or NOT EXISTS ( → suggest SELECT for subquery
    if re.search(r"\b(NOT\s+)?EXISTS\s*\(\s*\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["SELECT"])

    # GROUPING SETS/CUBE/ROLLUP ( → suggest columns
    if re.search(r"\b(GROUPING\s+SETS|CUBE|ROLLUP)\s*\(\s*\w*$", clean_before, re.IGNORECASE):
        table_refs = extract_table_refs(sql)
        result_cols = []
        for ref in table_refs:
            table_key = ref.name.lower()
            if table_key in columns:
                result_cols.extend(columns[table_key])
        if result_cols:
            return fuzzy_match(current_word, result_cols)

    # ORDER BY column → suggest ASC, DESC, NULLS
    # Pattern: ORDER BY col or ORDER BY col1, col2
    if re.search(r"\bORDER\s+BY\s+(?:\w+\s*,\s*)*\w+\s+\w*$", clean_before, re.IGNORECASE):
        # Make sure we're not right after ORDER BY (that should suggest columns)
        if not re.search(r"\bORDER\s+BY\s+\w*$", clean_before, re.IGNORECASE):
            # Check if we just typed ASC/DESC and need more options
            if re.search(r"\b(ASC|DESC)\s+\w*$", clean_before, re.IGNORECASE):
                return fuzzy_match(current_word, ["NULLS", ",", "LIMIT", "OFFSET", "FETCH"])
            return fuzzy_match(current_word, ["ASC", "DESC", "NULLS", ",", "LIMIT"])

    # NULLS → suggest FIRST, LAST
    if re.search(r"\bNULLS\s+\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["FIRST", "LAST"])

    # CASE [column] → suggest WHEN
    # Matches "CASE " or "CASE col " but not "CASE WHEN"
    if re.search(r"\bCASE\s+(?!WHEN\b)\w*\s*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["WHEN"])

    # OVER ( → suggest PARTITION BY, ORDER BY
    if re.search(r"\bOVER\s*\(\s*\w*$", clean_before, re.IGNORECASE):
        return fuzzy_match(current_word, ["PARTITION", "ORDER", "ROWS", "RANGE"])

    # Special-case: after SELECT * prefer FROM and hide redundant "*"
    prefer_from = False

    # Fall back to context-based completion
    suggestions = get_context(sql, cursor_pos)
    if not suggestions:
        return []

    # Build table alias map from all sources
    table_refs = extract_table_refs(sql)
    table_refs.extend(extract_delete_table_refs(sql))
    alias_map = build_alias_map(table_refs, tables)

    cte_names = extract_cte_names(sql)

    results: list[str] = []

    for suggestion in suggestions:
        if suggestion.type == SuggestionType.TABLE:
            results.extend(tables)
            results.extend(cte_names)

        elif suggestion.type == SuggestionType.COLUMN:
            # Check if we're in SELECT clause (before FROM) to add special keywords
            clause = find_current_clause(clean_before)
            if not prefer_from and clause == "select":
                if re.search(r"\bSELECT\s+\*\s+\w*$", clean_before, re.IGNORECASE) or re.search(
                    r"\bSELECT\s+\*\s*$", clean_before, re.IGNORECASE
                ):
                    if not current_word or "from".startswith(current_word.lower()):
                        prefer_from = True
            if clause == "select":
                results.extend(SELECT_CLAUSE_KEYWORDS)

            for ref in table_refs:
                table_key = ref.name.lower()
                if table_key in columns:
                    results.extend(columns[table_key])

            # Only add table names if NOT in SELECT clause (tables go after FROM, not SELECT)
            if clause != "select":
                results.extend(tables)

            if include_functions:
                results.extend(get_all_functions())

        elif suggestion.type == SuggestionType.ALIAS_COLUMN:
            scope = suggestion.table_scope
            if scope:
                scope_lower = scope.lower()

                if scope_lower in alias_map:
                    table_name = alias_map[scope_lower]
                    if table_name.lower() in columns:
                        results.extend(columns[table_name.lower()])
                elif scope_lower in columns:
                    results.extend(columns[scope_lower])

        elif suggestion.type == SuggestionType.PROCEDURE:
            if procedures:
                results.extend(procedures)

        elif suggestion.type == SuggestionType.KEYWORD:
            if include_keywords:
                results.extend(get_all_keywords())
            if include_functions:
                results.extend(get_all_functions())

        elif suggestion.type == SuggestionType.OPERATOR:
            results.extend(SQL_OPERATORS)

    # Remove duplicates while preserving order
    seen: set[str] = set()
    unique_results: list[str] = []
    for r in results:
        if r.lower() not in seen:
            seen.add(r.lower())
            unique_results.append(r)

    if prefer_from:
        unique_results = [r for r in unique_results if r != "*"]
        if "FROM" not in unique_results:
            unique_results.insert(0, "FROM")

    return fuzzy_match(current_word, unique_results)
