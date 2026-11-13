"""Server-wide autocomplete indexing is skipped on servers with many databases."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlit.domains.query.ui.mixins.autocomplete_schema import (
    MAX_SERVER_WIDE_INDEX_DATABASES,
    AutocompleteSchemaMixin,
)


class _Host(AutocompleteSchemaMixin):
    def __init__(self) -> None:
        self.current_provider = SimpleNamespace(
            capabilities=SimpleNamespace(supports_stored_procedures=False),
            schema_inspector=object(),
        )
        self.current_connection = object()
        self.notifications: list[tuple[str, str]] = []
        self.loaded: list[tuple[str, Any]] = []
        self.spinner_stopped = False

    def notify(self, message: str, severity: str = "information") -> None:
        self.notifications.append((message, severity))

    def _stop_schema_spinner(self) -> None:
        self.spinner_stopped = True

    def _load_tables_job(self, database: Any) -> None:
        self.loaded.append(("tables", database))

    def _load_views_job(self, database: Any) -> None:
        self.loaded.append(("views", database))

    def _schema_job_complete(self) -> None:
        pass


def test_many_databases_skip_indexing_and_warn() -> None:
    host = _Host()
    databases = [f"db{i}" for i in range(MAX_SERVER_WIDE_INDEX_DATABASES + 1)]

    host._on_databases_loaded(databases)

    assert host.loaded == []
    assert host.spinner_stopped
    assert len(host.notifications) == 1
    message, severity = host.notifications[0]
    assert severity == "warning"
    assert str(len(databases)) in message


def test_few_databases_are_indexed() -> None:
    host = _Host()
    databases = [f"db{i}" for i in range(MAX_SERVER_WIDE_INDEX_DATABASES)]

    host._on_databases_loaded(databases)

    assert ("tables", "db0") in host.loaded
    assert host.notifications == []


def test_selected_database_is_always_indexed() -> None:
    host = _Host()

    host._on_databases_loaded(["AppDb"])

    assert host.loaded == [("tables", "AppDb"), ("views", "AppDb")]
