"""Clipboard operations for the query editor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PasteResult:
    """Result of a paste operation."""

    text: str
    row: int
    col: int


def select_all_range(text: str) -> tuple[int, int, int, int]:
    """Get selection range for all text.

    Returns (start_row, start_col, end_row, end_col).
    """
    lines = text.split("\n")
    if not lines:
        return (0, 0, 0, 0)
    return (0, 0, len(lines) - 1, len(lines[-1]))


def paste_text(text: str, row: int, col: int, clipboard: str) -> PasteResult:
    """Paste clipboard content at cursor position."""
    lines = text.split("\n")
    if not lines:
        lines = [""]

    row = max(0, min(row, len(lines) - 1))
    col = max(0, min(col, len(lines[row])))

    # Split clipboard into lines
    paste_lines = clipboard.split("\n")

    if len(paste_lines) == 1:
        # Single line paste
        line = lines[row]
        lines[row] = line[:col] + clipboard + line[col:]
        new_col = col + len(clipboard)
        return PasteResult("\n".join(lines), row, new_col)
    else:
        # Multi-line paste
        line = lines[row]
        before = line[:col]
        after = line[col:]

        new_lines = (
            lines[:row]
            + [before + paste_lines[0]]
            + paste_lines[1:-1]
            + [paste_lines[-1] + after]
            + lines[row + 1 :]
        )

        new_row = row + len(paste_lines) - 1
        new_col = len(paste_lines[-1])

        return PasteResult("\n".join(new_lines), new_row, new_col)


def get_selection_text(
    text: str,
    start_row: int,
    start_col: int,
    end_row: int,
    end_col: int,
) -> str:
    """Extract text from a selection range."""
    lines = text.split("\n")
    if not lines:
        return ""

    # Clamp
    start_row = max(0, min(start_row, len(lines) - 1))
    end_row = max(0, min(end_row, len(lines) - 1))
    start_col = max(0, min(start_col, len(lines[start_row])))
    end_col = max(0, min(end_col, len(lines[end_row])))

    # Ensure start <= end
    if (start_row, start_col) > (end_row, end_col):
        start_row, start_col, end_row, end_col = end_row, end_col, start_row, start_col

    if start_row == end_row:
        return lines[start_row][start_col:end_col]
    else:
        parts = [lines[start_row][start_col:]]
        parts.extend(lines[start_row + 1 : end_row])
        parts.append(lines[end_row][:end_col])
        return "\n".join(parts)
