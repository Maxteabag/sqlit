"""TRUNCATE TABLE statement context detection."""

from __future__ import annotations

import re


def get_truncate_completions(
    before_cursor: str, tables: list[str]
) -> list[str] | None:
    """Get completions specific to TRUNCATE context.

    Handles:
    - TRUNCATE → TABLE keyword or tables directly
    - TRUNCATE TABLE → table names

    Args:
        before_cursor: SQL text before cursor position
        tables: List of available table names

    Returns:
        List of completions, or None if not in TRUNCATE context
    """
    # Check for TRUNCATE pattern
    truncate_match = re.search(r"\bTRUNCATE\s+", before_cursor, re.IGNORECASE)
    if not truncate_match:
        return None

    after_truncate = before_cursor[truncate_match.end():]

    # Check for TRUNCATE TABLE → suggest tables
    if re.search(r"^TABLE\s+\w*$", after_truncate, re.IGNORECASE):
        return tables

    # Just TRUNCATE or partial word → suggest TABLE keyword and tables
    if not after_truncate.strip() or re.match(r"^\w*$", after_truncate.strip()):
        return ["TABLE"] + tables

    return None
