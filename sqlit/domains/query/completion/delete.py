"""DELETE statement context detection."""

from __future__ import annotations

import re

from .core import RESERVED_WORDS, Suggestion, SuggestionType, TableRef


def get_delete_context(before_cursor: str) -> list[Suggestion] | None:
    """Detect DELETE-specific context and return suggestions.

    Handles:
    - DELETE FROM table WHERE → columns for that table (only right after WHERE or AND/OR)

    Args:
        before_cursor: SQL text before cursor position

    Returns:
        List of suggestions if in DELETE WHERE context, None otherwise
    """
    # Don't handle if we're inside a subquery (has unclosed parenthesis after DELETE)
    delete_pos = before_cursor.upper().find("DELETE")
    if delete_pos != -1:
        after_delete = before_cursor[delete_pos:]
        open_parens = after_delete.count("(") - after_delete.count(")")
        if open_parens > 0:
            # Inside a subquery, let normal context detection handle it
            return None

    # Pattern: DELETE FROM table [alias] WHERE ...
    delete_match = re.search(
        r"\bDELETE\s+FROM\s+(\w+)(?:\s+(\w+))?\s+WHERE\b",
        before_cursor,
        re.IGNORECASE,
    )
    if delete_match:
        table_name = delete_match.group(1)
        # Only suggest columns right after WHERE, AND, or OR (not after a column name)
        # This allows operator detection to work after column names
        if re.search(r"\b(WHERE|AND|OR)\s+\w*$", before_cursor, re.IGNORECASE):
            return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=table_name)]

    return None


def extract_delete_table_refs(sql: str) -> list[TableRef]:
    """Extract table references from DELETE statements.

    Handles:
    - DELETE FROM users
    - DELETE FROM users u WHERE ...
    - DELETE u FROM users u JOIN ... (SQL Server)

    Args:
        sql: The SQL text to parse

    Returns:
        List of TableRef objects
    """
    refs: list[TableRef] = []

    # Pattern: DELETE FROM table [alias]
    ident = r'(?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\w+))'

    delete_from_pattern = (
        r"\bDELETE\s+FROM\s+"
        + r"(?:" + ident + r"\.)?"  # optional schema
        + ident  # table name (required)
        + r"(?:\s+(?:AS\s+)?(\w+))?"  # optional alias
    )

    for match in re.finditer(delete_from_pattern, sql, re.IGNORECASE):
        groups = match.groups()
        schema = next((g for g in groups[0:4] if g is not None), None)
        table = next((g for g in groups[4:8] if g is not None), None)
        alias = groups[8]

        if alias and alias.lower() in RESERVED_WORDS:
            alias = None

        if table:
            refs.append(TableRef(name=table, alias=alias, schema=schema))

    return refs
