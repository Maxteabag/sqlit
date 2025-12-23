"""Vim operator functions.

Operators act on a range of text (defined by a motion or text object).
They're the d in "dw", the c in "ciw", the y in "y$", etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .state import TextObjectType, VimMode

if TYPE_CHECKING:
    from .document import DocumentWrapper
    from .state import VimState


@dataclass
class OperatorResult:
    """Result of an operator execution."""

    success: bool = True
    deleted_text: str = ""
    enter_insert: bool = False  # For 'c' operator


# Type alias for operator functions
OperatorFunc = Callable[
    ["DocumentWrapper", "VimState", tuple[int, int], tuple[int, int], TextObjectType],
    OperatorResult,
]


# ─────────────────────────────────────────────────────────────────
# Core Operators
# ─────────────────────────────────────────────────────────────────


def operator_delete(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Delete text in range (d operator)."""
    if obj_type == TextObjectType.LINEWISE:
        # Delete entire lines
        start_row = min(start[0], end[0])
        end_row = max(start[0], end[0])
        deleted = doc.delete_lines(start_row, end_row)
        state.yank_to_register(deleted, linewise=True)
    else:
        # Ensure start <= end
        if start > end:
            start, end = end, start

        # For inclusive motions, include the end character
        if obj_type == TextObjectType.INCLUSIVE:
            row, col = end
            line = doc.lines[row] if row < len(doc.lines) else ""
            if col < len(line):
                end = (row, col + 1)

        deleted = doc.delete_range(start, end)
        state.yank_to_register(deleted, linewise=False)

    return OperatorResult(success=True, deleted_text=deleted)


def operator_change(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Delete text and enter insert mode (c operator)."""
    result = operator_delete(doc, state, start, end, obj_type)
    result.enter_insert = True
    return result


def operator_yank(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Copy text to register (y operator)."""
    if obj_type == TextObjectType.LINEWISE:
        start_row = min(start[0], end[0])
        end_row = max(start[0], end[0])
        text = doc.get_line_range(start_row, end_row)
        state.yank_to_register(text, linewise=True)
    else:
        if start > end:
            start, end = end, start

        if obj_type == TextObjectType.INCLUSIVE:
            row, col = end
            line = doc.lines[row] if row < len(doc.lines) else ""
            if col < len(line):
                end = (row, col + 1)

        text = doc.get_text_between(start, end)
        state.yank_to_register(text, linewise=False)

    return OperatorResult(success=True)


def operator_indent(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Indent lines (> operator)."""
    start_row = min(start[0], end[0])
    end_row = max(start[0], end[0])
    lines = doc.lines

    # Insert spaces at the beginning of each line
    indent = "    "  # 4 spaces, could be configurable
    for row in range(start_row, end_row + 1):
        if row < len(lines):
            line_start = (row, 0)
            doc.replace_text(line_start, line_start, indent)

    return OperatorResult(success=True)


def operator_dedent(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Dedent lines (< operator)."""
    start_row = min(start[0], end[0])
    end_row = max(start[0], end[0])
    lines = doc.lines

    # Remove up to 4 spaces from the beginning of each line
    for row in range(start_row, end_row + 1):
        if row < len(lines):
            line = lines[row]
            spaces_to_remove = 0
            for char in line[:4]:
                if char == " ":
                    spaces_to_remove += 1
                elif char == "\t":
                    spaces_to_remove += 1
                    break
                else:
                    break

            if spaces_to_remove > 0:
                line_start = (row, 0)
                line_after = (row, spaces_to_remove)
                doc.delete_range(line_start, line_after)

    return OperatorResult(success=True)


def operator_lowercase(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Convert text to lowercase (gu operator)."""
    if start > end:
        start, end = end, start

    if obj_type == TextObjectType.INCLUSIVE:
        row, col = end
        line = doc.lines[row] if row < len(doc.lines) else ""
        if col < len(line):
            end = (row, col + 1)

    text = doc.get_text_between(start, end)
    doc.replace_text(start, end, text.lower())

    return OperatorResult(success=True)


def operator_uppercase(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Convert text to uppercase (gU operator)."""
    if start > end:
        start, end = end, start

    if obj_type == TextObjectType.INCLUSIVE:
        row, col = end
        line = doc.lines[row] if row < len(doc.lines) else ""
        if col < len(line):
            end = (row, col + 1)

    text = doc.get_text_between(start, end)
    doc.replace_text(start, end, text.upper())

    return OperatorResult(success=True)


def operator_swap_case(
    doc: DocumentWrapper,
    state: VimState,
    start: tuple[int, int],
    end: tuple[int, int],
    obj_type: TextObjectType,
) -> OperatorResult:
    """Swap case of text (g~ operator)."""
    if start > end:
        start, end = end, start

    if obj_type == TextObjectType.INCLUSIVE:
        row, col = end
        line = doc.lines[row] if row < len(doc.lines) else ""
        if col < len(line):
            end = (row, col + 1)

    text = doc.get_text_between(start, end)
    swapped = "".join(c.lower() if c.isupper() else c.upper() for c in text)
    doc.replace_text(start, end, swapped)

    return OperatorResult(success=True)


# ─────────────────────────────────────────────────────────────────
# Operator Registry
# ─────────────────────────────────────────────────────────────────

OPERATOR_HANDLERS: dict[str, OperatorFunc] = {
    "operator_delete": operator_delete,
    "operator_change": operator_change,
    "operator_yank": operator_yank,
    "operator_indent": operator_indent,
    "operator_dedent": operator_dedent,
    "operator_lowercase": operator_lowercase,
    "operator_uppercase": operator_uppercase,
    "operator_swap_case": operator_swap_case,
}


def get_operator_handler(name: str) -> OperatorFunc | None:
    """Get an operator function by handler name."""
    return OPERATOR_HANDLERS.get(name)
