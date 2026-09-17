"""SQL formatting helpers for the query editor."""

from __future__ import annotations

import sqlparse

from sqlit.domains.query.app.multi_statement import split_statements


def _format_fragment(sql: str) -> str:
    return sqlparse.format(
        sql,
        reindent=True,
        keyword_case="upper",
        use_space_around_operators=True,
        indent_width=4,
    ).strip()


def format_sql(sql: str) -> str:
    """Format SQL without changing Sqlit's implicit statement boundaries."""
    if not sql.strip():
        return sql

    statements = split_statements(sql)
    semicolon_statements = sqlparse.split(sql)
    if len(statements) > 1 and len(semicolon_statements) == 1:
        # Sqlit also supports two blank lines as an implicit separator. Format
        # each statement independently so sqlparse cannot collapse that boundary.
        return "\n\n\n".join(_format_fragment(statement) for statement in statements)
    return _format_fragment(sql)


def _location_to_offset(text: str, location: tuple[int, int]) -> int:
    row, column = location
    lines = text.splitlines(keepends=True)
    if row >= len(lines):
        return len(text)
    return min(sum(len(line) for line in lines[:row]) + column, len(text))


def _offset_to_location(text: str, offset: int) -> tuple[int, int]:
    prefix = text[: max(0, min(offset, len(text)))]
    row = prefix.count("\n")
    last_newline = prefix.rfind("\n")
    column = len(prefix) if last_newline < 0 else len(prefix) - last_newline - 1
    return row, column


def remap_cursor_after_format(
    original: str,
    formatted: str,
    cursor: tuple[int, int],
) -> tuple[int, int]:
    """Keep the cursor beside the same non-whitespace token after formatting."""
    original_offset = _location_to_offset(original, cursor)
    token_count = sum(not char.isspace() for char in original[:original_offset])
    if token_count == 0:
        return 0, 0

    seen = 0
    formatted_offset = len(formatted)
    for index, char in enumerate(formatted):
        if not char.isspace():
            seen += 1
            if seen == token_count:
                formatted_offset = index + 1
                break
    return _offset_to_location(formatted, formatted_offset)
