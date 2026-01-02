"""Protocol for database metadata helpers used by mixins."""

from __future__ import annotations

from typing import Protocol


class MetadataHelpersProtocol(Protocol):
    def _get_effective_database(self) -> str | None:
        ...

    def _get_metadata_db_arg(self, database: str | None) -> str | None:
        ...
