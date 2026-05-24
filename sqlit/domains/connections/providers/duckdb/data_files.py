"""Detection of data files queryable directly by DuckDB.

DuckDB's `read_csv_auto`, `read_parquet`, `read_json_auto` etc. let you
query a raw data file as if it were a table. When a sqlit DuckDB connection
points at one of these files instead of a `.duckdb` database, the adapter:

1. Picks a per-process sidecar `.duckdb` file in the OS temp dir.
2. Loads the source file into a real TABLE in the sidecar on first connect.
3. Lets the user CRUD the table freely; edits persist for the lifetime of
   the sqlit process and are wiped on restart.
4. Writing back to the source file is explicit (`COPY <table> TO '<path>'`).
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path


# File extension -> DuckDB table function that can read it.
_READ_FUNCTIONS: dict[str, str] = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".parquet": "read_parquet",
    ".pq": "read_parquet",
    ".json": "read_json_auto",
    ".jsonl": "read_json_auto",
    ".ndjson": "read_json_auto",
}

# Allowed compression suffixes that wrap the data extensions above. DuckDB's
# auto-readers transparently decompress these.
_COMPRESSION_SUFFIXES: frozenset[str] = frozenset({".gz", ".zst", ".bz2"})


def get_read_function(path: Path) -> str | None:
    """Return the DuckDB table function for this file, or None if not a known
    data file extension.

    Handles compressed forms like `.csv.gz` by looking past the compression
    suffix.
    """
    suffixes = [s.lower() for s in path.suffixes]
    if not suffixes:
        return None

    last = suffixes[-1]
    if last in _COMPRESSION_SUFFIXES:
        if len(suffixes) >= 2:
            return _READ_FUNCTIONS.get(suffixes[-2])
        return None
    return _READ_FUNCTIONS.get(last)


def is_data_file(path: Path) -> bool:
    """True if the file extension is one DuckDB can query directly."""
    return get_read_function(path) is not None


def table_name_for(path: Path) -> str:
    """Build a SQL-safe table name from a file path basename.

    Strips the data and (optional) compression extension, then sanitizes
    non-identifier characters to underscores.

    Examples:
        sales.csv         -> sales
        sales-2024.csv    -> sales_2024
        events.json.gz    -> events
        123-data.parquet  -> _123_data
    """
    stem = path.name
    # Strip compression suffix if present.
    lower = stem.lower()
    for comp in _COMPRESSION_SUFFIXES:
        if lower.endswith(comp):
            stem = stem[: -len(comp)]
            break
    # Strip data extension.
    dot = stem.rfind(".")
    if dot > 0:
        stem = stem[:dot]

    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_")
    if not sanitized:
        sanitized = "data"
    if sanitized[0].isdigit():
        sanitized = "_" + sanitized
    return sanitized.lower()


def sidecar_path_for(source_path: Path) -> Path:
    """Per-process scratch `.duckdb` path for a data-file source.

    Each sqlit process gets its own directory under the OS temp dir. The
    sidecar persists for the lifetime of the process so edits within a
    sqlit session survive across query Runs. A fresh process gets a fresh
    sidecar, so source-file changes are picked up on restart and unsaved
    edits are wiped (the user opted into "re-load from source each time").
    """
    digest = hashlib.sha1(str(source_path.resolve()).encode()).hexdigest()[:16]
    base = Path(tempfile.gettempdir()) / f"sqlit-{os.getpid()}" / "data-files"
    return base / f"{digest}.duckdb"
