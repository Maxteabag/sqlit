#!/usr/bin/env python3
"""sqlit - A terminal UI for SQL databases."""

from __future__ import annotations

import argparse
import os
import sys
import time

from .cli_helpers import add_schema_arguments, build_connection_config_from_args
from .config import AuthType, ConnectionConfig, DatabaseType
from .db.providers import get_connection_schema, get_supported_db_types


def main() -> int:
    """Entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="sqlit",
        description="A terminal UI for SQL databases",
    )

    parser.add_argument(
        "--mock",
        metavar="PROFILE",
        help="Run with mock data (profiles: sqlite-demo, empty, multi-db)",
    )
    parser.add_argument(
        "--db-type",
        choices=[t.value for t in DatabaseType],
        help="Temporary connection database type (auto-connects in UI)",
    )
    parser.add_argument("--name", help="Temporary connection name (default: Temp <DB>)")
    parser.add_argument("--server", help="Temporary connection server/host")
    parser.add_argument("--host", help="Alias for --server")
    parser.add_argument("--port", help="Temporary connection port")
    parser.add_argument("--database", help="Temporary connection database name")
    parser.add_argument("--username", help="Temporary connection username")
    parser.add_argument("--password", help="Temporary connection password")
    parser.add_argument("--file-path", help="Temporary connection file path (SQLite/DuckDB)")
    parser.add_argument(
        "--auth-type",
        choices=[t.value for t in AuthType],
        help="Temporary connection auth type (SQL Server only)",
    )
    parser.add_argument("--supabase-region", help="Supabase region (temporary connection)")
    parser.add_argument("--supabase-project-id", help="Supabase project id (temporary connection)")
    parser.add_argument(
        "--settings",
        metavar="PATH",
        help="Path to settings JSON file (overrides ~/.sqlit/settings.json)",
    )
    parser.add_argument(
        "--mock-missing-drivers",
        metavar="DB_TYPES",
        help="Force missing Python drivers for the given db types (comma-separated), e.g. postgresql,mysql",
    )
    parser.add_argument(
        "--mock-install",
        choices=["real", "success", "fail"],
        default="real",
        help="Mock the driver install result in the UI (default: real).",
    )
    parser.add_argument(
        "--mock-pipx",
        choices=["auto", "pipx", "pip"],
        default="auto",
        help="Mock whether sqlit is running under pipx for install hints (default: auto).",
    )
    parser.add_argument(
        "--profile-startup",
        action="store_true",
        help="Log startup timing diagnostics to stderr.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show startup timing in the status bar.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    conn_parser = subparsers.add_parser(
        "connections",
        help="Manage saved connections",
        aliases=["connection"],
    )
    conn_subparsers = conn_parser.add_subparsers(dest="conn_command", help="Connection commands")

    conn_subparsers.add_parser("list", help="List all saved connections")

    add_parser = conn_subparsers.add_parser(
        "add",
        help="Add a new connection",
        aliases=["create"],
    )
    add_provider_parsers = add_parser.add_subparsers(dest="provider", metavar="PROVIDER")
    for db_type in get_supported_db_types():
        schema = get_connection_schema(db_type)
        provider_parser = add_provider_parsers.add_parser(
            db_type,
            help=f"{schema.display_name} options",
            description=f"{schema.display_name} connection options",
        )
        add_schema_arguments(provider_parser, schema, include_name=True, name_required=True)

    edit_parser = conn_subparsers.add_parser("edit", help="Edit an existing connection")
    edit_parser.add_argument("connection_name", help="Name of connection to edit")
    edit_parser.add_argument("--name", "-n", help="New connection name")
    edit_parser.add_argument("--server", "-s", help="Server address")
    edit_parser.add_argument("--host", help="Alias for --server (e.g. Cloudflare D1 Account ID)")
    edit_parser.add_argument("--port", "-P", help="Port")
    edit_parser.add_argument("--database", "-d", help="Database name")
    edit_parser.add_argument("--username", "-u", help="Username")
    edit_parser.add_argument("--password", "-p", help="Password")
    edit_parser.add_argument(
        "--auth-type",
        "-a",
        choices=[t.value for t in AuthType],
        help="Authentication type (SQL Server only)",
    )
    edit_parser.add_argument("--file-path", help="Database file path (SQLite only)")

    delete_parser = conn_subparsers.add_parser("delete", help="Delete a connection")
    delete_parser.add_argument("connection_name", help="Name of connection to delete")

    connect_parser = subparsers.add_parser("connect", help="Temporary connection (not saved)")
    connect_provider_parsers = connect_parser.add_subparsers(dest="provider", metavar="PROVIDER")
    for db_type in get_supported_db_types():
        schema = get_connection_schema(db_type)
        provider_parser = connect_provider_parsers.add_parser(
            db_type,
            help=f"{schema.display_name} options",
            description=f"{schema.display_name} connection options",
        )
        add_schema_arguments(provider_parser, schema, include_name=True, name_required=False)

    query_parser = subparsers.add_parser("query", help="Execute a SQL query")
    query_parser.add_argument("--connection", "-c", required=True, help="Connection name to use")
    query_parser.add_argument("--database", "-d", help="Database to query (overrides connection default)")
    query_parser.add_argument("--query", "-q", help="SQL query to execute")
    query_parser.add_argument("--file", "-f", help="SQL file to execute")
    query_parser.add_argument(
        "--format",
        "-o",
        default="table",
        choices=["table", "csv", "json"],
        help="Output format (default: table)",
    )
    query_parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=1000,
        help="Maximum rows to fetch (default: 1000, use 0 for unlimited)",
    )

    startup_mark = time.perf_counter()
    args = parser.parse_args()
    if args.settings:
        os.environ["SQLIT_SETTINGS_PATH"] = str(args.settings)
    if args.mock_missing_drivers:
        os.environ["SQLIT_MOCK_MISSING_DRIVERS"] = str(args.mock_missing_drivers)
    if args.mock_install and args.mock_install != "real":
        os.environ["SQLIT_MOCK_INSTALL_RESULT"] = str(args.mock_install)
    else:
        os.environ.pop("SQLIT_MOCK_INSTALL_RESULT", None)
    if args.mock_pipx and args.mock_pipx != "auto":
        os.environ["SQLIT_MOCK_PIPX"] = str(args.mock_pipx)
    else:
        os.environ.pop("SQLIT_MOCK_PIPX", None)
    if args.profile_startup:
        os.environ["SQLIT_PROFILE_STARTUP"] = "1"
    else:
        os.environ.pop("SQLIT_PROFILE_STARTUP", None)
    if args.debug:
        os.environ["SQLIT_DEBUG"] = "1"
    else:
        os.environ.pop("SQLIT_DEBUG", None)
    if args.profile_startup or args.debug:
        os.environ["SQLIT_STARTUP_MARK"] = str(startup_mark)
    else:
        os.environ.pop("SQLIT_STARTUP_MARK", None)
    if args.command is None:
        from .app import SSMSTUI

        mock_profile = None
        if args.mock:
            from .mocks import get_mock_profile, list_mock_profiles

            mock_profile = get_mock_profile(args.mock)
            if mock_profile is None:
                print(f"Unknown mock profile: {args.mock}")
                print(f"Available profiles: {', '.join(list_mock_profiles())}")
                return 1

        temp_config = None
        try:
            temp_config = _build_temp_connection(args)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        app = SSMSTUI(mock_profile=mock_profile, startup_connection=temp_config)
        app.run()
        return 0

    from .commands import (
        cmd_connection_create,
        cmd_connection_delete,
        cmd_connection_edit,
        cmd_connection_list,
        cmd_query,
    )

    if args.command == "connect":
        from .app import SSMSTUI

        db_type = getattr(args, "provider", None)
        if not db_type:
            connect_parser.print_help()
            return 1

        mock_profile = None
        if args.mock:
            from .mocks import get_mock_profile, list_mock_profiles

            mock_profile = get_mock_profile(args.mock)
            if mock_profile is None:
                print(f"Unknown mock profile: {args.mock}")
                print(f"Available profiles: {', '.join(list_mock_profiles())}")
                return 1

        schema = get_connection_schema(db_type)
        try:
            temp_config = build_connection_config_from_args(
                schema,
                args,
                name=getattr(args, "name", None),
                default_name=f"Temp {schema.display_name}",
                strict=True,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        app = SSMSTUI(mock_profile=mock_profile, startup_connection=temp_config)
        app.run()
        return 0

    if args.command in {"connections", "connection"}:
        if args.conn_command == "list":
            return cmd_connection_list(args)
        elif args.conn_command in {"add", "create"}:
            return cmd_connection_create(args)
        elif args.conn_command == "edit":
            return cmd_connection_edit(args)
        elif args.conn_command == "delete":
            return cmd_connection_delete(args)
        else:
            conn_parser.print_help()
            return 1

    if args.command == "query":
        return cmd_query(args)

    parser.print_help()
    return 1


def _build_temp_connection(args: argparse.Namespace) -> ConnectionConfig | None:
    """Build a temporary connection config from CLI args, if provided."""
    db_type = getattr(args, "db_type", None)
    file_path = getattr(args, "file_path", None)
    if not db_type and file_path:
        db_type = "sqlite"
        setattr(args, "db_type", db_type)
    if not db_type:
        if any(getattr(args, name, None) for name in ("file_path", "server", "host", "database")):
            raise ValueError("--db-type is required for temporary connections")
        return None

    try:
        DatabaseType(db_type)
    except ValueError:
        raise ValueError(f"Invalid database type '{db_type}'")

    schema = get_connection_schema(db_type)
    return build_connection_config_from_args(
        schema,
        args,
        name=getattr(args, "name", None),
        default_name=f"Temp {schema.display_name}",
        strict=True,
    )


if __name__ == "__main__":
    sys.exit(main())
