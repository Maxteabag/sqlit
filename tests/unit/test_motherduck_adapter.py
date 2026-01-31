"""Unit tests for MotherDuck adapter."""

from __future__ import annotations

from sqlit.domains.connections.domain.config import ConnectionConfig, FileEndpoint


def test_motherduck_provider_registered():
    """Test that MotherDuck provider is properly registered."""
    from sqlit.domains.connections.providers.catalog import get_supported_db_types

    db_types = get_supported_db_types()
    assert "motherduck" in db_types


def test_motherduck_provider_metadata():
    """Test MotherDuck provider metadata."""
    from sqlit.domains.connections.providers.catalog import get_provider

    provider = get_provider("motherduck")
    assert provider.metadata.display_name == "MotherDuck"
    assert provider.metadata.is_file_based is True
    assert provider.metadata.supports_ssh is False
    assert provider.metadata.requires_auth is True
    assert "md" in provider.metadata.url_schemes
    assert "motherduck" in provider.metadata.url_schemes


def test_motherduck_database_type_enum():
    """Test MotherDuck is in DatabaseType enum."""
    from sqlit.domains.connections.domain.config import DatabaseType

    assert DatabaseType.MOTHERDUCK.value == "motherduck"


def test_motherduck_url_parsing():
    """Test MotherDuck URL parsing."""
    from sqlit.domains.connections.app.url_parser import parse_connection_url

    config = parse_connection_url("motherduck:///my_database?motherduck_token=abc123")

    assert config.db_type == "motherduck"
    assert config.file_path == "/my_database"
    assert config.extra_options.get("motherduck_token") == "abc123"


def test_motherduck_md_scheme_url_parsing():
    """Test MotherDuck md:// URL parsing."""
    from sqlit.domains.connections.app.url_parser import parse_connection_url

    config = parse_connection_url("md:///prod_db?motherduck_token=xyz789")

    assert config.db_type == "motherduck"
    assert config.file_path == "/prod_db"
    assert config.extra_options.get("motherduck_token") == "xyz789"
