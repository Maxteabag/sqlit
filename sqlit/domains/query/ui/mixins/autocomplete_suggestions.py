"""Suggestion helpers for SQL autocomplete."""

from __future__ import annotations

import re

from sqlit.domains.query.completion import (
    SuggestionType,
    extract_table_refs,
    get_completions,
    get_context,
)
from sqlit.shared.ui.protocols import AutocompleteMixinHost


class AutocompleteSuggestionsMixin:
    """Mixin providing SQL autocomplete suggestion logic."""

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

        alias_map: dict[str, str] = {}
        for ref in table_refs:
            if ref.alias and ref.name.lower() in known_tables:
                alias_map[ref.alias.lower()] = ref.name
        return alias_map

    def _get_autocomplete_suggestions(self: AutocompleteMixinHost, text: str, cursor_pos: int) -> list[str]:
        """Get autocomplete suggestions using the SQL completion engine."""
        # Build schema data for get_completions
        tables = self._schema_cache.get("tables", []) + self._schema_cache.get("views", [])
        columns = self._schema_cache.get("columns", {})
        procedures = self._schema_cache.get("procedures", [])

        # First check if we need to lazy-load columns before calling get_completions
        suggestions = get_context(text, cursor_pos)
        if suggestions:
            alias_map = self._build_alias_map(text)
            table_refs = extract_table_refs(text)
            loading: set[str] = getattr(self, "_columns_loading", set())

            for suggestion in suggestions:
                if suggestion.type == SuggestionType.COLUMN:
                    # Check if any tables need column loading
                    for ref in table_refs:
                        table_key = ref.name.lower()
                        if table_key not in columns and table_key not in loading:
                            self._load_columns_for_table(table_key)
                            return ["Loading..."]
                        elif table_key in loading:
                            return ["Loading..."]

                elif suggestion.type == SuggestionType.ALIAS_COLUMN:
                    scope = suggestion.table_scope
                    if scope:
                        scope_lower = scope.lower()
                        table_key = alias_map.get(scope_lower, scope_lower)

                        if table_key not in columns and table_key not in loading:
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
