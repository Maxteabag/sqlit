"""Operator functions that apply actions to ranges.

Operators use motions/text objects to determine the range,
then perform an action (delete, yank, change).
"""

from __future__ import annotations

from collections.abc import Callable

from .types import MotionType, OperatorResult, Range


def _apply_range_delete(
    text: str, range: Range
) -> tuple[str, str, int, int]:
    """Delete text in range, return (new_text, deleted_text, new_row, new_col)."""
    lines = text.split("\n")
    if not lines:
        return "", "", 0, 0

    r = range.ordered()

    start_row, start_col = r.start.row, r.start.col
    end_row, end_col = r.end.row, r.end.col

    # Clamp to valid bounds
    start_row = max(0, min(start_row, len(lines) - 1))
    end_row = max(0, min(end_row, len(lines) - 1))
    start_col = max(0, min(start_col, len(lines[start_row])))
    end_col = max(0, min(end_col, len(lines[end_row])))

    # Adjust for inclusive end
    if r.inclusive:
        end_col += 1
        end_col = min(end_col, len(lines[end_row]))

    if r.motion_type == MotionType.LINEWISE:
        # Delete entire lines
        deleted_lines = lines[start_row : end_row + 1]
        deleted = "\n".join(deleted_lines)
        new_lines = lines[:start_row] + lines[end_row + 1 :]
        if not new_lines:
            new_lines = [""]
        new_row = min(start_row, len(new_lines) - 1)
        new_col = 0
        return "\n".join(new_lines), deleted, new_row, new_col
    else:
        # Character-wise delete
        if start_row == end_row:
            line = lines[start_row]
            deleted = line[start_col:end_col]
            lines[start_row] = line[:start_col] + line[end_col:]
        else:
            # Multi-line delete
            first_line = lines[start_row]
            last_line = lines[end_row]
            deleted_parts = [first_line[start_col:]]
            deleted_parts.extend(lines[start_row + 1 : end_row])
            deleted_parts.append(last_line[:end_col])
            deleted = "\n".join(deleted_parts)

            lines[start_row] = first_line[:start_col] + last_line[end_col:]
            del lines[start_row + 1 : end_row + 1]

        new_row = start_row
        new_col = min(start_col, len(lines[start_row]) if lines else 0)
        return "\n".join(lines), deleted, new_row, new_col


def operator_delete(text: str, range: Range) -> OperatorResult:
    """Delete text in range (d operator)."""
    new_text, deleted, new_row, new_col = _apply_range_delete(text, range)
    return OperatorResult(
        text=new_text,
        row=new_row,
        col=new_col,
        yanked=deleted,
    )


def operator_yank(text: str, range: Range) -> OperatorResult:
    """Yank (copy) text in range (y operator)."""
    lines = text.split("\n")
    if not lines:
        return OperatorResult(text=text, row=0, col=0, yanked="")

    r = range.ordered()

    start_row, start_col = r.start.row, r.start.col
    end_row, end_col = r.end.row, r.end.col

    # Clamp
    start_row = max(0, min(start_row, len(lines) - 1))
    end_row = max(0, min(end_row, len(lines) - 1))
    start_col = max(0, min(start_col, len(lines[start_row])))
    end_col = max(0, min(end_col, len(lines[end_row])))

    if r.inclusive:
        end_col += 1
        end_col = min(end_col, len(lines[end_row]))

    if r.motion_type == MotionType.LINEWISE:
        yanked = "\n".join(lines[start_row : end_row + 1])
    elif start_row == end_row:
        yanked = lines[start_row][start_col:end_col]
    else:
        parts = [lines[start_row][start_col:]]
        parts.extend(lines[start_row + 1 : end_row])
        parts.append(lines[end_row][:end_col])
        yanked = "\n".join(parts)

    # Cursor doesn't move for yank
    return OperatorResult(
        text=text,
        row=r.start.row,
        col=r.start.col,
        yanked=yanked,
    )


def operator_change(text: str, range: Range) -> OperatorResult:
    """Change text in range (c operator) - delete and enter insert mode."""
    result = operator_delete(text, range)
    return OperatorResult(
        text=result.text,
        row=result.row,
        col=result.col,
        yanked=result.yanked,
        enter_insert=True,
    )


# ============================================================================
# Operator registry
# ============================================================================

OperatorFunc = Callable[[str, Range], OperatorResult]

OPERATORS: dict[str, OperatorFunc] = {
    "d": operator_delete,
    "y": operator_yank,
    "c": operator_change,
}
