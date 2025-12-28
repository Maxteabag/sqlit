"""CREATE TABLE statement context detection."""

from __future__ import annotations

import re

from .core import Suggestion, SuggestionType

# SQL Data types for column definitions
SQL_DATA_TYPES = [
    # Numeric
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
    "DOUBLE PRECISION",
    "MONEY",
    "SMALLMONEY",
    # String
    "VARCHAR",
    "CHAR",
    "TEXT",
    "NVARCHAR",
    "NCHAR",
    "NTEXT",
    # Binary
    "BINARY",
    "VARBINARY",
    "BLOB",
    "BYTEA",
    # Date/Time
    "DATE",
    "TIME",
    "DATETIME",
    "DATETIME2",
    "DATETIMEOFFSET",
    "SMALLDATETIME",
    "TIMESTAMP",
    "TIMESTAMPTZ",
    "INTERVAL",
    # Boolean
    "BOOLEAN",
    "BOOL",
    "BIT",
    # Other
    "UUID",
    "UNIQUEIDENTIFIER",
    "JSON",
    "JSONB",
    "XML",
    "CLOB",
    "SERIAL",
    "BIGSERIAL",
    "SMALLSERIAL",
    "IDENTITY",
]

# Column constraints
SQL_CONSTRAINTS = [
    "PRIMARY KEY",
    "NOT NULL",
    "NULL",
    "UNIQUE",
    "DEFAULT",
    "CHECK",
    "REFERENCES",
    "AUTO_INCREMENT",
    "AUTOINCREMENT",
    "GENERATED",
]

# Table-level constraints
SQL_TABLE_CONSTRAINTS = [
    "PRIMARY KEY",
    "FOREIGN KEY",
    "UNIQUE",
    "CHECK",
    "CONSTRAINT",
    "INDEX",
]


class SuggestionTypeExtended:
    """Extended suggestion types for DDL."""
    DATA_TYPE = "DATA_TYPE"
    CONSTRAINT = "CONSTRAINT"
    TABLE_CONSTRAINT = "TABLE_CONSTRAINT"


def get_create_table_context(before_cursor: str) -> list[Suggestion] | None:
    """Detect CREATE TABLE-specific context and return suggestions.

    Handles:
    - CREATE TABLE name ( → nothing (user defines column name)
    - CREATE TABLE name (col → data types
    - CREATE TABLE name (col TYPE → constraints
    - CREATE TABLE name (col TYPE, → nothing (new column name)
    - FOREIGN KEY (col) REFERENCES → table names
    - REFERENCES table ( → column names

    Args:
        before_cursor: SQL text before cursor position

    Returns:
        List of suggestions if in CREATE TABLE context, None otherwise
    """
    # Check if we're in a CREATE TABLE statement
    if not re.search(r"\bCREATE\s+TABLE\b", before_cursor, re.IGNORECASE):
        return None

    # Check if we're inside the column definition parentheses
    create_match = re.search(
        r"\bCREATE\s+TABLE\s+\w+\s*\((.*)$",
        before_cursor,
        re.IGNORECASE | re.DOTALL,
    )
    if not create_match:
        return None

    inside_parens = create_match.group(1)

    # Check for REFERENCES table ( → suggest columns
    ref_table_match = re.search(
        r"\bREFERENCES\s+(\w+)\s*\(\s*\w*$",
        inside_parens,
        re.IGNORECASE,
    )
    if ref_table_match:
        table_name = ref_table_match.group(1)
        return [Suggestion(type=SuggestionType.ALIAS_COLUMN, table_scope=table_name)]

    # Check for FOREIGN KEY ... REFERENCES → suggest tables
    if re.search(r"\bREFERENCES\s+\w*$", inside_parens, re.IGNORECASE):
        return [Suggestion(type=SuggestionType.TABLE)]

    # Check if we just typed a data type and need constraints
    # Pattern: column_name TYPE (possibly with size) and cursor after space
    if re.search(r"\b(?:" + "|".join(SQL_DATA_TYPES) + r")(?:\s*\([^)]*\))?\s+\w*$", inside_parens, re.IGNORECASE):
        # After a data type, suggest constraints
        return [Suggestion(type=SuggestionType.KEYWORD)]  # Will be handled specially

    # Check if we're right after a column name (no type yet)
    # Pattern: comma or opening paren, then word, then space
    if re.search(r"(?:,|\()\s*\w+\s+\w*$", inside_parens, re.IGNORECASE):
        # After column name, suggest data types
        return [Suggestion(type=SuggestionType.KEYWORD)]  # Will be handled specially

    return None


def get_create_table_completions(before_cursor: str, tables: list[str], columns: dict[str, list[str]]) -> list[str] | None:
    """Get completions specific to CREATE TABLE context.

    Args:
        before_cursor: SQL text before cursor position
        tables: List of available table names
        columns: Dict mapping table names to column lists

    Returns:
        List of completions, or None if not in CREATE TABLE context
    """
    # Check if we're in a CREATE TABLE statement
    if not re.search(r"\bCREATE\s+TABLE\b", before_cursor, re.IGNORECASE):
        return None

    # Check if we're inside the column definition parentheses
    create_match = re.search(
        r"\bCREATE\s+TABLE\s+\w+\s*\((.*)$",
        before_cursor,
        re.IGNORECASE | re.DOTALL,
    )
    if not create_match:
        return None

    inside_parens = create_match.group(1)

    # Check for REFERENCES table ( → suggest columns from that table
    ref_table_match = re.search(
        r"\bREFERENCES\s+(\w+)\s*\(\s*\w*$",
        inside_parens,
        re.IGNORECASE,
    )
    if ref_table_match:
        table_name = ref_table_match.group(1).lower()
        if table_name in columns:
            return columns[table_name]
        return []

    # Check for FOREIGN KEY ... REFERENCES → suggest tables
    if re.search(r"\bREFERENCES\s+\w*$", inside_parens, re.IGNORECASE):
        return tables

    # Check if after a data type → suggest constraints
    if re.search(r"\b(?:" + "|".join(SQL_DATA_TYPES) + r")(?:\s*\([^)]*\))?\s+\w*$", inside_parens, re.IGNORECASE):
        return SQL_CONSTRAINTS

    # Check if right after column name → suggest data types
    # Match start of content or after comma, then column name, then space
    if re.search(r"(?:^|,)\s*\w+\s+\w*$", inside_parens, re.IGNORECASE):
        return SQL_DATA_TYPES

    # At start of new column definition (empty or after comma with space)
    if not inside_parens.strip() or re.search(r",\s*$", inside_parens):
        # User needs to type column name, no suggestions
        return []

    # Check for table-level constraint context
    if re.search(r",\s*(?:PRIMARY|FOREIGN|UNIQUE|CHECK|CONSTRAINT)\s+\w*$", inside_parens, re.IGNORECASE):
        return SQL_TABLE_CONSTRAINTS

    return None
