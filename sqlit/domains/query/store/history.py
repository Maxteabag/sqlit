"""File-backed query history store.

Each query is a `.sql` file under
``CONFIG_DIR/queries/<connection_dir>/[<database_dir>/]<timestamp>_<hash>.sql``.

The connection always becomes a directory level; the database becomes a
second directory level when the connection runs against a named
database (MSSQL/Postgres/etc.). For file-based engines (SQLite, DuckDB)
where there's no database concept, files sit directly under the
connection dir.

Each file holds an SQL-comment header followed by a blank line and the
query body::

    -- sqlit:history
    -- connection: postgres-prod

    SELECT * FROM users

The connection name in the header is authoritative — the directory
name is sanitized + hashed for filesystem safety and is not reversible.
Timestamps and the database are encoded structurally in the path, so
they don't need to be repeated in the header.

Re-running the same query (exact text after `strip()`) deletes the old
file and writes a new one with the current timestamp, so the most-
recent timestamp always wins and the directory listing stays
chronologically sortable.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlit.shared.core.store import CONFIG_DIR

_HEADER_MARKER = "-- sqlit:history"
_HEADER_LINE = re.compile(r"^--\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


@dataclass
class QueryHistoryEntry:
    """A query history entry."""

    query: str
    timestamp: str  # ISO format
    connection_name: str
    database: str = ""
    is_starred: bool = False  # Computed at load time, not persisted
    is_starred_only: bool = False  # True if only in starred store, not in history

    def to_dict(self) -> dict:
        d: dict = {
            "query": self.query,
            "timestamp": self.timestamp,
            "connection_name": self.connection_name,
        }
        if self.database:
            d["database"] = self.database
        return d

    @classmethod
    def from_dict(cls, data: dict) -> QueryHistoryEntry:
        return cls(
            query=data["query"],
            timestamp=data["timestamp"],
            connection_name=data["connection_name"],
            database=data.get("database", ""),
        )


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:8]


def _safe_dir_name(name: str) -> str:
    """Sanitize + append short hash so distinct names always get distinct dirs."""
    safe = _SAFE_NAME.sub("_", name)[:40] or "_"
    short = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{safe}_{short}"


def _connection_dir_name(connection_name: str) -> str:
    return _safe_dir_name(connection_name)


def _database_dir_name(database: str) -> str:
    return _safe_dir_name(database)


def _timestamp_to_filename(iso_ts: str) -> str:
    """Turn an ISO timestamp into a filesystem-safe sortable prefix."""
    return iso_ts.replace(":", "-")


def _filename_to_timestamp(stem_prefix: str) -> str:
    """Inverse of _timestamp_to_filename, used to derive the canonical
    ISO timestamp from a stored filename."""
    if "T" not in stem_prefix:
        return stem_prefix
    date_part, _, time_part = stem_prefix.partition("T")
    return f"{date_part}T{time_part.replace('-', ':', 2)}"


def _format_entry(entry: QueryHistoryEntry) -> str:
    lines = [
        _HEADER_MARKER,
        f"-- connection: {entry.connection_name}",
        "",
        entry.query,
    ]
    if not entry.query.endswith("\n"):
        lines.append("")
    return "\n".join(lines)


def _parse_entry(
    text: str,
    *,
    fallback_connection: str,
    fallback_database: str,
    fallback_timestamp: str,
) -> QueryHistoryEntry | None:
    """Parse a stored .sql file. The header is the leading run of `--`
    comment lines, terminated by the first blank line. Anything after
    that is the query body."""
    lines = text.splitlines()
    metadata: dict[str, str] = {}
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped == _HEADER_MARKER:
            body_start = i + 1
            continue
        if stripped == "":
            body_start = i + 1
            break
        m = _HEADER_LINE.match(stripped)
        if m:
            key, value = m.group(1).lower(), m.group(2)
            metadata[key] = value
            body_start = i + 1
            continue
        body_start = i
        break

    query = "\n".join(lines[body_start:]).strip("\n")
    if not query:
        return None

    return QueryHistoryEntry(
        query=query,
        timestamp=metadata.get("ran") or fallback_timestamp,
        connection_name=metadata.get("connection") or fallback_connection,
        database=metadata.get("database", fallback_database),
    )


class HistoryStore:
    """File-backed query history.

    Layout::

        CONFIG_DIR/queries/<connection_dir>/<database_dir>/<timestamp>_<hash>.sql
        CONFIG_DIR/queries/<connection_dir>/<timestamp>_<hash>.sql   # db empty

    Each file holds the query prefixed by a small SQL-comment header
    (``-- sqlit:history`` and ``-- connection:``), terminated by a
    blank line.
    """

    MAX_ENTRIES_PER_CONNECTION = 100

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir if base_dir is not None else CONFIG_DIR / "queries"
        self._migrated = False

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass

    def _connection_dir(self, connection_name: str) -> Path:
        return self._base_dir / _connection_dir_name(connection_name)

    def _entry_dir(self, connection_name: str, database: str) -> Path:
        """Where a given (connection, database) pair's files live."""
        conn_dir = self._connection_dir(connection_name)
        if database:
            return conn_dir / _database_dir_name(database)
        return conn_dir

    def _maybe_migrate(self) -> None:
        if self._migrated:
            return
        self._migrated = True
        self._migrate_from_legacy_json()
        self._migrate_layout_v1_to_v2()

    def _migrate_from_legacy_json(self) -> None:
        legacy = self._base_dir.parent / "query_history.json"
        if not legacy.exists():
            return
        try:
            import json
            with legacy.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        for raw in data:
            if not isinstance(raw, dict):
                continue
            try:
                entry = QueryHistoryEntry.from_dict(raw)
            except (KeyError, TypeError):
                continue
            self._write_entry(entry)
        try:
            legacy.replace(legacy.with_suffix(".json.migrated"))
        except OSError:
            pass

    def _migrate_layout_v1_to_v2(self) -> None:
        """Move existing files written under v1 layout
        (`<conn>/<file>.sql` with `-- database:` in the header) into the
        v2 layout (`<conn>/<db>/<file>.sql`, header trimmed)."""
        if not self._base_dir.is_dir():
            return
        for conn_dir in self._base_dir.iterdir():
            if not conn_dir.is_dir():
                continue
            for path in list(conn_dir.glob("*.sql")):
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                stem = path.stem
                fallback_ts_raw = stem.rsplit("_", 1)[0] if "_" in stem else stem
                fallback_ts = _filename_to_timestamp(fallback_ts_raw)
                entry = _parse_entry(
                    text,
                    fallback_connection=conn_dir.name,
                    fallback_database="",
                    fallback_timestamp=fallback_ts,
                )
                if entry is None:
                    continue
                # If body matches what we'd write now (no db and no ran/database
                # in the header), nothing to migrate for this file.
                if not entry.database and not self._header_has_dropped_fields(text):
                    continue
                # Rewrite into the correct location with the trimmed header.
                self._write_entry(entry)
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass

    @staticmethod
    def _header_has_dropped_fields(text: str) -> bool:
        for line in text.splitlines():
            stripped = line.rstrip()
            if stripped == "":
                return False
            m = _HEADER_LINE.match(stripped)
            if m and m.group(1).lower() in {"ran", "database"}:
                return True
        return False

    def _write_entry(self, entry: QueryHistoryEntry) -> Path:
        """Write one entry to disk, replacing any prior file with the
        same query hash for this (connection, database). Atomic per-file."""
        target_dir = self._entry_dir(entry.connection_name, entry.database)
        self._ensure_dir(target_dir)

        qhash = _query_hash(entry.query)
        # Drop any same-hash file across all (conn, db) pairs so a query
        # that moves between databases doesn't leave a stale duplicate.
        for existing in self._all_files(entry.connection_name):
            if existing.name.endswith(f"_{qhash}.sql"):
                try:
                    existing.unlink()
                except OSError:
                    pass

        filename = f"{_timestamp_to_filename(entry.timestamp)}_{qhash}.sql"
        dest = target_dir / filename
        body = _format_entry(entry)

        fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp_", suffix=".sql")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, dest)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return dest

    def _all_files(self, connection_name: str) -> list[Path]:
        """Every `.sql` file for a connection, across all database subdirs."""
        conn_dir = self._connection_dir(connection_name)
        if not conn_dir.is_dir():
            return []
        files: list[Path] = []
        for path in conn_dir.glob("*.sql"):
            if path.is_file():
                files.append(path)
        for child in conn_dir.iterdir():
            if child.is_dir():
                for path in child.glob("*.sql"):
                    if path.is_file():
                        files.append(path)
        return files

    def _evict(self, connection_name: str) -> None:
        # Sort by filename only: timestamps live in the filename prefix,
        # so lex-ordering filenames = chronological ordering. Sorting by
        # full path would group by db subdir first, which is wrong.
        files = sorted(self._all_files(connection_name), key=lambda p: p.name)
        excess = len(files) - self.MAX_ENTRIES_PER_CONNECTION
        if excess <= 0:
            return
        for path in files[:excess]:
            try:
                path.unlink()
            except OSError:
                pass

    def _entries_from_files(
        self, files: list[Path], *, fallback_connection: str
    ) -> list[QueryHistoryEntry]:
        entries: list[QueryHistoryEntry] = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            stem = path.stem
            fallback_ts_raw = stem.rsplit("_", 1)[0] if "_" in stem else stem
            fallback_ts = _filename_to_timestamp(fallback_ts_raw)
            # If the file lives in a db subdir, derive db from the dir name
            # (sanitized — only useful for fallback; header trumps when present).
            parent = path.parent
            grandparent = parent.parent
            in_db_subdir = grandparent != self._base_dir and grandparent.is_dir()
            fallback_db = parent.name[:-9] if in_db_subdir and len(parent.name) > 9 and parent.name[-9] == "_" else ""
            entry = _parse_entry(
                text,
                fallback_connection=fallback_connection,
                fallback_database=fallback_db,
                fallback_timestamp=fallback_ts,
            )
            if entry is not None:
                entries.append(entry)
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def _fallback_connection_from_dir(self, conn_dir: Path) -> str:
        dir_name = conn_dir.name
        return (
            dir_name[:-9]
            if len(dir_name) > 9 and dir_name[-9] == "_"
            else dir_name
        )

    # ----- public API (matches HistoryStoreProtocol) -----

    def load_for_connection(self, connection_name: str) -> list[QueryHistoryEntry]:
        self._maybe_migrate()
        conn_dir = self._connection_dir(connection_name)
        return self._entries_from_files(
            self._all_files(connection_name),
            fallback_connection=self._fallback_connection_from_dir(conn_dir),
        )

    def load_all(self) -> list[QueryHistoryEntry]:
        self._maybe_migrate()
        if not self._base_dir.is_dir():
            return []
        entries: list[QueryHistoryEntry] = []
        for conn_dir in self._base_dir.iterdir():
            if not conn_dir.is_dir():
                continue
            fallback_connection = self._fallback_connection_from_dir(conn_dir)
            files: list[Path] = list(conn_dir.glob("*.sql"))
            for db_dir in conn_dir.iterdir():
                if db_dir.is_dir():
                    files.extend(db_dir.glob("*.sql"))
            entries.extend(
                self._entries_from_files(
                    [p for p in files if p.is_file()],
                    fallback_connection=fallback_connection,
                )
            )
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def save_query(self, connection_name: str, query: str, database: str = "") -> None:
        self._maybe_migrate()
        query_stripped = query.strip()
        if not query_stripped:
            return
        entry = QueryHistoryEntry(
            query=query_stripped,
            timestamp=datetime.now().isoformat(),
            connection_name=connection_name,
            database=database,
        )
        self._write_entry(entry)
        self._evict(connection_name)

    def delete_entry(self, connection_name: str, timestamp: str) -> bool:
        self._maybe_migrate()
        filename_prefix = _timestamp_to_filename(timestamp)
        for path in self._all_files(connection_name):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            entry = _parse_entry(
                text,
                fallback_connection=connection_name,
                fallback_database="",
                fallback_timestamp=_filename_to_timestamp(path.stem.rsplit("_", 1)[0]),
            )
            if entry is None:
                continue
            if entry.timestamp == timestamp or path.name.startswith(filename_prefix):
                try:
                    path.unlink()
                    return True
                except OSError:
                    return False
        return False

    def clear_for_connection(self, connection_name: str) -> int:
        self._maybe_migrate()
        files = self._all_files(connection_name)
        count = 0
        for path in files:
            try:
                path.unlink()
                count += 1
            except OSError:
                pass
        # Drop now-empty database subdirs and the connection dir itself.
        conn_dir = self._connection_dir(connection_name)
        if conn_dir.is_dir():
            for child in conn_dir.iterdir():
                if child.is_dir():
                    try:
                        child.rmdir()
                    except OSError:
                        pass
            try:
                conn_dir.rmdir()
            except OSError:
                pass
        return count
