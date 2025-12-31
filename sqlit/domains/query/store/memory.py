"""In-memory query stores for tests and mock mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InMemoryQueryHistoryEntry:
    query: str
    timestamp: str
    connection_name: str

    def to_dict(self) -> dict[str, str]:
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "connection_name": self.connection_name,
        }


class InMemoryHistoryStore:
    """In-memory history store."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def load_for_connection(self, connection_name: str) -> list[dict[str, Any]]:
        return [
            entry for entry in self._entries
            if entry.get("connection_name") == connection_name
        ]

    def save_query(self, connection_name: str, query: str) -> None:
        self._entries.append({
            "query": query.strip(),
            "timestamp": "",
            "connection_name": connection_name,
        })

    def delete_entry(self, connection_name: str, timestamp: str) -> bool:
        return False

    def clear_for_connection(self, connection_name: str) -> int:
        before = len(self._entries)
        self._entries = [
            entry for entry in self._entries
            if entry.get("connection_name") != connection_name
        ]
        return before - len(self._entries)


class InMemoryStarredStore:
    """In-memory starred queries store."""

    def __init__(self) -> None:
        self._starred: dict[str, set[str]] = {}

    def load_for_connection(self, connection_name: str) -> set[str]:
        return set(self._starred.get(connection_name, set()))

    def is_starred(self, connection_name: str, query: str) -> bool:
        return query.strip() in self._starred.get(connection_name, set())

    def star_query(self, connection_name: str, query: str) -> bool:
        queries = self._starred.setdefault(connection_name, set())
        query_stripped = query.strip()
        if query_stripped in queries:
            return False
        queries.add(query_stripped)
        return True

    def unstar_query(self, connection_name: str, query: str) -> bool:
        queries = self._starred.get(connection_name)
        if not queries:
            return False
        query_stripped = query.strip()
        if query_stripped not in queries:
            return False
        queries.remove(query_stripped)
        if not queries:
            self._starred.pop(connection_name, None)
        return True

    def toggle_star(self, connection_name: str, query: str) -> bool:
        if self.is_starred(connection_name, query):
            self.unstar_query(connection_name, query)
            return False
        self.star_query(connection_name, query)
        return True
