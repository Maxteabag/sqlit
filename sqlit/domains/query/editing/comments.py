"""SQL comment handling - detection, toggling, and stripping.

This module is the single source of truth for SQL comment logic.
All comment-related operations should use these functions.
"""

from __future__ import annotations

import re

SQL_COMMENT_PREFIX = "-- "

# Regex patterns for comment stripping
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def is_comment_line(line: str) -> bool:
    """Check if a line is a SQL line comment.

    Args:
        line: A single line of text.

    Returns:
        True if the line (after stripping whitespace) starts with --.
    """
    return line.strip().startswith("--")


def is_comment_only_statement(statement: str) -> bool:
    """Check if a SQL statement contains only comments (no actual SQL).

    A statement is comment-only if every non-empty line starts with --.
    This is used to filter out statements that would cause "empty query"
    errors in database drivers that strip comments before execution.

    Args:
        statement: A SQL statement (may be multi-line).

    Returns:
        True if the statement contains only comments.
    """
    lines = statement.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


def strip_line_comments(sql: str) -> str:
    """Remove all line comments (-- ...) from SQL.

    Note: This is a simple regex-based approach that doesn't account for
    -- inside string literals. For keyword detection this is usually fine,
    but for actual SQL transformation, use with caution.

    Args:
        sql: SQL text that may contain line comments.

    Returns:
        SQL with line comments removed.
    """
    return _LINE_COMMENT_RE.sub("", sql)


def strip_block_comments(sql: str) -> str:
    """Remove all block comments (/* ... */) from SQL.

    Args:
        sql: SQL text that may contain block comments.

    Returns:
        SQL with block comments removed.
    """
    return _BLOCK_COMMENT_RE.sub("", sql)


def strip_all_comments(sql: str) -> str:
    """Remove all comments (both line and block) from SQL.

    Args:
        sql: SQL text that may contain comments.

    Returns:
        SQL with all comments removed.
    """
    result = strip_block_comments(sql)
    result = strip_line_comments(result)
    return result


def toggle_comment_lines(text: str, start_row: int, end_row: int) -> tuple[str, int]:
    """Toggle SQL comments on a range of lines.

    Args:
        text: The full text content
        start_row: First line to toggle (0-indexed)
        end_row: Last line to toggle (0-indexed, inclusive)

    Returns:
        Tuple of (new_text, new_cursor_col) where new_cursor_col is the
        appropriate column position after the toggle.
    """
    lines = text.split("\n")
    if not lines:
        return text, 0

    # Clamp row bounds
    start_row = max(0, min(start_row, len(lines) - 1))
    end_row = max(0, min(end_row, len(lines) - 1))
    if start_row > end_row:
        start_row, end_row = end_row, start_row

    # Determine if we should comment or uncomment based on first non-empty line
    should_comment = True
    for row in range(start_row, end_row + 1):
        if lines[row].strip():
            should_comment = not is_comment_line(lines[row])
            break

    # Apply toggle to each line
    new_col = 0
    for row in range(start_row, end_row + 1):
        line = lines[row]
        if should_comment:
            new_line, col = _comment_line(line)
        else:
            new_line, col = _uncomment_line(line)
        lines[row] = new_line
        if row == start_row:
            new_col = col

    return "\n".join(lines), new_col


def _comment_line(line: str) -> tuple[str, int]:
    """Add SQL comment to a line, preserving indentation.

    Returns:
        Tuple of (new_line, cursor_col) where cursor_col is positioned
        after the comment prefix on the first non-whitespace.
    """
    if not line or line.isspace():
        # Empty or whitespace-only line: just add comment at start
        return SQL_COMMENT_PREFIX + line, len(SQL_COMMENT_PREFIX)

    # Find leading whitespace
    indent_end = 0
    while indent_end < len(line) and line[indent_end].isspace():
        indent_end += 1

    # Insert comment after indentation
    new_line = line[:indent_end] + SQL_COMMENT_PREFIX + line[indent_end:]
    return new_line, indent_end + len(SQL_COMMENT_PREFIX)


def _uncomment_line(line: str) -> tuple[str, int]:
    """Remove SQL comment from a line.

    Returns:
        Tuple of (new_line, cursor_col) where cursor_col is positioned
        at the first non-whitespace character.
    """
    # Find leading whitespace
    indent_end = 0
    while indent_end < len(line) and line[indent_end].isspace():
        indent_end += 1

    rest = line[indent_end:]

    # Check for comment prefix variants: "-- " or "--"
    if rest.startswith("-- "):
        new_line = line[:indent_end] + rest[3:]
        return new_line, indent_end
    elif rest.startswith("--"):
        new_line = line[:indent_end] + rest[2:]
        return new_line, indent_end

    # No comment found, return unchanged
    return line, indent_end
