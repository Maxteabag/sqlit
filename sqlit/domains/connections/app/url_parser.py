"""Connection URL parsing for sqlit.

Parses database connection URLs into ConnectionConfig objects.
Supports standard URL formats like:
    postgresql://user:password@host:port/database?sslmode=require
    mysql://user:password@host/database
    sqlite:///path/to/database.db
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.catalog import (
    get_db_type_for_scheme,
    get_provider_schema,
    get_url_scheme_map,
)
from sqlit.domains.connections.providers.config_service import normalize_connection_config
from sqlit.domains.connections.providers.metadata import get_display_name


class UrlParseStrategy(Protocol):
    def parse(
        self,
        parsed: ParseResult,
        db_type: str,
        name: str,
        original_url: str,
        extra_options: dict[str, str],
    ) -> ConnectionConfig:
        """Parse a URL into a ConnectionConfig."""
        ...


class ServerBasedUrlStrategy:
    def parse(
        self,
        parsed: ParseResult,
        db_type: str,
        name: str,
        original_url: str,
        extra_options: dict[str, str],
    ) -> ConnectionConfig:
        return _parse_server_based_url(parsed, db_type, name, original_url, extra_options)


class FileBasedUrlStrategy:
    def parse(
        self,
        parsed: ParseResult,
        db_type: str,
        name: str,
        original_url: str,
        extra_options: dict[str, str],
    ) -> ConnectionConfig:
        return _parse_file_based_url(parsed, db_type, name, original_url, extra_options)


FILE_BASED_STRATEGY = FileBasedUrlStrategy()
SERVER_BASED_STRATEGY = ServerBasedUrlStrategy()


def is_connection_url(arg: str) -> bool:
    """Check if an argument looks like a connection URL.

    Args:
        arg: Command-line argument to check

    Returns:
        True if the argument appears to be a connection URL
    """
    if "://" not in arg:
        return False
    scheme = arg.split("://")[0].lower()
    return get_db_type_for_scheme(scheme) is not None


def detect_db_type_from_scheme(scheme: str) -> str | None:
    """Map a URL scheme to a database type.

    Args:
        scheme: URL scheme (e.g., 'postgresql', 'postgres', 'mysql')

    Returns:
        Database type string, or None if scheme is not recognized
    """
    return get_db_type_for_scheme(scheme)


def parse_connection_url(
    url: str,
    *,
    name: str | None = None,
) -> ConnectionConfig:
    """Parse a connection URL into a ConnectionConfig.

    Args:
        url: Database connection URL
        name: Optional connection name (required for saved connections)

    Returns:
        ConnectionConfig populated from the URL

    Raises:
        ValueError: If the URL scheme is not supported or URL is malformed
    """
    parsed = urlparse(url)

    db_type = detect_db_type_from_scheme(parsed.scheme)
    if not db_type:
        supported = ", ".join(sorted(set(get_url_scheme_map().values())))
        raise ValueError(
            f"Unsupported URL scheme: '{parsed.scheme}'. "
            f"Supported databases: {supported}"
        )

    # Parse query string into extra_options
    extra_options: dict[str, str] = {}
    if parsed.query:
        qs = parse_qs(parsed.query)
        # parse_qs returns lists; take first value for each key
        extra_options = {k: v[0] for k, v in qs.items() if v}

    # Generate default name if not provided
    config_name = name or f"Temp {get_display_name(db_type)}"

    schema = get_provider_schema(db_type)
    strategy: UrlParseStrategy = SERVER_BASED_STRATEGY
    if schema.is_file_based:
        strategy = FILE_BASED_STRATEGY

    return normalize_connection_config(
        strategy.parse(parsed, db_type, config_name, url, extra_options)
    )


def _parse_file_based_url(
    parsed: ParseResult,
    db_type: str,
    name: str,
    original_url: str,
    extra_options: dict[str, str],
) -> ConnectionConfig:
    """Parse a file-based database URL (SQLite, DuckDB).

    Supports formats:
        sqlite:///absolute/path/to/db.sqlite
        sqlite://./relative/path/to/db.sqlite
        sqlite:///path/to/db.sqlite
    """
    # The path includes everything after scheme://
    # For sqlite:///path/to/db, parsed.path is /path/to/db
    # For sqlite://./path/to/db, parsed.netloc is '.' and path is /path/to/db
    file_path = parsed.path

    # Handle relative paths: sqlite://./path or sqlite://../path
    if parsed.netloc in (".", ".."):
        file_path = parsed.netloc + file_path
    elif parsed.netloc:
        # sqlite://hostname/path - treat hostname as start of path
        file_path = parsed.netloc + file_path

    if not file_path:
        raise ValueError(f"No file path specified in {db_type} URL")

    return ConnectionConfig.from_dict(
        {
            "name": name,
            "db_type": db_type,
            "endpoint": {"kind": "file", "path": file_path},
            "connection_url": original_url,
            "extra_options": extra_options,
        }
    )


def _parse_server_based_url(
    parsed: ParseResult,
    db_type: str,
    name: str,
    original_url: str,
    extra_options: dict[str, str],
) -> ConnectionConfig:
    """Parse a server-based database URL (PostgreSQL, MySQL, etc.)."""
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError(f"No host specified in URL: {original_url}")

    # Extract and decode credentials
    username = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else None

    # Port: use from URL or leave empty (ConnectionConfig will apply default)
    port = str(parsed.port) if parsed.port else ""

    # Database: strip leading slash from path
    database = parsed.path.lstrip("/") if parsed.path else ""

    return ConnectionConfig.from_dict(
        {
            "name": name,
            "db_type": db_type,
            "endpoint": {
                "kind": "tcp",
                "host": hostname,
                "port": port,
                "database": database,
                "username": username,
                "password": password,
            },
            "connection_url": original_url,
            "extra_options": extra_options,
        }
    )
