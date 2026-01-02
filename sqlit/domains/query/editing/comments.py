"""Comment toggle helpers for SQL editing."""

from __future__ import annotations

SQL_COMMENT_PREFIX = "-- "


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
        stripped = lines[row].lstrip()
        if stripped:
            should_comment = not stripped.startswith("--")
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
