"""SQL completion engine using sqlparse for context detection.

This module provides intelligent SQL autocompletion with:
- Context-aware suggestions (tables after FROM, columns after SELECT, etc.)
- Alias recognition (FROM users u -> u.id suggests users columns)
- Fuzzy matching
- SQL keywords and common functions
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import NamedTuple


class SuggestionType(Enum):
    """Types of SQL completion suggestions."""

    TABLE = auto()
    COLUMN = auto()
    KEYWORD = auto()
    FUNCTION = auto()
    SCHEMA = auto()
    DATABASE = auto()
    PROCEDURE = auto()
    ALIAS_COLUMN = auto()  # Column for a specific table/alias
    OPERATOR = auto()  # Comparison operators (=, <, >, etc.)


class Suggestion(NamedTuple):
    """A completion suggestion with type and optional scope."""

    type: SuggestionType
    table_scope: str | None = None  # For ALIAS_COLUMN, which table


@dataclass
class TableRef:
    """A table reference with optional alias."""

    name: str
    alias: str | None = None
    schema: str | None = None


# SQL Comparison operators and condition keywords
SQL_OPERATORS = [
    "=",
    "!=",
    "<>",
    "<",
    ">",
    "<=",
    ">=",
    "IS NULL",
    "IS NOT NULL",
    "IN",
    "NOT IN",
    "LIKE",
    "NOT LIKE",
    "ILIKE",
    "NOT ILIKE",
    "BETWEEN",
    "NOT BETWEEN",
    "EXISTS",
    "NOT EXISTS",
]

# SQL Keywords grouped by category
SQL_KEYWORDS = {
    "dml": [
        "SELECT",
        "FROM",
        "WHERE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "CROSS",
        "FULL",
        "ON",
        "AND",
        "OR",
        "NOT",
        "IN",
        "EXISTS",
        "BETWEEN",
        "LIKE",
        "IS",
        "NULL",
        "ORDER",
        "BY",
        "ASC",
        "DESC",
        "GROUP",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "TOP",
        "DISTINCT",
        "AS",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "ALL",
        "INSERT",
        "INTO",
        "VALUES",
        "UPDATE",
        "SET",
        "DELETE",
        "MERGE",
        "USING",
        "MATCHED",
    ],
    "ddl": [
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "INDEX",
        "VIEW",
        "TABLE",
        "DATABASE",
        "SCHEMA",
        "CONSTRAINT",
        "PRIMARY",
        "KEY",
        "FOREIGN",
        "REFERENCES",
        "UNIQUE",
        "CHECK",
        "DEFAULT",
    ],
    "control": [
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "IF",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "TRANSACTION",
    ],
    "types": [
        "INT",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "DECIMAL",
        "NUMERIC",
        "FLOAT",
        "REAL",
        "DOUBLE",
        "VARCHAR",
        "CHAR",
        "TEXT",
        "NVARCHAR",
        "NCHAR",
        "DATE",
        "TIME",
        "DATETIME",
        "TIMESTAMP",
        "BOOLEAN",
        "BIT",
        "BLOB",
        "CLOB",
        "UUID",
        "JSON",
        "XML",
    ],
}

# Common SQL functions
SQL_FUNCTIONS = {
    "aggregate": [
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "GROUP_CONCAT",
        "STRING_AGG",
        "ARRAY_AGG",
        "LISTAGG",
    ],
    "string": [
        "CONCAT",
        "SUBSTRING",
        "SUBSTR",
        "LEFT",
        "RIGHT",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "UPPER",
        "LOWER",
        "LENGTH",
        "LEN",
        "CHARINDEX",
        "POSITION",
        "REPLACE",
        "REVERSE",
        "SPLIT_PART",
        "STUFF",
    ],
    "numeric": [
        "ABS",
        "ROUND",
        "FLOOR",
        "CEILING",
        "CEIL",
        "POWER",
        "SQRT",
        "MOD",
        "SIGN",
        "RAND",
        "RANDOM",
    ],
    "datetime": [
        "NOW",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "GETDATE",
        "GETUTCDATE",
        "SYSDATETIME",
        "DATEADD",
        "DATEDIFF",
        "DATEPART",
        "YEAR",
        "MONTH",
        "DAY",
        "HOUR",
        "MINUTE",
        "SECOND",
        "EXTRACT",
        "DATE_TRUNC",
        "TO_DATE",
        "TO_CHAR",
        "FORMAT",
    ],
    "conversion": [
        "CAST",
        "CONVERT",
        "TRY_CAST",
        "TRY_CONVERT",
        "PARSE",
        "TRY_PARSE",
    ],
    "null_handling": [
        "COALESCE",
        "NULLIF",
        "ISNULL",
        "IFNULL",
        "NVL",
        "NVL2",
    ],
    "conditional": [
        "IIF",
        "CHOOSE",
        "DECODE",
    ],
    "window": [
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "NTILE",
        "LAG",
        "LEAD",
        "FIRST_VALUE",
        "LAST_VALUE",
        "OVER",
        "PARTITION",
    ],
}

# Reserved words that cannot be aliases
RESERVED_WORDS = {
    "select",
    "from",
    "where",
    "join",
    "inner",
    "outer",
    "left",
    "right",
    "cross",
    "full",
    "on",
    "and",
    "or",
    "not",
    "in",
    "as",
    "order",
    "by",
    "group",
    "having",
    "union",
    "intersect",
    "except",
    "limit",
    "offset",
    "insert",
    "into",
    "values",
    "update",
    "set",
    "delete",
    "create",
    "alter",
    "drop",
    "table",
    "index",
    "view",
    "case",
    "when",
    "then",
    "else",
    "end",
    "null",
    "is",
    "like",
    "between",
    "exists",
    "distinct",
    "all",
    "top",
    "with",
    "asc",
    "desc",
    "natural",
    "using",
}


def get_all_keywords() -> list[str]:
    """Get all SQL keywords as a flat list."""
    keywords = []
    for category in SQL_KEYWORDS.values():
        keywords.extend(category)
    return list(set(keywords))


def get_all_functions() -> list[str]:
    """Get all SQL functions as a flat list."""
    functions = []
    for category in SQL_FUNCTIONS.values():
        functions.extend(category)
    return list(set(functions))


def fuzzy_match(text: str, candidates: list[str], max_results: int = 50) -> list[str]:
    """Fuzzy match text against candidates.

    Matches if all characters in text appear in candidate in order.
    E.g., 'djmi' matches 'django_migrations'

    Args:
        text: The text to match
        candidates: List of candidate strings
        max_results: Maximum number of results to return

    Returns:
        List of matching candidates, sorted by match quality
    """
    if not text:
        return candidates[:max_results]

    text_lower = text.lower()
    results: list[tuple[int, int, str]] = []

    for candidate in candidates:
        c_lower = candidate.lower()

        # First check prefix match (higher priority)
        if c_lower.startswith(text_lower):
            # Score: 0 for exact prefix, length for sorting
            results.append((0, len(candidate), candidate))
            continue

        # Fuzzy match: all chars must appear in order
        idx = 0
        matched = True
        first_match_pos = -1

        for char in text_lower:
            idx = c_lower.find(char, idx)
            if idx == -1:
                matched = False
                break
            if first_match_pos == -1:
                first_match_pos = idx
            idx += 1

        if matched:
            # Score: 1 for fuzzy, then by first match position, then length
            results.append((1, first_match_pos * 100 + len(candidate), candidate))

    # Sort by score tuple and return candidates
    results.sort(key=lambda x: (x[0], x[1]))
    return [r[2] for r in results[:max_results]]


def extract_table_refs(sql: str) -> list[TableRef]:
    """Extract table references and aliases from SQL.

    Handles patterns like:
    - FROM users
    - FROM users u
    - FROM users AS u
    - JOIN orders o ON ...
    - FROM schema.users u
    - FROM "quoted_table" (PostgreSQL)
    - FROM [bracketed_table] (SQL Server)
    - FROM `backtick_table` (MySQL)

    Args:
        sql: The SQL text to parse

    Returns:
        List of TableRef objects with name, alias, and optional schema
    """
    refs: list[TableRef] = []

    # Pattern to match quoted identifiers: "name", [name], `name`, or unquoted name
    # (?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\w+)) captures the identifier
    ident = r'(?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\w+))'

    # Full pattern:
    # (?:FROM|JOIN)\s+  - FROM or JOIN keyword
    # optional schema.  - schema identifier followed by dot
    # table identifier  - the table name
    # optional alias    - optional AS keyword and alias
    pattern = (
        r"(?:FROM|JOIN)\s+"
        + r"(?:" + ident + r"\.)?"  # optional schema
        + ident  # table name (required)
        + r"(?:\s+(?:AS\s+)?(\w+))?"  # optional alias
    )

    for match in re.finditer(pattern, sql, re.IGNORECASE):
        groups = match.groups()
        # Groups 0-3: schema (quoted/backtick/bracket/unquoted)
        # Groups 4-7: table (quoted/backtick/bracket/unquoted)
        # Group 8: alias

        # Extract schema - first non-None of groups 0-3
        schema = next((g for g in groups[0:4] if g is not None), None)

        # Extract table - first non-None of groups 4-7
        table = next((g for g in groups[4:8] if g is not None), None)

        # Extract alias
        alias = groups[8]

        # Validate alias isn't a reserved word
        if alias and alias.lower() in RESERVED_WORDS:
            alias = None

        if table:
            refs.append(TableRef(name=table, alias=alias, schema=schema))

    return refs


def extract_cte_names(sql: str) -> list[str]:
    """Extract CTE (Common Table Expression) names from WITH clause.

    Args:
        sql: The SQL text to parse

    Returns:
        List of CTE names
    """
    ctes: list[str] = []

    # Pattern: WITH cte_name AS (
    # Also handles: WITH cte1 AS (...), cte2 AS (...)
    pattern = r"\bWITH\s+(.+?)(?=\s+SELECT\b)"

    match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    if match:
        with_clause = match.group(1)
        # Extract individual CTE names
        cte_pattern = r"(\w+)\s+AS\s*\("
        for cte_match in re.finditer(cte_pattern, with_clause, re.IGNORECASE):
            ctes.append(cte_match.group(1))

    return ctes


def _is_inside_string(sql: str) -> bool:
    """Check if the cursor position is inside an unclosed string literal.

    Args:
        sql: The SQL text up to cursor position

    Returns:
        True if inside a string literal, False otherwise
    """
    in_single_quote = False
    in_double_quote = False
    i = 0

    while i < len(sql):
        char = sql[i]

        # Handle escaped quotes ('' or "")
        if char == "'" and not in_double_quote:
            if i + 1 < len(sql) and sql[i + 1] == "'":
                # Escaped single quote, skip both
                i += 2
                continue
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            if i + 1 < len(sql) and sql[i + 1] == '"':
                # Escaped double quote, skip both
                i += 2
                continue
            in_double_quote = not in_double_quote

        i += 1

    return in_single_quote or in_double_quote


def _get_last_token_info(sql: str) -> tuple[str | None, str | None]:
    """Get the last meaningful token and its type using sqlparse.

    Args:
        sql: The SQL text to analyze

    Returns:
        Tuple of (token_value, token_type_string)
    """
    try:
        import sqlparse

        parsed = sqlparse.parse(sql)
        if not parsed:
            return None, None

        tokens = [t for t in parsed[0].flatten() if not t.is_whitespace]
        if not tokens:
            return None, None

        last = tokens[-1]
        ttype = str(last.ttype) if last.ttype else None
        return last.value, ttype
    except Exception:
        return None, None


def get_context(sql: str, cursor_pos: int) -> list[Suggestion]:
    """Determine what type of suggestions to provide based on cursor position.

    Uses sqlparse for accurate token-based context detection.

    Args:
        sql: The full SQL text
        cursor_pos: Position of cursor in the text

    Returns:
        List of Suggestion objects indicating what to suggest
    """
    # Get text before cursor
    before_cursor = sql[:cursor_pos]

    # Don't suggest anything if we're inside a string literal
    if _is_inside_string(before_cursor):
        return []

    # Check for table.column pattern (alias or table prefix)
    # Pattern: word followed by dot at end
    dot_match = re.search(r"(\w+)\.\w*$", before_cursor)
    if dot_match:
        prefix = dot_match.group(1)
        return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=prefix)]

    # Use sqlparse to detect operators - only when cursor is after whitespace
    # This means the previous word is complete (not being typed)
    if before_cursor and before_cursor[-1] in " \t\n":
        token_value, token_type = _get_last_token_info(before_cursor.rstrip())

        # Determine context based on last token type
        if token_type:
            # After a comparison operator (=, <, >, etc.) -> suggest columns/values
            if "Comparison" in token_type:
                return [Suggestion(type=SuggestionType.COLUMN)]

            # After a Name (column/table name) or ) (function call) in WHERE context -> suggest operators
            if token_type == "Token.Name" or (token_type == "Token.Punctuation" and token_value == ")"):
                # Check if we're in a WHERE/HAVING/ON clause
                clean_sql = _remove_string_literals(before_cursor)
                clean_sql = _remove_comments(clean_sql)
                clause = _find_current_clause(clean_sql)
                if clause in ("where", "having", "on"):
                    # After column name or function call in WHERE -> suggest operators
                    return [Suggestion(type=SuggestionType.OPERATOR)]

    # Fall back to keyword-based context detection
    clean_sql = _remove_string_literals(before_cursor)
    clean_sql = _remove_comments(clean_sql)
    context_keyword = _find_context_keyword(clean_sql)

    if context_keyword in ("from", "join", "inner", "left", "right", "outer", "cross", "full", "into", "update", "table"):
        return [Suggestion(type=SuggestionType.TABLE)]

    if context_keyword in ("select", "where", "and", "or", "on", "having", "set"):
        return [Suggestion(type=SuggestionType.COLUMN)]

    if context_keyword in ("order", "group"):
        if re.search(r"\b(ORDER|GROUP)\s+BY\s+\w*$", clean_sql, re.IGNORECASE):
            return [Suggestion(type=SuggestionType.COLUMN)]
        return [Suggestion(type=SuggestionType.KEYWORD)]

    if context_keyword in ("exec", "execute", "call"):
        return [Suggestion(type=SuggestionType.PROCEDURE)]

    if context_keyword == ",":
        clause = _find_current_clause(clean_sql)
        if clause == "select":
            return [Suggestion(type=SuggestionType.COLUMN)]
        if clause in ("from", "join"):
            return [Suggestion(type=SuggestionType.TABLE)]
        return [Suggestion(type=SuggestionType.COLUMN)]

    if context_keyword in ("by",):
        return [Suggestion(type=SuggestionType.COLUMN)]

    # Default: suggest keywords
    return [Suggestion(type=SuggestionType.KEYWORD)]


def _remove_string_literals(sql: str) -> str:
    """Remove string literals from SQL to avoid false matches."""
    # Remove 'string' and "string" patterns
    result = re.sub(r"'[^']*'", "''", sql)
    result = re.sub(r'"[^"]*"', '""', result)
    return result


def _remove_comments(sql: str) -> str:
    """Remove SQL comments."""
    # Remove -- comments
    result = re.sub(r"--[^\n]*", "", sql)
    # Remove /* */ comments
    result = re.sub(r"/\*.*?\*/", "", result, flags=re.DOTALL)
    return result


def _find_context_keyword(sql: str) -> str:
    """Find the SQL keyword that provides context for completion.

    This looks for the keyword BEFORE the current partial word being typed.
    E.g., "SELECT * FROM us" -> returns "from" (not "us")
    E.g., "SELECT * FROM users WHERE " -> returns "where"
    """
    original_sql = sql
    sql = sql.rstrip()

    # If ends with comma, that's our context
    if sql.endswith(","):
        return ","

    # Check if the original SQL ends with whitespace (cursor after complete word)
    ends_with_space = len(original_sql) > len(sql) or (sql and sql[-1] in ",()")

    # Tokenize into words, keeping track of positions
    # We want the second-to-last token if the last one is a partial word
    tokens = re.findall(r"\w+|,", sql)

    if not tokens:
        return ""

    if ends_with_space or len(tokens) == 1:
        # The last complete token is our context
        return tokens[-1].lower()
    else:
        # We're typing a partial word, so look at the token before it
        if len(tokens) >= 2:
            return tokens[-2].lower()
        return tokens[-1].lower()


def _find_last_keyword(sql: str) -> str:
    """Find the last significant SQL keyword or punctuation."""
    # Tokenize backwards to find context
    sql = sql.rstrip()

    # Check for comma
    if sql.endswith(","):
        return ","

    # Find last word
    match = re.search(r"(\w+|\,)\s*$", sql)
    if match:
        word = match.group(1).lower()
        return word

    return ""


def _find_current_clause(sql: str) -> str:
    """Determine which clause the cursor is in.

    Looks for the most recent main SQL clause keyword.
    """
    sql_upper = sql.upper()

    # Find positions of main clauses using word boundaries
    # to avoid matching partial words like "orders"
    clauses = ["SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "ON"]
    join_pattern = r"\b(INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|FULL\s+JOIN|CROSS\s+JOIN|JOIN)\b"

    last_clause = ""
    last_pos = -1

    for clause in clauses:
        # Use word boundary to avoid matching "orders" as "order"
        pattern = r"\b" + clause + r"\b"
        for match in re.finditer(pattern, sql_upper):
            if match.start() > last_pos:
                last_pos = match.start()
                last_clause = clause.split()[0].lower()  # Get first word (e.g., "order" from "ORDER BY")

    # Check for JOIN separately - but ON clause should take precedence if it comes after
    for match in re.finditer(join_pattern, sql_upper):
        if match.start() > last_pos:
            last_pos = match.start()
            last_clause = "join"

    return last_clause


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
    suggestions = get_context(sql, cursor_pos)
    if not suggestions:
        return []

    # Extract current word being typed
    current_word = _get_current_word(sql, cursor_pos)

    # Build table alias map
    table_refs = extract_table_refs(sql)
    alias_map = _build_alias_map(table_refs, tables)

    # Also include CTE names as virtual tables
    cte_names = extract_cte_names(sql)

    results: list[str] = []

    for suggestion in suggestions:
        if suggestion.type == SuggestionType.TABLE:
            # Suggest tables and views
            results.extend(tables)
            # Also suggest CTEs
            results.extend(cte_names)

        elif suggestion.type == SuggestionType.COLUMN:
            # Suggest columns from all tables in scope
            for ref in table_refs:
                table_key = ref.name.lower()
                if table_key in columns:
                    results.extend(columns[table_key])

            # Also suggest table names for qualified references
            results.extend(tables)

            if include_functions:
                results.extend(get_all_functions())

        elif suggestion.type == SuggestionType.ALIAS_COLUMN:
            # Suggest columns for specific table/alias
            scope = suggestion.table_scope
            if scope:
                scope_lower = scope.lower()

                # Check if it's an alias
                if scope_lower in alias_map:
                    table_name = alias_map[scope_lower]
                    if table_name.lower() in columns:
                        results.extend(columns[table_name.lower()])
                # Check if it's a direct table name
                elif scope_lower in columns:
                    results.extend(columns[scope_lower])
                # Check if it's a CTE (no columns available)
                elif scope in cte_names:
                    # CTEs don't have pre-known columns
                    pass

        elif suggestion.type == SuggestionType.PROCEDURE:
            if procedures:
                results.extend(procedures)

        elif suggestion.type == SuggestionType.KEYWORD:
            if include_keywords:
                results.extend(get_all_keywords())
            if include_functions:
                results.extend(get_all_functions())

        elif suggestion.type == SuggestionType.OPERATOR:
            # Suggest comparison operators
            results.extend(SQL_OPERATORS)

    # Remove duplicates while preserving order
    seen: set[str] = set()
    unique_results: list[str] = []
    for r in results:
        if r.lower() not in seen:
            seen.add(r.lower())
            unique_results.append(r)

    # Apply fuzzy matching
    return fuzzy_match(current_word, unique_results)


def _get_current_word(sql: str, cursor_pos: int) -> str:
    """Get the word currently being typed at cursor position."""
    before_cursor = sql[:cursor_pos]

    # Handle table.column case - get just the part after dot
    if "." in before_cursor:
        dot_match = re.search(r"\.(\w*)$", before_cursor)
        if dot_match:
            return dot_match.group(1)

    # Get word before cursor
    match = re.search(r"(\w*)$", before_cursor)
    if match:
        return match.group(1)
    return ""


def _build_alias_map(refs: list[TableRef], known_tables: list[str]) -> dict[str, str]:
    """Build a map of alias -> table name.

    Only includes aliases for tables that exist in known_tables.
    """
    known_lower = {t.lower() for t in known_tables}
    alias_map: dict[str, str] = {}

    for ref in refs:
        if ref.alias and ref.name.lower() in known_lower:
            alias_map[ref.alias.lower()] = ref.name

    return alias_map
