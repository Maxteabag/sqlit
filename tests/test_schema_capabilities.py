"""Tests for schema capability functions."""

from sqlit.db.schema import (
    get_default_port,
    get_display_name,
    get_supported_db_types,
    has_advanced_auth,
    is_file_based,
    supports_ssh,
)


class TestIsFileBased:
    def test_unknown_type_returns_false(self):
        assert is_file_based("nonexistent") is False


class TestHasAdvancedAuth:
    def test_unknown_type_returns_false(self):
        assert has_advanced_auth("nonexistent") is False


class TestSupportsSSH:
    def test_unknown_type_returns_false(self):
        assert supports_ssh("nonexistent") is False


class TestGetDefaultPort:
    def test_unknown_type_returns_fallback(self):
        assert get_default_port("nonexistent") == "1433"


class TestGetDisplayName:
    def test_unknown_type_returns_input(self):
        assert get_display_name("nonexistent") == "nonexistent"


class TestCatalogConsistency:
    def test_provider_schema_ids_match_keys(self):
        from sqlit.db.providers import PROVIDERS, get_connection_schema

        for db_type, spec in PROVIDERS.items():
            schema = get_connection_schema(db_type)
            assert schema.db_type == db_type

    def test_database_type_enum_matches_schema(self):
        from sqlit.config import DatabaseType

        assert {t.value for t in DatabaseType} == set(get_supported_db_types())

    def test_adapter_factory_matches_schema(self):
        from sqlit.db.adapters import get_supported_adapter_db_types

        assert set(get_supported_adapter_db_types()) == set(get_supported_db_types())

    def test_display_names_match_schema(self):
        from sqlit.db.providers import get_connection_schema

        for db_type in get_supported_db_types():
            schema = get_connection_schema(db_type)
            assert schema.display_name == get_display_name(db_type)
