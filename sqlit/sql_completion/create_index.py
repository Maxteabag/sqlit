"""CREATE INDEX statement context detection."""

from __future__ import annotations

import re

from .core import Suggestion, SuggestionType


def get_create_index_completions(
    before_cursor: str, tables: list[str], columns: dict[str, list[str]]
) -> list[str] | None:
    """Get completions specific to CREATE INDEX context.

    Handles:
    - CREATE [UNIQUE] INDEX name ON → tables
    - CREATE INDEX name ON table ( → columns
    - CREATE INDEX name ON table (col1, → more columns

    Args:
        before_cursor: SQL text before cursor position
        tables: List of available table names
        columns: Dict mapping table names to column lists

    Returns:
        List of completions, or None if not in CREATE INDEX context
    """
    # Check for CREATE INDEX pattern (with optional UNIQUE)
    if not re.search(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", before_cursor, re.IGNORECASE):
        return None

    # Check for ON table ( → suggest columns
    # Pattern: ON table_name ( with optional columns already listed
    table_paren_match = re.search(
        r"\bON\s+(\w+)\s*\(\s*(?:[\w\s,]*,\s*)?\w*$",
        before_cursor,
        re.IGNORECASE,
    )
    if table_paren_match:
        table_name = table_paren_match.group(1).lower()
        if table_name in columns:
            return columns[table_name]
        return []

    # Check for ON → suggest tables
    if re.search(r"\bON\s+\w*$", before_cursor, re.IGNORECASE):
        return tables

    # After CREATE INDEX name, suggest ON keyword
    if re.search(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+\w+\s+\w*$", before_cursor, re.IGNORECASE):
        return ["ON"]

    return None
