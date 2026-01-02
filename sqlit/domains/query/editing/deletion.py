"""Deletion helpers for query text editing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EditResult:
    text: str
    row: int
    col: int


def delete_line(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not lines:
        return EditResult("", 0, 0)
    lines.pop(row)
    if not lines:
        return EditResult("", 0, 0)
    row = min(row, len(lines) - 1)
    col = min(col, len(lines[row]))
    return EditResult("\n".join(lines), row, col)


def delete_word(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not lines:
        return EditResult("", 0, 0)
    line = lines[row]
    if col >= len(line):
        return EditResult(text, row, col)
    start = col
    if line[start].isspace():
        end = start
        while end < len(line) and line[end].isspace():
            end += 1
    else:
        end = start
        if _is_word_char(line[end]):
            while end < len(line) and _is_word_char(line[end]):
                end += 1
        else:
            end = start + 1
        while end < len(line) and line[end].isspace():
            end += 1
    lines[row] = line[:start] + line[end:]
    return EditResult("\n".join(lines), row, min(start, len(lines[row])))


def delete_word_back(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not lines:
        return EditResult("", 0, 0)
    line = lines[row]
    if col <= 0:
        return EditResult(text, row, col)
    start = col
    while start > 0 and line[start - 1].isspace():
        start -= 1
    if start > 0:
        if _is_word_char(line[start - 1]):
            while start > 0 and _is_word_char(line[start - 1]):
                start -= 1
        else:
            start -= 1
    lines[row] = line[:start] + line[col:]
    return EditResult("\n".join(lines), row, start)


def delete_word_end(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not lines:
        return EditResult("", 0, 0)
    line = lines[row]
    if col >= len(line):
        return EditResult(text, row, col)
    end = col
    while end < len(line) and line[end].isspace():
        end += 1
    if end >= len(line):
        return EditResult(text, row, col)
    if _is_word_char(line[end]):
        while end < len(line) and _is_word_char(line[end]):
            end += 1
    else:
        end += 1
    lines[row] = line[:col] + line[end:]
    return EditResult("\n".join(lines), row, min(col, len(lines[row])))


def delete_line_start(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not lines:
        return EditResult("", 0, 0)
    line = lines[row]
    if col <= 0:
        return EditResult(text, row, col)
    lines[row] = line[col:]
    return EditResult("\n".join(lines), row, 0)


def delete_line_end(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not lines:
        return EditResult("", 0, 0)
    line = lines[row]
    if col >= len(line):
        return EditResult(text, row, col)
    lines[row] = line[:col]
    return EditResult("\n".join(lines), row, col)


def delete_char(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not text:
        return EditResult("", 0, 0)
    index = _cursor_index(lines, row, col)
    if index >= len(text):
        return EditResult(text, row, col)
    new_text = text[:index] + text[index + 1 :]
    new_row, new_col = _cursor_from_index(new_text, index)
    return EditResult(new_text, new_row, new_col)


def delete_char_back(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not text:
        return EditResult("", 0, 0)
    index = _cursor_index(lines, row, col)
    if index <= 0:
        return EditResult(text, row, col)
    new_index = index - 1
    new_text = text[:new_index] + text[index:]
    new_row, new_col = _cursor_from_index(new_text, new_index)
    return EditResult(new_text, new_row, new_col)


def delete_to_end(text: str, row: int, col: int) -> EditResult:
    lines, row, col = _normalize(text, row, col)
    if not text:
        return EditResult("", 0, 0)
    index = _cursor_index(lines, row, col)
    if index >= len(text):
        return EditResult(text, row, col)
    new_text = text[:index]
    new_row, new_col = _cursor_from_index(new_text, index)
    return EditResult(new_text, new_row, new_col)


def delete_all(text: str, row: int, col: int) -> EditResult:
    _ = (text, row, col)
    return EditResult("", 0, 0)


def _normalize(text: str, row: int, col: int) -> tuple[list[str], int, int]:
    lines = text.split("\n")
    if not lines:
        lines = [""]
    row = max(0, min(row, len(lines) - 1))
    col = max(0, min(col, len(lines[row])))
    return lines, row, col


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _cursor_index(lines: list[str], row: int, col: int) -> int:
    return sum(len(lines[i]) + 1 for i in range(row)) + col


def _cursor_from_index(text: str, index: int) -> tuple[int, int]:
    index = max(0, min(index, len(text)))
    if not text:
        return 0, 0
    before = text[:index]
    row = before.count("\n")
    last_break = before.rfind("\n")
    col = index if last_break == -1 else index - last_break - 1
    return row, col
