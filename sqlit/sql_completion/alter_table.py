"""ALTER TABLE statement context detection."""

from __future__ import annotations

import re

from .core import Suggestion, SuggestionType
from .create_table import SQL_CONSTRAINTS, SQL_DATA_TYPES

# ALTER TABLE operations
ALTER_OPERATIONS = [
    "ADD",
    "ADD COLUMN",
    "DROP",
    "DROP COLUMN",
    "ALTER",
    "ALTER COLUMN",
    "MODIFY",
    "MODIFY COLUMN",
    "RENAME",
    "RENAME COLUMN",
    "RENAME TO",
    "ADD CONSTRAINT",
    "DROP CONSTRAINT",
    "ADD PRIMARY KEY",
    "DROP PRIMARY KEY",
    "ADD FOREIGN KEY",
    "ADD INDEX",
    "DROP INDEX",
    "ADD UNIQUE",
    "SET DEFAULT",
    "DROP DEFAULT",
    "SET NOT NULL",
    "DROP NOT NULL",
]


def get_alter_table_context(before_cursor: str) -> list[Suggestion] | None:
    """Detect ALTER TABLE-specific context and return suggestions.

    Handles:
    - ALTER TABLE → table names
    - ALTER TABLE name → operations (ADD, DROP, etc.)
    - ALTER TABLE name ADD → column name (user types) then data type
    - ALTER TABLE name DROP COLUMN → existing columns
    - ALTER TABLE name ALTER COLUMN → existing columns
    - ALTER TABLE name ADD FOREIGN KEY ... REFERENCES → tables

    Args:
        before_cursor: SQL text before cursor position

    Returns:
        List of suggestions if in ALTER TABLE context, None otherwise
    """
    # Check for ALTER TABLE pattern
    alter_match = re.search(r"\bALTER\s+TABLE\s+", before_cursor, re.IGNORECASE)
    if not alter_match:
        return None

    after_alter_table = before_cursor[alter_match.end():]

    # If no table name yet, suggest tables
    if not after_alter_table.strip() or re.match(r"^\w*$", after_alter_table.strip()):
        return [Suggestion(type=SuggestionType.TABLE)]

    # Extract table name
    table_match = re.match(r"^(\w+)\s*", after_alter_table)
    if not table_match:
        return None

    table_name = table_match.group(1)
    after_table = after_alter_table[table_match.end():]

    # If nothing after table name, suggest operations
    if not after_table.strip() or re.match(r"^\w*$", after_table.strip()):
        return [Suggestion(type=SuggestionType.KEYWORD)]  # Will return ALTER_OPERATIONS

    # Check for DROP COLUMN → suggest columns
    if re.search(r"\bDROP\s+(?:COLUMN\s+)?\w*$", after_table, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=table_name)]

    # Check for ALTER/MODIFY COLUMN → suggest columns
    if re.search(r"\b(?:ALTER|MODIFY)\s+(?:COLUMN\s+)?\w*$", after_table, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=table_name)]

    # Check for RENAME COLUMN → suggest columns
    if re.search(r"\bRENAME\s+(?:COLUMN\s+)?\w*$", after_table, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=table_name)]

    # Check for ADD COLUMN name → suggest data types
    if re.search(r"\bADD\s+(?:COLUMN\s+)?\w+\s+\w*$", after_table, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.KEYWORD)]  # Will return SQL_DATA_TYPES

    # Check for REFERENCES → suggest tables
    if re.search(r"\bREFERENCES\s+\w*$", after_table, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.TABLE)]

    # Check for REFERENCES table ( → suggest columns
    ref_match = re.search(r"\bREFERENCES\s+(\w+)\s*\(\s*\w*$", after_table, re.IGNORECASE)
    if ref_match:
        ref_table = ref_match.group(1)
        return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=ref_table)]

    return None


def get_alter_table_completions(before_cursor: str, tables: list[str], columns: dict[str, list[str]]) -> list[str] | None:
    """Get completions specific to ALTER TABLE context.

    Args:
        before_cursor: SQL text before cursor position
        tables: List of available table names
        columns: Dict mapping table names to column lists

    Returns:
        List of completions, or None if not in ALTER TABLE context
    """
    alter_match = re.search(r"\bALTER\s+TABLE\s+", before_cursor, re.IGNORECASE)
    if not alter_match:
        return None

    after_alter_table = before_cursor[alter_match.end():]

    # If no table name yet or still typing table name, suggest tables
    # Only suggest tables if there's no trailing whitespace (user still typing)
    if not after_alter_table.strip():
        return tables
    # Check if it's just a partial table name (no whitespace after the word)
    if re.match(r"^\w+$", after_alter_table):
        return tables

    # Extract table name
    table_match = re.match(r"^(\w+)\s*", after_alter_table)
    if not table_match:
        return None

    table_name = table_match.group(1).lower()
    after_table = after_alter_table[table_match.end():]

    # Check for DROP COLUMN → suggest columns (must check before generic pattern)
    # Pattern requires whitespace after DROP or COLUMN to avoid matching "DROP" as partial
    if re.search(r"\bDROP\s+COLUMN\s+\w*$", after_table, re.IGNORECASE):
        if table_name in columns:
            return columns[table_name]
        return []

    # DROP without COLUMN - only match if there's whitespace after DROP
    if re.search(r"\bDROP\s+(?!COLUMN)(?!CONSTRAINT)(?!PRIMARY)(?!INDEX)\w*$", after_table, re.IGNORECASE):
        if table_name in columns:
            return columns[table_name]
        return []

    # If nothing after table name or just typing operation, suggest operations
    if not after_table.strip() or re.match(r"^\w*$", after_table.strip()):
        return ALTER_OPERATIONS

    # Check for ALTER/MODIFY COLUMN → suggest columns
    if re.search(r"\b(?:ALTER|MODIFY)\s+(?:COLUMN\s+)?\w*$", after_table, re.IGNORECASE):
        if table_name in columns:
            return columns[table_name]
        return []

    # Check for RENAME COLUMN → suggest columns
    if re.search(r"\bRENAME\s+(?:COLUMN\s+)?\w*$", after_table, re.IGNORECASE):
        if table_name in columns:
            return columns[table_name]
        return []

    # Check for ADD COLUMN name → suggest data types
    if re.search(r"\bADD\s+(?:COLUMN\s+)?\w+\s+\w*$", after_table, re.IGNORECASE):
        return SQL_DATA_TYPES

    # Check for data type followed by space → suggest constraints
    if re.search(r"\b(?:" + "|".join(SQL_DATA_TYPES) + r")(?:\s*\([^)]*\))?\s+\w*$", after_table, re.IGNORECASE):
        return SQL_CONSTRAINTS

    # Check for REFERENCES → suggest tables
    if re.search(r"\bREFERENCES\s+\w*$", after_table, re.IGNORECASE):
        return tables

    # Check for REFERENCES table ( → suggest columns
    ref_match = re.search(r"\bREFERENCES\s+(\w+)\s*\(\s*\w*$", after_table, re.IGNORECASE)
    if ref_match:
        ref_table = ref_match.group(1).lower()
        if ref_table in columns:
            return columns[ref_table]
        return []

    return None
