"""Suggestion helpers for SQL autocomplete."""

from __future__ import annotations

import re
from typing import cast

from sqlit.domains.query.completion import (
    SuggestionType,
    extract_table_refs,
    get_completions,
    get_context,
)
from sqlit.shared.ui.protocols import AutocompleteMixinHost


class AutocompleteSuggestionsMixin:
    """Mixin providing SQL autocomplete suggestion logic."""

    def _format_autocomplete_identifier(self: AutocompleteMixinHost, name: str) -> str:
        provider = getattr(self, "current_provider", None)
        formatter = getattr(getattr(provider, "dialect", None), "format_autocomplete_identifier", None)
        if callable(formatter):
            return cast(str, formatter(name))
        return name

    def _format_autocomplete_name(self: AutocompleteMixinHost, name: str) -> str:
        if any(marker in name for marker in ('"', "`", "[", "]")):
            return name
        table_metadata = getattr(self, "_table_metadata", {}) or {}
        metadata = table_metadata.get(name.lower())
        if metadata:
            schema_name, object_name, _database = metadata
            provider = getattr(self, "current_provider", None)
            default_schema = getattr(getattr(provider, "capabilities", None), "default_schema", None)
            formatted_object = AutocompleteSuggestionsMixin._format_autocomplete_identifier(self, object_name)
            if schema_name and schema_name != default_schema and name.lower().startswith(f"{schema_name.lower()}."):
                formatted_schema = AutocompleteSuggestionsMixin._format_autocomplete_identifier(self, schema_name)
                return f"{formatted_schema}.{formatted_object}"
            return formatted_object
        if "." not in name:
            return AutocompleteSuggestionsMixin._format_autocomplete_identifier(self, name)
        return ".".join(
            AutocompleteSuggestionsMixin._format_autocomplete_identifier(self, part)
            for part in name.split(".")
        )

    def _format_autocomplete_columns(
        self: AutocompleteMixinHost,
        columns: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        return {
            table_key: [
                AutocompleteSuggestionsMixin._format_autocomplete_identifier(self, column)
                for column in column_names
            ]
            for table_key, column_names in columns.items()
        }

    def _get_current_word(self: AutocompleteMixinHost, text: str, cursor_pos: int) -> str:
        """Get the word currently being typed at cursor position."""
        before_cursor = text[:cursor_pos]

        # Handle table.column case - get just the part after dot
        if "." in before_cursor:
            dot_match = re.search(r"\.(\w*)$", before_cursor)
            if dot_match:
                return dot_match.group(1)

        # Get word before cursor
        match = re.search(r"(\w*)$", before_cursor)
        if match:
            return match.group(1)
        return ""

    def _build_alias_map(self: AutocompleteMixinHost, text: str) -> dict[str, str]:
        """Build a map of alias -> table name from the SQL text."""
        table_refs = extract_table_refs(text)
        known_tables = set(t.lower() for t in self._schema_cache.get("tables", []))
        known_tables.update(t.lower() for t in self._schema_cache.get("views", []))
        table_metadata = getattr(self, "_table_metadata", {}) or {}
        known_metadata = {key.lower() for key in table_metadata.keys()}

        alias_map: dict[str, str] = {}

        def is_known(name: str) -> bool:
            lowered = name.lower()
            return lowered in known_tables or lowered in known_metadata

        for ref in table_refs:
            if not ref.alias:
                continue

            # Prefer schema-qualified name when present (db.table or schema.table).
            if ref.schema:
                qualified = f"{ref.schema}.{ref.name}"
                if is_known(qualified):
                    alias_map[ref.alias.lower()] = qualified
                    continue

            if is_known(ref.name):
                alias_map[ref.alias.lower()] = ref.name
        return alias_map

    def _get_autocomplete_suggestions(self: AutocompleteMixinHost, text: str, cursor_pos: int) -> list[str]:
        """Get autocomplete suggestions using the SQL completion engine."""
        # Build schema data for get_completions
        raw_tables = self._schema_cache.get("tables", []) + self._schema_cache.get("views", [])
        raw_columns = self._schema_cache.get("columns", {})
        tables = [
            AutocompleteSuggestionsMixin._format_autocomplete_name(self, table)
            for table in raw_tables
        ]
        columns = AutocompleteSuggestionsMixin._format_autocomplete_columns(self, raw_columns)
        procedures = self._schema_cache.get("procedures", [])

        # First check if we need to lazy-load columns before calling get_completions
        suggestions = get_context(text, cursor_pos)
        if suggestions:
            alias_map = self._build_alias_map(text)
            table_refs = extract_table_refs(text)
            loading: set[str] = getattr(self, "_columns_loading", set())
            table_metadata = getattr(self, "_table_metadata", {}) or {}

            def needs_column_load(key: str) -> bool:
                """Return True only if the key names a known table that hasn't
                been loaded yet. Returning Loading... for an unknown key would
                wedge forever because the loader skips unknown tables silently.
                """
                if key in raw_columns:
                    return False
                if key not in table_metadata:
                    return False
                return True

            for suggestion in suggestions:
                if suggestion.type == SuggestionType.COLUMN:
                    # Check if any tables need column loading
                    for ref in table_refs:
                        table_key = ref.name.lower()
                        if needs_column_load(table_key) and table_key not in loading:
                            self._load_columns_for_table(table_key)
                            return ["Loading..."]
                        elif table_key in loading:
                            return ["Loading..."]

                elif suggestion.type == SuggestionType.ALIAS_COLUMN:
                    scope = suggestion.table_scope
                    if scope:
                        scope_lower = scope.lower()
                        table_key = alias_map.get(scope_lower, scope_lower).lower()

                        if needs_column_load(table_key) and table_key not in loading:
                            self._load_columns_for_table(table_key)
                            return ["Loading..."]
                        elif table_key in loading:
                            return ["Loading..."]

        # Now call get_completions with all available data
        results = get_completions(
            text,
            cursor_pos,
            tables,
            columns,
            procedures,
            include_keywords=True,
            include_functions=True,
        )

        return results
