"""UPDATE statement context detection."""

from __future__ import annotations

import re

from .core import Suggestion, SuggestionType


def get_update_context(before_cursor: str) -> list[Suggestion] | None:
    """Detect UPDATE-specific context and return suggestions.

    Handles:
    - UPDATE table SET → columns for that table
    - UPDATE table SET col = value, → more columns

    Args:
        before_cursor: SQL text before cursor position

    Returns:
        List of suggestions if in UPDATE SET context, None otherwise
    """
    # Pattern: UPDATE table [alias] SET ... (not after WHERE or FROM)
    update_set_match = re.search(
        r"\bUPDATE\s+(\w+)(?:\s+\w+)?\s+SET\b",
        before_cursor,
        re.IGNORECASE,
    )
    if update_set_match:
        # Check we're not in WHERE or FROM clause (SQL Server UPDATE...FROM...JOIN syntax)
        if not re.search(r"\b(WHERE|FROM)\b", before_cursor[update_set_match.end():], re.IGNORECASE):
            table_name = update_set_match.group(1)
            # Check if we're after SET (not just typing "SET")
            set_pos = before_cursor.upper().rfind("SET")
            if set_pos != -1 and len(before_cursor) > set_pos + 3:
                return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=table_name)]

    return None
