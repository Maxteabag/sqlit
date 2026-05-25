"""Result formatters for copy & export.

Shared by the clipboard copy actions (ry/ryf menus) and the file export
flow (rye menu). Each ResultFormat ties a formatter function to a file
extension and a display label so the registry can drive both paths.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

Rows = Sequence[Sequence[Any]]
Columns = Sequence[str]


def format_csv(columns: Columns, rows: Rows) -> str:
    """Format results as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    if columns:
        writer.writerow(list(columns))
    for row in rows:
        writer.writerow(str(val) if val is not None else "" for val in row)
    return output.getvalue()


def format_json(columns: Columns, rows: Rows) -> str:
    """Format results as JSON string (array of objects)."""
    cols = list(columns)
    result = [
        dict(zip(cols, [val if val is not None else None for val in row]))
        for row in rows
    ]
    return json.dumps(result, indent=2, default=str)


def format_markdown(columns: Columns, rows: Rows) -> str:
    """Format results as a GitHub-flavored markdown table."""

    def cell(value: Any) -> str:
        if value is None:
            return ""
        # Escape pipes and flatten newlines so the table layout survives.
        return str(value).replace("|", "\\|").replace("\r", "").replace("\n", " ")

    cols = list(columns)
    lines: list[str] = []
    if cols:
        lines.append("| " + " | ".join(cell(c) for c in cols) + " |")
        lines.append("| " + " | ".join("---" for _ in cols) + " |")
    for row in rows:
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    return "\n".join(lines) + ("\n" if lines else "")


def format_values_list(values: Sequence[Any], separator: str = ", ") -> str:
    """Format a flat sequence of values as a separator-joined plain list.

    Intended for re-using a column's values inside `WHERE col IN (...)` or
    similar. Numeric values pass through; strings are SQL-quoted with single
    quotes doubled. NULL becomes the literal `NULL` (unquoted).
    """

    def fmt(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value).replace("'", "''")
        return f"'{text}'"

    return separator.join(fmt(v) for v in values)


@dataclass(frozen=True)
class ResultFormat:
    """A copy/export format with formatter, label, and file extension."""

    key: str
    label: str
    extension: str
    formatter: Callable[[Columns, Rows], str]


FORMATS: dict[str, ResultFormat] = {
    "csv": ResultFormat("csv", "CSV", "csv", format_csv),
    "json": ResultFormat("json", "JSON", "json", format_json),
    "markdown": ResultFormat("markdown", "Markdown", "md", format_markdown),
}
