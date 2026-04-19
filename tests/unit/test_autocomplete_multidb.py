"""Regression tests for MySQL autocomplete in multi-database scenarios (#151).

Two narrow bugs are covered:

1. Qualified identifiers for databases without schemas (MySQL/MariaDB) used
   to render as `db`.``.`table` — an empty-backticked middle segment. The
   qualifying logic is now a Dialect method so each adapter owns its own
   composition rule.

2. Autocomplete returned a permanent "Loading..." sentinel whenever the
   table reference in the query didn't resolve to anything in the schema
   cache (e.g. the user typed `SELECT * FROM shop.cu`: `shop` was treated
   as an alias and the loader spun forever for an unknown key).
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------------
# Bug 1: Dialect.qualified_name
# --------------------------------------------------------------------------


def _get_dialect(db_type: str):
    from sqlit.domains.connections.providers.catalog import get_provider

    return get_provider(db_type).dialect


def test_mysql_qualified_name_is_two_part() -> None:
    """MySQL has no schema-within-database; the qualified form is
    `db`.`table`, NOT `db`.``.`table`."""
    dialect = _get_dialect("mysql")
    assert dialect.qualified_name("shop", "", "customers") == "`shop`.`customers`"


def test_mariadb_qualified_name_is_two_part() -> None:
    dialect = _get_dialect("mariadb")
    assert dialect.qualified_name("shop", "", "customers") == "`shop`.`customers`"


def test_postgresql_qualified_name_uses_schema_only() -> None:
    """PostgreSQL databases are isolated; only schema.table makes sense
    for cross-reference within the connected database."""
    dialect = _get_dialect("postgresql")
    # No db segment expected when schema is present.
    assert dialect.qualified_name(None, "public", "users") == '"public"."users"'


def test_sqlserver_qualified_name_is_three_part() -> None:
    """SQL Server explicitly uses [db].[schema].[table]."""
    dialect = _get_dialect("mssql")
    assert dialect.qualified_name("app", "dbo", "Users") == "[app].[dbo].[Users]"


def test_qualified_name_skips_empty_segments_everywhere() -> None:
    """Regardless of dialect, empty db/schema segments must be omitted,
    never rendered as empty-quoted placeholders."""
    for db_type in ("mysql", "postgresql", "mssql", "sqlite"):
        dialect = _get_dialect(db_type)
        # bare table name: single quoted segment, no dot joins.
        bare = dialect.qualified_name(None, None, "t")
        assert "t" in bare, f"{db_type}: {bare}"
        assert "." not in bare, f"{db_type} unexpected joins: {bare}"
        # empty schema segment must not produce empty quote pair like `` or "" or [].
        out = dialect.qualified_name(None, "", "t")
        for marker in ("``", '""', "[]"):
            assert marker not in out, f"{db_type} emitted empty-quoted segment: {out}"


def test_qualified_name_escapes_embedded_quote_chars() -> None:
    """Each dialect must escape its own quote char, not leak raw input."""
    for db_type, payload, expected_substr in [
        ("mysql", "app`evil", "app``evil"),
        ("postgresql", 'app"evil', 'app""evil'),
        ("mssql", "app]evil", "app]]evil"),
    ]:
        dialect = _get_dialect(db_type)
        out = dialect.qualified_name(None, None, payload)
        assert expected_substr in out, f"{db_type}: {out}"


# --------------------------------------------------------------------------
# Bug 2: stuck Loading... for unknown table references
# --------------------------------------------------------------------------


class _SchemaHost:
    """Minimal stand-in for AutocompleteMixinHost — just enough to drive
    `_get_autocomplete_suggestions`."""

    def __init__(self, tables, metadata, columns=None, loading=None):
        self._schema_cache = {
            "tables": tables,
            "views": [],
            "columns": columns or {},
            "procedures": [],
        }
        self._table_metadata = metadata
        self._columns_loading = loading or set()
        self.load_calls: list[str] = []

    def _load_columns_for_table(self, table_name: str) -> None:
        self.load_calls.append(table_name)

    def _build_alias_map(self, text: str) -> dict:
        return {}


def test_unknown_table_ref_does_not_stick_on_loading() -> None:
    """`SELECT * FROM shop.cu` parses `shop` as an ALIAS_COLUMN scope. It
    isn't a real table. Before the fix the completion engine called
    _load_columns_for_table('shop') and returned `Loading...`; the loader
    skipped unknown keys silently, so the sentinel never cleared."""
    from sqlit.domains.query.ui.mixins.autocomplete_suggestions import AutocompleteSuggestionsMixin

    host = _SchemaHost(
        tables=["customers", "orders", "products"],
        metadata={
            "customers": ("", "customers", "shop"),
            "shop.customers": ("", "customers", "shop"),
            "orders": ("", "orders", "shop"),
            "products": ("", "products", "shop"),
        },
    )

    get_suggestions = AutocompleteSuggestionsMixin._get_autocomplete_suggestions.__get__(host)

    text = "SELECT * FROM shop.cu"
    result = get_suggestions(text, len(text))

    assert result != ["Loading..."], (
        "unknown table key must not pin Loading... — loader never clears it"
    )
    assert "shop" not in host.load_calls


def test_known_table_ref_still_triggers_loading_on_first_call() -> None:
    """Sanity check: the fix must not regress legit lazy loading."""
    from sqlit.domains.query.ui.mixins.autocomplete_suggestions import AutocompleteSuggestionsMixin

    host = _SchemaHost(
        tables=["customers"],
        metadata={"customers": ("", "customers", None)},
        columns={},
    )
    get_suggestions = AutocompleteSuggestionsMixin._get_autocomplete_suggestions.__get__(host)

    text = "SELECT * FROM customers WHERE em"
    result = get_suggestions(text, len(text))

    assert result == ["Loading..."]
    assert "customers" in host.load_calls
