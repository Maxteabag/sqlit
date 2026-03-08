"""INSERT statement context detection."""

from __future__ import annotations

import re

from .core import Suggestion, SuggestionType


def get_insert_context(before_cursor: str) -> list[Suggestion] | None:
    """Detect INSERT-specific context and return suggestions.

    Handles:
    - INSERT INTO table ( → columns for that table
    - INSERT INTO table (col1, → more columns

    Args:
        before_cursor: SQL text before cursor position

    Returns:
        List of suggestions if in INSERT context, None otherwise
    """
    # Pattern: INSERT INTO table_name ( with optional columns and commas
    insert_match = re.search(
        r"\bINSERT\s+INTO\s+(\w+)\s*\([^)]*$",
        before_cursor,
        re.IGNORECASE,
    )
    if insert_match:
        # Check we're not inside VALUES clause
        if not re.search(r"\bVALUES\s*\(", before_cursor, re.IGNORECASE):
            table_name = insert_match.group(1)
            return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=table_name)]

    return None
