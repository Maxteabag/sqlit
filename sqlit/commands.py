"""CLI command handlers for sqlit."""

from __future__ import annotations

import csv
import getpass
import json
import sys
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .config import (
    AUTH_TYPE_LABELS,
    AuthType,
    ConnectionConfig,
    DatabaseType,
    get_database_type_labels,
    load_connections,
    save_connections,
)
from .db.providers import get_default_port, has_advanced_auth, is_file_based
from .services import ConnectionSession, QueryResult, QueryService
from .services.credentials import (
    ALLOW_PLAINTEXT_CREDENTIALS_SETTING,
    is_keyring_usable,
    reset_credentials_service,
)

if TYPE_CHECKING:
    pass


def _maybe_prompt_plaintext_credentials() -> bool:
    """Ensure plaintext credential storage preference is set when keyring isn't usable.

    Returns True if plaintext storage is allowed; False otherwise.
    """
    from .config import load_settings, save_settings

    if is_keyring_usable():
        return False

    settings = load_settings()
    existing = settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING)
    if isinstance(existing, bool):
        if existing:
            reset_credentials_service()
        return bool(existing)

    if not sys.stdin.isatty():
        return False

    answer = input("Keyring isn't available. Save passwords as plaintext in ~/.sqlit/? [y/N]: ").strip().lower()
    allow = answer in {"y", "yes"}
    settings[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = allow
    save_settings(settings)
    if allow:
        reset_credentials_service()
    return allow


def _clear_passwords_if_not_persisted(config: ConnectionConfig) -> None:
    config.password = ""
    config.ssh_password = ""


def _prompt_for_password(config: ConnectionConfig) -> ConnectionConfig:
    """Prompt for passwords if they are empty.

    Uses getpass for secure input that doesn't appear in bash history.
    Returns a new config with passwords filled in (original is not modified).
    """
    new_config = config

    if config.ssh_enabled and config.ssh_auth_type == "password" and not config.ssh_password:
        ssh_password = getpass.getpass(f"SSH password for '{config.name}': ")
        new_config = replace(new_config, ssh_password=ssh_password)

    if not is_file_based(config.db_type) and not config.password:
        db_password = getpass.getpass(f"Password for '{config.name}': ")
        new_config = replace(new_config, password=db_password)

    return new_config


def cmd_connection_list(args: Any) -> int:
    """List all saved connections."""
    connections = load_connections()
    if not connections:
        print("No saved connections.")
        return 0

    print(f"{'Name':<20} {'Type':<10} {'Connection Info':<40} {'Auth Type':<25}")
    print("-" * 95)
    labels = get_database_type_labels()
    for conn in connections:
        db_type_label = labels.get(conn.get_db_type(), conn.db_type)
        if is_file_based(conn.db_type):
            conn_info = conn.file_path[:38] + ".." if len(conn.file_path) > 40 else conn.file_path
            auth_label = "N/A"
        elif has_advanced_auth(conn.db_type):
            conn_info = f"{conn.server}@{conn.database}" if conn.database else conn.server
            conn_info = conn_info[:38] + ".." if len(conn_info) > 40 else conn_info
            auth_label = AUTH_TYPE_LABELS.get(conn.get_auth_type(), conn.auth_type)
        else:
            # Server-based databases with simple auth
            conn_info = f"{conn.server}@{conn.database}" if conn.database else conn.server
            conn_info = conn_info[:38] + ".." if len(conn_info) > 40 else conn_info
            auth_label = f"User: {conn.username}" if conn.username else "N/A"
        print(f"{conn.name:<20} {db_type_label:<10} {conn_info:<40} {auth_label:<25}")
    return 0


def cmd_connection_create(args: Any) -> int:
    """Create a new connection."""
    connections = load_connections()

    if any(c.name == args.name for c in connections):
        print(f"Error: Connection '{args.name}' already exists. Use 'edit' to modify it.")
        return 1

    db_type = getattr(args, "db_type", "mssql") or "mssql"
    try:
        DatabaseType(db_type)
    except ValueError:
        valid_types = ", ".join(t.value for t in DatabaseType)
        print(f"Error: Invalid database type '{db_type}'. Valid types: {valid_types}")
        return 1

    if is_file_based(db_type):
        file_path = getattr(args, "file_path", None)
        if not file_path:
            print(f"Error: --file-path is required for {db_type.upper()} connections.")
            return 1

        config = ConnectionConfig(
            name=args.name,
            db_type=db_type,
            file_path=file_path,
        )
    elif has_advanced_auth(db_type):
        # SQL Server connection (has Windows/Azure AD auth)
        server = getattr(args, "server", None) or getattr(args, "host", None)
        if not server:
            print("Error: --server is required for SQL Server connections.")
            return 1

        auth_type_str = getattr(args, "auth_type", "sql") or "sql"
        try:
            auth_type = AuthType(auth_type_str)
        except ValueError:
            valid_types = ", ".join(t.value for t in AuthType)
            print(f"Error: Invalid auth type '{auth_type_str}'. Valid types: {valid_types}")
            return 1

        config = ConnectionConfig(
            name=args.name,
            db_type=db_type,
            server=server,
            port=args.port or get_default_port(db_type),
            database=args.database or "",
            username=args.username or "",
            password=args.password or "",
            auth_type=auth_type.value,
            trusted_connection=(auth_type == AuthType.WINDOWS),
            ssh_enabled=getattr(args, "ssh_enabled", False) or False,
            ssh_host=getattr(args, "ssh_host", "") or "",
            ssh_port=getattr(args, "ssh_port", "22") or "22",
            ssh_username=getattr(args, "ssh_username", "") or "",
            ssh_auth_type=getattr(args, "ssh_auth_type", "key") or "key",
            ssh_key_path=getattr(args, "ssh_key_path", "") or "",
            ssh_password=getattr(args, "ssh_password", "") or "",
        )
    else:
        server = getattr(args, "server", None) or getattr(args, "host", None)
        if not server:
            db_label = get_database_type_labels().get(DatabaseType(db_type), db_type.upper())
            print(f"Error: --server is required for {db_label} connections.")
            return 1

        config = ConnectionConfig(
            name=args.name,
            db_type=db_type,
            server=server,
            port=args.port or get_default_port(db_type),
            database=args.database or "",
            username=args.username or "",
            password=args.password or "",
            ssh_enabled=getattr(args, "ssh_enabled", False) or False,
            ssh_host=getattr(args, "ssh_host", "") or "",
            ssh_port=getattr(args, "ssh_port", "22") or "22",
            ssh_username=getattr(args, "ssh_username", "") or "",
            ssh_auth_type=getattr(args, "ssh_auth_type", "key") or "key",
            ssh_key_path=getattr(args, "ssh_key_path", "") or "",
            ssh_password=getattr(args, "ssh_password", "") or "",
        )

    connections.append(config)
    if (config.password or config.ssh_password) and not is_keyring_usable():
        if not _maybe_prompt_plaintext_credentials():
            _clear_passwords_if_not_persisted(config)
    save_connections(connections)
    print(f"Connection '{args.name}' created successfully.")
    return 0


def cmd_connection_edit(args: Any) -> int:
    """Edit an existing connection."""
    connections = load_connections()

    conn_idx = None
    for i, c in enumerate(connections):
        if c.name == args.connection_name:
            conn_idx = i
            break

    if conn_idx is None:
        print(f"Error: Connection '{args.connection_name}' not found.")
        return 1

    conn = connections[conn_idx]

    if args.name:
        if args.name != conn.name and any(c.name == args.name for c in connections):
            print(f"Error: Connection '{args.name}' already exists.")
            return 1
        conn.name = args.name

    server = getattr(args, "server", None) or getattr(args, "host", None)
    if server:
        conn.server = server
    if args.port:
        conn.port = args.port
    if args.database:
        conn.database = args.database
    if args.auth_type:
        try:
            auth_type = AuthType(args.auth_type)
            conn.auth_type = auth_type.value
            conn.trusted_connection = auth_type == AuthType.WINDOWS
        except ValueError:
            valid_types = ", ".join(t.value for t in AuthType)
            print(f"Error: Invalid auth type '{args.auth_type}'. Valid types: {valid_types}")
            return 1
    if args.username is not None:
        conn.username = args.username
    if args.password is not None:
        conn.password = args.password

    file_path = getattr(args, "file_path", None)
    if file_path is not None:
        conn.file_path = file_path

    if (conn.password or conn.ssh_password) and not is_keyring_usable():
        if not _maybe_prompt_plaintext_credentials():
            _clear_passwords_if_not_persisted(conn)

    save_connections(connections)
    print(f"Connection '{conn.name}' updated successfully.")
    return 0


def cmd_connection_delete(args: Any) -> int:
    """Delete a connection."""
    connections = load_connections()

    conn_idx = None
    for i, c in enumerate(connections):
        if c.name == args.connection_name:
            conn_idx = i
            break

    if conn_idx is None:
        print(f"Error: Connection '{args.connection_name}' not found.")
        return 1

    deleted = connections.pop(conn_idx)
    save_connections(connections)
    print(f"Connection '{deleted.name}' deleted successfully.")
    return 0


def _stream_csv_output(cursor: Any, columns: list[str]) -> int:
    """Stream CSV output from cursor using fetchmany."""
    writer = csv.writer(sys.stdout)
    writer.writerow(columns)
    row_count = 0
    batch_size = 1000
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            writer.writerow(str(val) if val is not None else "" for val in row)
            row_count += 1
    return row_count


def _stream_json_output(cursor: Any, columns: list[str]) -> int:
    """Stream JSON output from cursor using fetchmany (JSON array format)."""
    print("[")
    first = True
    row_count = 0
    batch_size = 1000
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            if not first:
                print(",")
            first = False
            obj = dict(zip(columns, [val if val is not None else None for val in row]))
            print(json.dumps(obj, default=str), end="")
            row_count += 1
    print("\n]")
    return row_count


def _output_table(columns: list[str], rows: list[tuple], truncated: bool) -> None:
    """Output query results in table format with optimized width calculation."""
    MAX_COL_WIDTH = 50

    # Only scan first 100 rows for performance
    col_widths = [min(len(col), MAX_COL_WIDTH) for col in columns]
    for row in rows[:100]:
        for i, val in enumerate(row):
            val_str = str(val) if val is not None else "NULL"
            col_widths[i] = min(MAX_COL_WIDTH, max(col_widths[i], len(val_str)))

    header_parts = []
    for i, col in enumerate(columns):
        col_display = col[: col_widths[i]] if len(col) > col_widths[i] else col
        header_parts.append(col_display.ljust(col_widths[i]))
    header = " | ".join(header_parts)
    print(header)
    print("-" * len(header))

    for row in rows:
        row_parts = []
        for i, val in enumerate(row):
            val_str = str(val) if val is not None else "NULL"
            if len(val_str) > col_widths[i]:
                val_str = val_str[: col_widths[i] - 2] + ".."
            row_parts.append(val_str.ljust(col_widths[i]))
        print(" | ".join(row_parts))

    if truncated:
        print(f"\n({len(rows)} rows shown, results truncated)")
    else:
        print(f"\n({len(rows)} row(s) returned)")


def cmd_query(
    args: Any,
    *,
    session_factory: Callable[[ConnectionConfig], ConnectionSession] | None = None,
    query_service: QueryService | None = None,
) -> int:
    """Execute a SQL query against a connection.

    Args:
        args: Parsed command-line arguments.
        session_factory: Optional factory for creating ConnectionSession.
            Defaults to ConnectionSession.create. Useful for testing.
        query_service: Optional QueryService instance.
            Defaults to a new QueryService(). Useful for testing.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    connections = load_connections()

    config = None
    for c in connections:
        if c.name == args.connection:
            config = c
            break

    if config is None:
        print(f"Error: Connection '{args.connection}' not found.")
        return 1

    if args.database and config.db_type == "mssql":
        config = replace(config, database=args.database)

    config = _prompt_for_password(config)

    if args.query:
        query = args.query
    elif args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                query = f.read()
        except FileNotFoundError:
            print(f"Error: File '{args.file}' not found.")
            return 1
        except OSError as e:
            print(f"Error reading file: {e}")
            return 1
    else:
        print("Error: Either --query or --file must be provided.")
        return 1

    max_rows = args.limit if args.limit > 0 else None

    create_session = session_factory or ConnectionSession.create
    service = query_service or QueryService()

    try:
        with create_session(config) as session:
            from .services.query import is_select_query

            has_cursor = hasattr(session.connection, "cursor") and callable(getattr(session.connection, "cursor", None))

            if max_rows is None and args.format in ("csv", "json") and is_select_query(query) and has_cursor:
                cursor = session.connection.cursor()
                cursor.execute(query)

                if not cursor.description:
                    print("Query executed successfully (no results)")
                    return 0

                columns = [col[0] for col in cursor.description]

                if args.format == "csv":
                    row_count = _stream_csv_output(cursor, columns)
                else:
                    row_count = _stream_json_output(cursor, columns)

                service._save_to_history(config.name, query)
                print(f"\n({row_count} row(s) returned)", file=sys.stderr)
                return 0

            result = service.execute(
                connection=session.connection,
                adapter=session.adapter,
                query=query,
                config=config,
                max_rows=max_rows,
                save_to_history=True,
            )

            if isinstance(result, QueryResult):
                columns = result.columns
                rows = result.rows

                if args.format == "csv":
                    writer = csv.writer(sys.stdout)
                    writer.writerow(columns)
                    for row in rows:
                        writer.writerow(str(val) if val is not None else "" for val in row)
                    if result.truncated:
                        print(f"\n({len(rows)} rows shown, results truncated)", file=sys.stderr)
                    else:
                        print(f"\n({len(rows)} row(s) returned)", file=sys.stderr)
                elif args.format == "json":
                    json_result = [
                        dict(zip(columns, [val if val is not None else None for val in row])) for row in rows
                    ]
                    print(json.dumps(json_result, indent=2, default=str))
                    if result.truncated:
                        print(f"\n({len(rows)} rows shown, results truncated)", file=sys.stderr)
                    else:
                        print(f"\n({len(rows)} row(s) returned)", file=sys.stderr)
                else:
                    _output_table(columns, rows, result.truncated)
            else:
                print(f"Query executed successfully. Rows affected: {result.rows_affected}")

            return 0

    except ImportError as e:
        print(f"Error: Required module not installed: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
