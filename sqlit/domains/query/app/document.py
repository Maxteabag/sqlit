"""State for a query document loaded from the saved-query library."""

from __future__ import annotations

from dataclasses import dataclass

from sqlit.domains.query.store.saved_queries import FileFingerprint


@dataclass
class QueryDocument:
    """The file association and last saved contents of the query editor."""

    connection_name: str | None = None
    relative_path: str | None = None
    saved_text: str = ""
    fingerprint: FileFingerprint | None = None

    def is_dirty(self, current_text: str) -> bool:
        return current_text != self.saved_text

    @property
    def name(self) -> str:
        return self.relative_path or "Untitled"
