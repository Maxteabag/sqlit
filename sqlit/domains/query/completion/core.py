"""Core SQL completion utilities.

Shared logic for fuzzy matching, table extraction, keywords, and helper functions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import NamedTuple

from .keywords import SQL_FUNCTIONS, SQL_KEYWORDS, SQL_OPERATORS  # noqa: F401


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
    - UPDATE users u SET ...
    - DELETE FROM users u WHERE ...

    Args:
        sql: The SQL text to parse

    Returns:
        List of TableRef objects with name, alias, and optional schema
    """
    refs: list[TableRef] = []

    # Pattern to match quoted identifiers: "name", [name], `name`, or unquoted name
    ident = r'(?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\w+))'

    # Pattern for FROM/JOIN
    from_join_pattern = (
        r"(?:FROM|JOIN)\s+"
        + r"(?:" + ident + r"\.)?"  # optional schema
        + ident  # table name (required)
        + r"(?:\s+(?:AS\s+)?(\w+))?"  # optional alias
    )

    for match in re.finditer(from_join_pattern, sql, re.IGNORECASE):
        groups = match.groups()
        schema = next((g for g in groups[0:4] if g is not None), None)
        table = next((g for g in groups[4:8] if g is not None), None)
        alias = groups[8]

        if alias and alias.lower() in RESERVED_WORDS:
            alias = None

        if table:
            refs.append(TableRef(name=table, alias=alias, schema=schema))

    # Pattern for UPDATE table [alias] SET
    update_pattern = (
        r"\bUPDATE\s+"
        + r"(?:" + ident + r"\.)?"  # optional schema
        + ident  # table name (required)
        + r"(?:\s+(?:AS\s+)?(\w+))?"  # optional alias
        + r"(?=\s+SET\b)"  # followed by SET (lookahead)
    )

    for match in re.finditer(update_pattern, sql, re.IGNORECASE):
        groups = match.groups()
        schema = next((g for g in groups[0:4] if g is not None), None)
        table = next((g for g in groups[4:8] if g is not None), None)
        alias = groups[8]

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

    pattern = r"\bWITH\s+(.+?)(?=\s+SELECT\b)"

    match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    if match:
        with_clause = match.group(1)
        cte_pattern = r"(\w+)\s+AS\s*\("
        for cte_match in re.finditer(cte_pattern, with_clause, re.IGNORECASE):
            ctes.append(cte_match.group(1))

    return ctes


def is_inside_string(sql: str) -> bool:
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

        if char == "'" and not in_double_quote:
            if i + 1 < len(sql) and sql[i + 1] == "'":
                i += 2
                continue
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            if i + 1 < len(sql) and sql[i + 1] == '"':
                i += 2
                continue
            in_double_quote = not in_double_quote

        i += 1

    return in_single_quote or in_double_quote


def get_last_token_info(sql: str) -> tuple[str | None, str | None]:
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


def remove_string_literals(sql: str) -> str:
    """Remove string literals from SQL to avoid false matches."""
    result = re.sub(r"'[^']*'", "''", sql)
    result = re.sub(r'"[^"]*"', '""', result)
    return result


def remove_comments(sql: str) -> str:
    """Remove SQL comments."""
    result = re.sub(r"--[^\n]*", "", sql)
    result = re.sub(r"/\*.*?\*/", "", result, flags=re.DOTALL)
    return result


def find_context_keyword(sql: str) -> str:
    """Find the SQL keyword that provides context for completion.

    This looks for the keyword BEFORE the current partial word being typed.
    """
    original_sql = sql
    sql = sql.rstrip()

    if sql.endswith(","):
        return ","

    ends_with_space = len(original_sql) > len(sql) or (sql and sql[-1] in ",()")

    tokens = re.findall(r"\w+|,", sql)

    if not tokens:
        return ""

    if ends_with_space or len(tokens) == 1:
        return str(tokens[-1]).lower()
    if len(tokens) >= 2:
        return str(tokens[-2]).lower()
    return str(tokens[-1]).lower()


def find_last_keyword(sql: str) -> str:
    """Find the last significant SQL keyword or punctuation."""
    sql = sql.rstrip()

    if sql.endswith(","):
        return ","

    match = re.search(r"(\w+|\,)\s*$", sql)
    if match:
        word = match.group(1).lower()
        return word

    return ""


def find_current_clause(sql: str) -> str:
    """Determine which clause the cursor is in.

    Looks for the most recent main SQL clause keyword.
    """
    sql_upper = sql.upper()

    clauses = ["SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "ON", "SET"]
    join_pattern = r"\b(INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|FULL\s+JOIN|CROSS\s+JOIN|JOIN)\b"

    last_clause = ""
    last_pos = -1

    for clause in clauses:
        pattern = r"\b" + clause + r"\b"
        for match in re.finditer(pattern, sql_upper):
            if match.start() > last_pos:
                last_pos = match.start()
                last_clause = clause.split()[0].lower()

    for match in re.finditer(join_pattern, sql_upper):
        if match.start() > last_pos:
            last_pos = match.start()
            last_clause = "join"

    return last_clause


def get_current_word(sql: str, cursor_pos: int) -> str:
    """Get the word currently being typed at cursor position."""
    before_cursor = sql[:cursor_pos]

    if "." in before_cursor:
        dot_match = re.search(r"\.(\w*)$", before_cursor)
        if dot_match:
            return dot_match.group(1)

    match = re.search(r"(\w*)$", before_cursor)
    if match:
        return match.group(1)
    return ""


def build_alias_map(refs: list[TableRef], known_tables: list[str]) -> dict[str, str]:
    """Build a map of alias -> table name.

    Only includes aliases for tables that exist in known_tables.
    """
    known_lower = {t.lower() for t in known_tables}
    alias_map: dict[str, str] = {}

    for ref in refs:
        if ref.alias and ref.name.lower() in known_lower:
            alias_map[ref.alias.lower()] = ref.name

    return alias_map
