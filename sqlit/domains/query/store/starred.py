"""Starred queries store for managing favorite queries per connection."""

from __future__ import annotations

from sqlit.shared.core.store import CONFIG_DIR, JSONFileStore


class StarredStore(JSONFileStore):
    """Store for managing starred queries.

    Starred queries are stored as a JSON object in ~/.sqlit/starred_queries.json
    Structure: { "connection_name": ["query1", "query2", ...] }

    Starred queries persist independently of history - they are never auto-deleted
    even when the history limit is reached or queries are manually deleted from history.
    """

    _instance: StarredStore | None = None

    def __init__(self) -> None:
        super().__init__(CONFIG_DIR / "starred_queries.json")

    @classmethod
    def get_instance(cls) -> StarredStore:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_all(self) -> dict[str, list[str]]:
        """Load all starred queries as raw dictionary."""
        data = self._read_json()
        return data if isinstance(data, dict) else {}

    def load_all(self) -> dict[str, set[str]]:
        """Load starred queries for all connections."""
        all_starred = self._load_all()
        result: dict[str, set[str]] = {}
        for connection_name, queries in all_starred.items():
            if not isinstance(queries, list):
                continue
            result[connection_name] = {q.strip() for q in queries}
        return result

    def load_for_connection(self, connection_name: str) -> set[str]:
        """Load starred queries for a specific connection.

        Args:
            connection_name: Name of connection to load starred queries for.

        Returns:
            Set of starred query strings (normalized/stripped).
        """
        all_starred = self._load_all()
        queries = all_starred.get(connection_name, [])
        return {q.strip() for q in queries}

    def is_starred(self, connection_name: str, query: str) -> bool:
        """Check if a query is starred.

        Args:
            connection_name: Name of the connection.
            query: SQL query text.

        Returns:
            True if the query is starred, False otherwise.
        """
        starred = self.load_for_connection(connection_name)
        return query.strip() in starred

    def star_query(self, connection_name: str, query: str) -> bool:
        """Star a query.

        Args:
            connection_name: Name of the connection.
            query: SQL query text to star.

        Returns:
            True if newly starred, False if already starred.
        """
        all_starred = self._load_all()
        query_stripped = query.strip()

        if connection_name not in all_starred:
            all_starred[connection_name] = []

        if query_stripped in all_starred[connection_name]:
            return False

        all_starred[connection_name].append(query_stripped)
        self._write_json(all_starred)
        return True

    def unstar_query(self, connection_name: str, query: str) -> bool:
        """Unstar a query.

        Args:
            connection_name: Name of the connection.
            query: SQL query text to unstar.

        Returns:
            True if unstarred, False if wasn't starred.
        """
        all_starred = self._load_all()
        query_stripped = query.strip()

        if connection_name not in all_starred:
            return False

        if query_stripped not in all_starred[connection_name]:
            return False

        all_starred[connection_name].remove(query_stripped)

        # Clean up empty connection entries
        if not all_starred[connection_name]:
            del all_starred[connection_name]

        self._write_json(all_starred)
        return True

    def toggle_star(self, connection_name: str, query: str) -> bool:
        """Toggle star status for a query.

        Args:
            connection_name: Name of the connection.
            query: SQL query text.

        Returns:
            True if now starred, False if now unstarred.
        """
        if self.is_starred(connection_name, query):
            self.unstar_query(connection_name, query)
            return False
        else:
            self.star_query(connection_name, query)
            return True

    def clear_for_connection(self, connection_name: str) -> int:
        """Clear all starred queries for a connection.

        Args:
            connection_name: Name of the connection.

        Returns:
            Number of queries unstarred.
        """
        all_starred = self._load_all()

        if connection_name not in all_starred:
            return 0

        count = len(all_starred[connection_name])
        del all_starred[connection_name]
        self._write_json(all_starred)
        return count
