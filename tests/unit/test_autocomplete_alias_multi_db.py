"""Tests for autocomplete alias handling in multi-database schemas."""

from __future__ import annotations

from sqlit.domains.query.ui.mixins.autocomplete_suggestions import AutocompleteSuggestionsMixin


class _DummyAutocompleteHost(AutocompleteSuggestionsMixin):
    def __init__(self, schema_cache: dict) -> None:
        self._schema_cache = schema_cache
        self._columns_loading = set()
        self.loaded: list[str] = []

    def _load_columns_for_table(self, table_name: str, *, allow_retry: bool = True) -> None:  # noqa: ARG002
        self.loaded.append(table_name)


def test_alias_column_loads_table_when_tables_are_qualified() -> None:
    """Alias-based column lookup should resolve to the table name, not the alias."""
    host = _DummyAutocompleteHost(
        {
            "tables": ["db.test_users"],
            "views": [],
            "columns": {},
            "procedures": [],
        }
    )
    host._table_metadata = {"test_users": ("", "test_users", "db")}

    sql = "SELECT * FROM test_users u WHERE u."
    suggestions = host._get_autocomplete_suggestions(sql, len(sql))

    assert suggestions == ["Loading..."]
    assert host.loaded == ["test_users"]
