"""Connection URL parsing for sqlit.

Parses database connection URLs into ConnectionConfig objects.
Supports standard URL formats like:
    postgresql://user:password@host:port/database?sslmode=require
    mysql://user:password@host/database
    sqlite:///path/to/database.db
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from .config import ConnectionConfig
from .db.providers import get_default_port, get_display_name

# Map URL schemes to database types
SCHEME_TO_DB_TYPE: dict[str, str] = {
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "mysql": "mysql",
    "mariadb": "mariadb",
    "mssql": "mssql",
    "sqlserver": "mssql",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
    "cockroachdb": "cockroachdb",
    "cockroach": "cockroachdb",
    "oracle": "oracle",
    "libsql": "turso",
}

# Database types that use file paths instead of server connections
FILE_BASED_SCHEMES = {"sqlite", "duckdb"}


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
    return scheme in SCHEME_TO_DB_TYPE


def detect_db_type_from_scheme(scheme: str) -> str | None:
    """Map a URL scheme to a database type.

    Args:
        scheme: URL scheme (e.g., 'postgresql', 'postgres', 'mysql')

    Returns:
        Database type string, or None if scheme is not recognized
    """
    return SCHEME_TO_DB_TYPE.get(scheme.lower())


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
        supported = ", ".join(sorted(set(SCHEME_TO_DB_TYPE.values())))
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

    # Handle file-based databases (SQLite, DuckDB)
    if db_type in FILE_BASED_SCHEMES:
        return _parse_file_based_url(parsed, db_type, config_name, url, extra_options)

    # Handle server-based databases
    return _parse_server_based_url(parsed, db_type, config_name, url, extra_options)


def _parse_file_based_url(
    parsed: "urlparse",
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

    return ConnectionConfig(
        name=name,
        db_type=db_type,
        file_path=file_path,
        connection_url=original_url,
        extra_options=extra_options,
    )


def _parse_server_based_url(
    parsed: "urlparse",
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

    return ConnectionConfig(
        name=name,
        db_type=db_type,
        server=hostname,
        port=port,
        database=database,
        username=username,
        password=password,
        connection_url=original_url,
        extra_options=extra_options,
    )
