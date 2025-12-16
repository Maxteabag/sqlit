#!/usr/bin/env python3
"""sqlit - A terminal UI for SQL databases."""

from __future__ import annotations

import argparse
import os
import sys

from .config import AuthType, DatabaseType


def main() -> int:
    """Entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="sqlit",
        description="A terminal UI for SQL databases",
    )

    # Global options for TUI mode
    parser.add_argument(
        "--mock",
        metavar="PROFILE",
        help="Run with mock data (profiles: sqlite-demo, empty, multi-db)",
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

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Connection commands
    conn_parser = subparsers.add_parser("connection", help="Manage connections")
    conn_subparsers = conn_parser.add_subparsers(dest="conn_command", help="Connection commands")

    # connection list
    conn_subparsers.add_parser("list", help="List all saved connections")

    # connection create
    create_parser = conn_subparsers.add_parser("create", help="Create a new connection")
    create_parser.add_argument("--name", "-n", required=True, help="Connection name")
    create_parser.add_argument(
        "--db-type",
        "-t",
        default="mssql",
        choices=[t.value for t in DatabaseType],
        help="Database type (default: mssql)",
    )
    # Server-based database options (SQL Server, PostgreSQL, MySQL)
    create_parser.add_argument("--server", "-s", help="Server address")
    create_parser.add_argument("--host", help="Alias for --server (e.g. Cloudflare D1 Account ID)")
    create_parser.add_argument("--port", "-P", help="Port (default: provider default)")
    create_parser.add_argument("--database", "-d", default="", help="Database name (empty = browse all)")
    create_parser.add_argument("--username", "-u", help="Username")
    create_parser.add_argument("--password", "-p", help="Password")
    # SQL Server specific options
    create_parser.add_argument(
        "--auth-type",
        "-a",
        default="sql",
        choices=[t.value for t in AuthType],
        help="Authentication type (SQL Server only, default: sql)",
    )
    # SQLite options
    create_parser.add_argument("--file-path", help="Database file path (SQLite only)")
    # SSH tunnel options
    create_parser.add_argument("--ssh-enabled", action="store_true", help="Enable SSH tunnel")
    create_parser.add_argument("--ssh-host", help="SSH server hostname")
    create_parser.add_argument("--ssh-port", default="22", help="SSH server port (default: 22)")
    create_parser.add_argument("--ssh-username", help="SSH username")
    create_parser.add_argument("--ssh-auth-type", default="key", choices=["key", "password"], help="SSH auth type")
    create_parser.add_argument("--ssh-key-path", help="SSH private key path")
    create_parser.add_argument("--ssh-password", help="SSH password")

    # connection edit
    edit_parser = conn_subparsers.add_parser("edit", help="Edit an existing connection")
    edit_parser.add_argument("connection_name", help="Name of connection to edit")
    edit_parser.add_argument("--name", "-n", help="New connection name")
    # Server-based database options (SQL Server, PostgreSQL, MySQL)
    edit_parser.add_argument("--server", "-s", help="Server address")
    edit_parser.add_argument("--host", help="Alias for --server (e.g. Cloudflare D1 Account ID)")
    edit_parser.add_argument("--port", "-P", help="Port")
    edit_parser.add_argument("--database", "-d", help="Database name")
    edit_parser.add_argument("--username", "-u", help="Username")
    edit_parser.add_argument("--password", "-p", help="Password")
    # SQL Server specific options
    edit_parser.add_argument(
        "--auth-type",
        "-a",
        choices=[t.value for t in AuthType],
        help="Authentication type (SQL Server only)",
    )
    # SQLite options
    edit_parser.add_argument("--file-path", help="Database file path (SQLite only)")

    # connection delete
    delete_parser = conn_subparsers.add_parser("delete", help="Delete a connection")
    delete_parser.add_argument("connection_name", help="Name of connection to delete")

    # query command
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

    args = parser.parse_args()
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

    # No command = launch TUI
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

        app = SSMSTUI(mock_profile=mock_profile)
        app.run()
        return 0

    # Import commands lazily to speed up --help
    from .commands import (
        cmd_connection_create,
        cmd_connection_delete,
        cmd_connection_edit,
        cmd_connection_list,
        cmd_query,
    )

    # Handle connection commands
    if args.command == "connection":
        if args.conn_command == "list":
            return cmd_connection_list(args)
        elif args.conn_command == "create":
            return cmd_connection_create(args)
        elif args.conn_command == "edit":
            return cmd_connection_edit(args)
        elif args.conn_command == "delete":
            return cmd_connection_delete(args)
        else:
            conn_parser.print_help()
            return 1

    # Handle query command
    if args.command == "query":
        return cmd_query(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
