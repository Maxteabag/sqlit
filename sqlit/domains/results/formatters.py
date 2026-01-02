"""Result formatters for export (CSV, JSON)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any


def format_csv(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Format results as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(str(val) if val is not None else "" for val in row)
    return output.getvalue()


def format_json(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Format results as JSON string (array of objects)."""
    result = [
        dict(zip(columns, [val if val is not None else None for val in row]))
        for row in rows
    ]
    return json.dumps(result, indent=2, default=str)
