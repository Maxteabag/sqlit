#!/usr/bin/env python3
"""sqlit - A terminal UI for SQL databases."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sqlit.domains.connections.cli.helpers import add_schema_arguments, build_connection_config_from_args
from sqlit.domains.connections.domain.config import AuthType, ConnectionConfig, DatabaseType
from sqlit.domains.connections.providers.catalog import get_provider_schema, get_supported_db_types
from sqlit.shared.app.runtime import MockConfig, RuntimeConfig
from sqlit.shared.app.services import build_app_services


def _get_schema_value_flags() -> set[str]:
    from sqlit.domains.connections.providers.catalog import iter_provider_schemas

    flags: set[str] = set()
    for schema in iter_provider_schemas():
        for field in schema.fields:
            if field.name == "ssh_enabled":
                continue
            flags.add(f"--{field.name.replace('_', '-')}")
            if field.name == "server":
                flags.add("--host")
    return flags


def _extract_connection_url(argv: list[str]) -> tuple[str | None, list[str]]:
    """Extract a connection URL from argv if present.

    Looks for the first non-flag argument that looks like a connection URL.
    Returns (url, remaining_argv) where url is None if not found.
    """
    from sqlit.domains.connections.app.url_parser import is_connection_url

    subcommands = {"connections", "connection", "connect", "query"}
    result_argv = []
    url = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        # Skip the program name
        if i == 0:
            result_argv.append(arg)
            i += 1
            continue

        # If it's a flag, include it (and its value if applicable)
        if arg.startswith("-"):
            result_argv.append(arg)
            # Check if this flag takes a value (simple heuristic: next arg doesn't start with -)
            if i + 1 < len(argv) and not argv[i + 1].startswith("-") and "=" not in arg:
                # Flags that take values
                value_flags = {
                    "--mock",
                    "--db-type",
                    "--name",
                    "--settings",
                    "--mock-missing-drivers",
                    "--mock-install",
                    "--mock-pipx",
                    "--mock-query-delay",
                    "--demo-rows",
                    "--max-rows",
                }
                value_flags |= _get_schema_value_flags()
                if arg in value_flags:
                    i += 1
                    result_argv.append(argv[i])
            i += 1
            continue

        # If it's a subcommand, include it and everything after
        if arg in subcommands:
            result_argv.extend(argv[i:])
            break

        # If it looks like a URL, extract it
        if url is None and is_connection_url(arg):
            url = arg
            i += 1
            continue

        # Otherwise include it
        result_argv.append(arg)
        i += 1

    return url, result_argv


def _parse_missing_drivers(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _build_runtime(args: argparse.Namespace, startup_mark: float) -> RuntimeConfig:
    settings_path = Path(args.settings).expanduser() if args.settings else None
    max_rows = args.max_rows if args.max_rows and args.max_rows > 0 else None
    mock_install = args.mock_install if args.mock_install != "real" else None
    mock_pipx = args.mock_pipx if args.mock_pipx != "auto" else None

    mock_config = MockConfig(
        enabled=bool(args.mock),
        missing_drivers=_parse_missing_drivers(args.mock_missing_drivers),
        install_result=mock_install,
        pipx_mode=mock_pipx,
        query_delay=args.mock_query_delay or 0.0,
        demo_rows=args.demo_rows or 0,
        demo_long_text=bool(args.demo_long_text),
        cloud=bool(args.mock_cloud),
    )

    return RuntimeConfig(
        settings_path=settings_path,
        max_rows=max_rows,
        debug_mode=bool(args.debug),
        debug_idle_scheduler=bool(args.debug_idle_scheduler),
        profile_startup=bool(args.profile_startup),
        startup_mark=startup_mark if args.profile_startup or args.debug else None,
        mock=mock_config,
    )


def main() -> int:
    """Entry point for the CLI."""
    # Extract connection URL before argparse (URLs conflict with subcommands)
    connection_url, filtered_argv = _extract_connection_url(sys.argv)

    parser = argparse.ArgumentParser(
        prog="sqlit",
        description="A terminal UI for SQL databases",
        epilog="Connect via URL: sqlit mysql://user:pass@host/db, sqlit sqlite:///path/to/db.sqlite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        choices=["auto", "pipx", "pip", "unknown"],
        default="auto",
        help="Mock installation method for install hints: pipx, pip, or unknown (can't auto-install).",
    )
    parser.add_argument(
        "--mock-query-delay",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Add artificial delay to mock query execution (e.g. 3.0 for 3 seconds).",
    )
    parser.add_argument(
        "--demo-rows",
        type=int,
        default=0,
        metavar="COUNT",
        help="Generate fake data with COUNT rows for mock queries (requires --mock, uses Faker if installed).",
    )
    parser.add_argument(
        "--demo-long-text",
        action="store_true",
        help="Generate data with long varchar columns to test truncation (use with --mock).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        metavar="COUNT",
        help="Maximum rows to fetch and render (default: 10000). Use for performance testing.",
    )
    parser.add_argument(
        "--mock-cloud",
        action="store_true",
        help="Use mock cloud provider data (Azure, AWS, GCP) for demos/screenshots.",
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
    parser.add_argument(
        "--debug-idle-scheduler",
        action="store_true",
        help="Show idle scheduler status in the status bar.",
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
    add_parser.add_argument(
        "--url",
        metavar="URL",
        help="Connection URL (e.g., postgresql://user:pass@host:5432/db). Requires --name.",
    )
    add_parser.add_argument(
        "--name",
        "-n",
        dest="url_name",
        help="Connection name (required when using --url)",
    )
    add_provider_parsers = add_parser.add_subparsers(dest="provider", metavar="PROVIDER")
    for db_type in get_supported_db_types():
        schema = get_provider_schema(db_type)
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
        schema = get_provider_schema(db_type)
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

    # Docker discovery command
    docker_parser = subparsers.add_parser("docker", help="Docker container discovery")
    docker_subparsers = docker_parser.add_subparsers(dest="docker_command", help="Docker commands")
    docker_subparsers.add_parser("list", help="List detected database containers")

    startup_mark = time.perf_counter()
    args = parser.parse_args(filtered_argv[1:])  # Skip program name
    runtime = _build_runtime(args, startup_mark)
    services = build_app_services(runtime)
    if args.command is None:
        from sqlit.domains.shell.app.main import SSMSTUI
        from sqlit.domains.connections.app.url_parser import parse_connection_url

        if args.mock:
            from sqlit.domains.connections.app.mocks import get_mock_profile, list_mock_profiles

            mock_profile = get_mock_profile(args.mock)
            if mock_profile is None:
                print(f"Unknown mock profile: {args.mock}")
                print(f"Available profiles: {', '.join(list_mock_profiles())}")
                return 1
            services.apply_mock_profile(mock_profile)

        temp_config = None
        try:
            # Check for connection URL first (extracted before argparse)
            if connection_url:
                temp_config = parse_connection_url(
                    connection_url,
                    name=getattr(args, "name", None),
                )
            else:
                temp_config = _build_temp_connection(args)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        app = SSMSTUI(services=services, startup_connection=temp_config)
        app.run()
        return 0

    from sqlit.domains.connections.cli.commands import (
        cmd_connection_create,
        cmd_connection_delete,
        cmd_connection_edit,
        cmd_connection_list,
    )
    from sqlit.domains.query.cli.commands import cmd_query

    if args.command == "connect":
        from sqlit.domains.shell.app.main import SSMSTUI

        provider_db_type = getattr(args, "provider", None)
        if not isinstance(provider_db_type, str):
            connect_parser.print_help()
            return 1

        if args.mock:
            from sqlit.domains.connections.app.mocks import get_mock_profile, list_mock_profiles

            mock_profile = get_mock_profile(args.mock)
            if mock_profile is None:
                print(f"Unknown mock profile: {args.mock}")
                print(f"Available profiles: {', '.join(list_mock_profiles())}")
                return 1
            services.apply_mock_profile(mock_profile)

        schema = get_provider_schema(provider_db_type)
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

        app = SSMSTUI(services=services, startup_connection=temp_config)
        app.run()
        return 0

    if args.command in {"connections", "connection"}:
        if args.conn_command == "list":
            return cmd_connection_list(args, services=services)
        elif args.conn_command in {"add", "create"}:
            return cmd_connection_create(args, services=services)
        elif args.conn_command == "edit":
            return cmd_connection_edit(args, services=services)
        elif args.conn_command == "delete":
            return cmd_connection_delete(args, services=services)
        else:
            conn_parser.print_help()
            return 1

    if args.command == "query":
        return cmd_query(args, services=services)

    if args.command == "docker":
        from sqlit.domains.connections.cli.commands import cmd_docker_list

        if args.docker_command == "list":
            return cmd_docker_list(args, services=services)
        else:
            docker_parser.print_help()
            return 1

    parser.print_help()
    return 1


def _build_temp_connection(args: argparse.Namespace) -> ConnectionConfig | None:
    """Build a temporary connection config from CLI args, if provided."""
    db_type = getattr(args, "db_type", None)
    file_path = getattr(args, "file_path", None)
    if not db_type:
        if file_path:
            raise ValueError("--db-type is required when using --file-path")
        if any(getattr(args, name, None) for name in ("server", "host", "database")):
            raise ValueError("--db-type is required for temporary connections")
        return None

    try:
        DatabaseType(db_type)
    except ValueError:
        raise ValueError(f"Invalid database type '{db_type}'")

    schema = get_provider_schema(db_type)
    return build_connection_config_from_args(
        schema,
        args,
        name=getattr(args, "name", None),
        default_name=f"Temp {schema.display_name}",
        strict=True,
    )


if __name__ == "__main__":
    sys.exit(main())
