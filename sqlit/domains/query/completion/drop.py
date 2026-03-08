"""DROP statement context detection."""

from __future__ import annotations

import re

from .core import Suggestion, SuggestionType

# Objects that can be dropped
DROP_OBJECTS = [
    "TABLE",
    "VIEW",
    "INDEX",
    "DATABASE",
    "SCHEMA",
    "PROCEDURE",
    "FUNCTION",
    "TRIGGER",
    "SEQUENCE",
    "TYPE",
    "CONSTRAINT",
]


def get_drop_context(before_cursor: str) -> list[Suggestion] | None:
    """Detect DROP-specific context and return suggestions.

    Handles:
    - DROP → object types (TABLE, VIEW, INDEX, etc.)
    - DROP TABLE → table names
    - DROP VIEW → view names (we'll suggest tables as we don't track views separately)
    - DROP INDEX → index names
    - DROP TABLE IF EXISTS → table names

    Args:
        before_cursor: SQL text before cursor position

    Returns:
        List of suggestions if in DROP context, None otherwise
    """
    # Check for DROP pattern
    drop_match = re.search(r"\bDROP\s+", before_cursor, re.IGNORECASE)
    if not drop_match:
        return None

    after_drop = before_cursor[drop_match.end():]

    # If nothing after DROP, suggest object types
    if not after_drop.strip() or re.match(r"^\w*$", after_drop.strip()):
        return [Suggestion(type=SuggestionType.KEYWORD)]  # Will return DROP_OBJECTS

    # Check for DROP TABLE [IF EXISTS] → suggest tables
    if re.search(r"\bTABLE\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.TABLE)]

    # Check for DROP VIEW [IF EXISTS] → suggest tables/views
    if re.search(r"\bVIEW\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.TABLE)]  # Views treated as tables

    # Check for DROP INDEX [IF EXISTS] → we don't track indexes, so suggest nothing special
    if re.search(r"\bINDEX\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.KEYWORD)]  # Could track indexes in future

    # Check for DROP DATABASE/SCHEMA → suggest nothing (not tracked)
    if re.search(r"\b(?:DATABASE|SCHEMA)\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.KEYWORD)]

    # Check for DROP PROCEDURE/FUNCTION → suggest procedures
    if re.search(r"\b(?:PROCEDURE|FUNCTION)\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.PROCEDURE)]

    return None


def get_drop_completions(before_cursor: str, tables: list[str], procedures: list[str] | None = None) -> list[str] | None:
    """Get completions specific to DROP context.

    Args:
        before_cursor: SQL text before cursor position
        tables: List of available table names
        procedures: List of stored procedure names

    Returns:
        List of completions, or None if not in DROP context
    """
    drop_match = re.search(r"\bDROP\s+", before_cursor, re.IGNORECASE)
    if not drop_match:
        return None

    after_drop = before_cursor[drop_match.end():]

    # Check for DROP TABLE [IF EXISTS] → suggest tables (must check before generic pattern)
    if re.search(r"^TABLE\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return tables

    # Check for DROP VIEW [IF EXISTS] → suggest tables (views mixed with tables in our schema)
    if re.search(r"^VIEW\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return tables

    # Check for DROP PROCEDURE/FUNCTION → suggest procedures
    if re.search(r"^(?:PROCEDURE|FUNCTION)\s+(?:IF\s+EXISTS\s+)?\w*$", after_drop, re.IGNORECASE):
        return procedures or []

    # If nothing after DROP or just typing object type, suggest object types
    if not after_drop.strip() or re.match(r"^\w*$", after_drop.strip()):
        return DROP_OBJECTS

    return None
