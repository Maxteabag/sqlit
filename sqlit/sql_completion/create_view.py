"""CREATE VIEW statement context detection."""

from __future__ import annotations

import re

from .core import Suggestion, SuggestionType


def get_create_view_completions(
    before_cursor: str, tables: list[str], columns: dict[str, list[str]]
) -> list[str] | None:
    """Get completions specific to CREATE VIEW context.

    Handles:
    - CREATE [OR REPLACE] VIEW name AS → SELECT keyword
    - After AS SELECT, delegates to normal SELECT handling

    Args:
        before_cursor: SQL text before cursor position
        tables: List of available table names
        columns: Dict mapping table names to column lists

    Returns:
        List of completions, or None if not in CREATE VIEW context
        Returns None after AS SELECT to let normal SELECT handling take over
    """
    # Check for CREATE VIEW pattern (with optional OR REPLACE)
    create_view_match = re.search(
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b",
        before_cursor,
        re.IGNORECASE,
    )
    if not create_view_match:
        return None

    after_create_view = before_cursor[create_view_match.end():]

    # Check if we're after AS SELECT - let normal SELECT handling take over
    if re.search(r"\bAS\s+SELECT\b", after_create_view, re.IGNORECASE):
        return None

    # Check for AS → suggest SELECT
    if re.search(r"\bAS\s+\w*$", after_create_view, re.IGNORECASE):
        return ["SELECT"]

    # After view name, suggest AS
    if re.search(r"^\s+\w+\s+\w*$", after_create_view):
        return ["AS"]

    # Still typing view name or haven't started
    return None
