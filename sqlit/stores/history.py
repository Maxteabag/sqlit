"""History store for managing query history per connection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .base import CONFIG_DIR, JSONFileStore


@dataclass
class QueryHistoryEntry:
    """A query history entry."""

    query: str
    timestamp: str  # ISO format
    connection_name: str
    is_starred: bool = False  # Computed at load time, not persisted
    is_starred_only: bool = False  # True if only in starred store, not in history

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "connection_name": self.connection_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> QueryHistoryEntry:
        """Create from dictionary."""
        return cls(
            query=data["query"],
            timestamp=data["timestamp"],
            connection_name=data["connection_name"],
        )


class HistoryStore(JSONFileStore):
    """Store for managing query history.

    History is stored as a JSON array in ~/.sqlit/query_history.json
    Each entry includes query text, timestamp, and connection name.
    """

    MAX_ENTRIES_PER_CONNECTION = 100
    _instance: HistoryStore | None = None

    def __init__(self) -> None:
        super().__init__(CONFIG_DIR / "query_history.json")

    @classmethod
    def get_instance(cls) -> HistoryStore:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_all_entries(self) -> list[dict]:
        """Load all history entries as raw dictionaries."""
        data = self._read_json()
        return data if isinstance(data, list) else []

    def load_for_connection(self, connection_name: str) -> list[QueryHistoryEntry]:
        """Load query history for a specific connection.

        Args:
            connection_name: Name of connection to load history for.

        Returns:
            List of QueryHistoryEntry objects, sorted by most recent first.
        """
        all_entries = self._load_all_entries()
        try:
            entries = [
                QueryHistoryEntry.from_dict(entry)
                for entry in all_entries
                if entry.get("connection_name") == connection_name
            ]
            entries.sort(key=lambda e: e.timestamp, reverse=True)
            return entries
        except (KeyError, TypeError):
            return []

    def save_query(self, connection_name: str, query: str) -> None:
        """Save a query to history.

        If the exact query already exists for this connection, updates its timestamp.
        Otherwise adds a new entry. Keeps only MAX_ENTRIES_PER_CONNECTION entries.

        Args:
            connection_name: Name of the connection.
            query: SQL query text.
        """
        all_entries = self._load_all_entries()
        query_stripped = query.strip()
        now = datetime.now().isoformat()

        # Check if query already exists
        for entry in all_entries:
            if entry.get("connection_name") == connection_name and entry.get("query", "").strip() == query_stripped:
                entry["timestamp"] = now
                break
        else:
            # Add new entry
            new_entry = QueryHistoryEntry(
                query=query_stripped,
                timestamp=now,
                connection_name=connection_name,
            )
            all_entries.append(new_entry.to_dict())

        # Limit entries per connection
        connection_entries = [e for e in all_entries if e.get("connection_name") == connection_name]
        other_entries = [e for e in all_entries if e.get("connection_name") != connection_name]

        connection_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        connection_entries = connection_entries[: self.MAX_ENTRIES_PER_CONNECTION]

        self._write_json(other_entries + connection_entries)

    def delete_entry(self, connection_name: str, timestamp: str) -> bool:
        """Delete a specific history entry.

        Args:
            connection_name: Name of the connection.
            timestamp: ISO timestamp of the entry to delete.

        Returns:
            True if an entry was deleted, False otherwise.
        """
        all_entries = self._load_all_entries()
        original_count = len(all_entries)

        all_entries = [
            e
            for e in all_entries
            if not (e.get("timestamp") == timestamp and e.get("connection_name") == connection_name)
        ]

        if len(all_entries) < original_count:
            self._write_json(all_entries)
            return True
        return False

    def clear_for_connection(self, connection_name: str) -> int:
        """Clear all history for a connection.

        Args:
            connection_name: Name of the connection.

        Returns:
            Number of entries deleted.
        """
        all_entries = self._load_all_entries()
        original_count = len(all_entries)

        all_entries = [e for e in all_entries if e.get("connection_name") != connection_name]

        deleted = original_count - len(all_entries)
        if deleted > 0:
            self._write_json(all_entries)
        return deleted


# Module-level convenience functions for backward compatibility
_store = HistoryStore()


def load_query_history(connection_name: str) -> list[QueryHistoryEntry]:
    """Load query history for a specific connection, sorted by most recent first."""
    return _store.load_for_connection(connection_name)


def save_query_to_history(connection_name: str, query: str) -> None:
    """Save a query to history for a connection."""
    _store.save_query(connection_name, query)


def delete_query_from_history(connection_name: str, timestamp: str) -> bool:
    """Delete a specific query from history by connection name and timestamp."""
    return _store.delete_entry(connection_name, timestamp)
