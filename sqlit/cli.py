#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""sqlit - A terminal UI for SQL databases."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from sqlit.domains.connections.cli.completion import complete_connection_names
from sqlit.domains.connections.cli.helpers import add_schema_arguments, build_connection_config_from_args
from sqlit.domains.connections.domain.config import AuthType, ConnectionConfig, DatabaseType
from sqlit.domains.connections.providers.catalog import get_provider_schema, get_supported_db_types
from sqlit.shared.app.runtime import MockConfig, RuntimeConfig
from sqlit.shared.app.startup_profiler import configure as configure_startup_profiler
from sqlit.shared.app.startup_profiler import enable_import_timing
from sqlit.shared.app.startup_profiler import log_step as log_startup_step
from sqlit.shared.app.startup_profiler import span as startup_span
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


def _looks_like_project_path(arg: str) -> bool:
    """Conservative test for a positional project-dir argument.

    Only matches things that are obviously paths: `.`, `..`, anything
    starting with `./`, `../`, `/`, `~`, or anything ending in `/`.
    """
    if arg in {".", ".."}:
        return True
    if arg.startswith(("./", "../", "/", "~")):
        return True
    if arg.endswith("/"):
        return True
    return False


def _extract_project_dir(argv: list[str]) -> tuple[Path | None, list[str]]:
    """Extract a positional project-dir argument from argv if present.

    Returns (project_dir, remaining_argv). Exits with an error if the
    user passed a path that doesn't resolve to an existing directory.
    """
    subcommands = {"connections", "connection", "connect", "query", "docker", "alerts"}
    result_argv: list[str] = []
    project_dir: Path | None = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if i == 0:
            result_argv.append(arg)
            i += 1
            continue
        # Flags pass straight through (let argparse handle them).
        if arg.startswith("-"):
            result_argv.append(arg)
            i += 1
            continue
        # First subcommand: copy the rest verbatim.
        if arg in subcommands:
            result_argv.extend(argv[i:])
            break
        if project_dir is None and _looks_like_project_path(arg):
            resolved = Path(arg).expanduser().resolve()
            if not resolved.is_dir():
                print(
                    f"Error: project directory does not exist: {arg}",
                    file=sys.stderr,
                )
                sys.exit(1)
            project_dir = resolved
            i += 1
            continue
        result_argv.append(arg)
        i += 1

    return project_dir, result_argv


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
                    "--theme",
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


def _sane_tty() -> None:
    if os.name != "posix":
        return
    if not sys.stdin.isatty():
        return
    try:
        subprocess.run(
            ["stty", "sane"],
            stdin=sys.stdin,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        pass


def _prewarm_process_worker(runtime: RuntimeConfig) -> Any | None:
    """Spawn the process worker before the Textual App is constructed.

    `multiprocessing.spawn` collects the parent's open file descriptors at
    spawn time. Textual's `App.__init__` registers signal-handler pipes
    and other non-inheritable FDs, which cause spawn to abort with
    `ValueError: bad value(s) in fds_to_keep` (see issue #189). Spawning
    here — before the App is constructed — is the latest point at which
    the FD set is still clean.

    Returns the live client, or None if spawn fails or the worker is
    disabled. On failure we fall through to the lazy path inside the UI;
    on macOS that path raises and the in-process executor takes over.
    """
    if not runtime.process_worker:
        return None
    if runtime.mock.enabled:
        return None
    try:
        from sqlit.domains.process_worker.app.process_worker_client import ProcessWorkerClient

        return ProcessWorkerClient()
    except Exception:
        return None


def _run_app(app: Any) -> int:
    exit_code: int | None = None
    handled_signals = [signal.SIGINT, signal.SIGTERM]
    for maybe_sig in (getattr(signal, "SIGHUP", None), getattr(signal, "SIGQUIT", None)):
        if isinstance(maybe_sig, signal.Signals):
            handled_signals.append(maybe_sig)

    previous_handlers: dict[signal.Signals, Any] = {}

    def _handle_signal(signum: int, _frame: Any) -> None:
        nonlocal exit_code
        exit_code = 128 + signum
        try:
            close_worker = getattr(app, "_close_process_worker_client", None)
            if callable(close_worker):
                close_worker()
        except Exception:
            pass
        try:
            app.exit()
            return
        except Exception:
            _sane_tty()
            raise KeyboardInterrupt

    for sig in handled_signals:
        try:
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, _handle_signal)
        except Exception:
            continue

    try:
        _sane_tty()
        app.run()
    except KeyboardInterrupt:
        _sane_tty()
        return exit_code if exit_code is not None else 130
    finally:
        _sane_tty()
        for sig, handler in previous_handlers.items():
            try:
                signal.signal(sig, handler)
            except Exception:
                pass

    return exit_code if exit_code is not None else 0


def _parse_missing_drivers(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _parse_float_value(value: str | None, default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _add_stdin_secret_flags(parser: argparse.ArgumentParser, *, include_ssh: bool) -> None:
    """Attach --password-stdin (and optionally --ssh-password-stdin) to a parser."""
    parser.add_argument(
        "--password-stdin",
        dest="password_stdin",
        action="store_true",
        help="Read the password from stdin (one line, trailing newline stripped)",
    )
    if include_ssh:
        parser.add_argument(
            "--ssh-password-stdin",
            dest="ssh_password_stdin",
            action="store_true",
            help="Read the SSH password from stdin (one line, trailing newline stripped)",
        )


def _resolve_stdin_secrets(args: argparse.Namespace) -> None:
    """Populate args.password / args.url / args.ssh_password from stdin if requested.

    Recognised stdin-trigger attrs: ``password_stdin``, ``url_stdin``,
    ``ssh_password_stdin``. At most one may be set per invocation — stdin
    is a single stream and we read one line from it. The corresponding
    cleartext flag must not also be set.
    """
    from sqlit.domains.connections.domain.stdin_secret import (
        StdinSecretError,
        read_secret_from_stdin,
    )

    requests: list[tuple[str, str]] = []
    if getattr(args, "password_stdin", False):
        requests.append(("password", "password"))
    if getattr(args, "url_stdin", False):
        requests.append(("url", "url"))
    if getattr(args, "ssh_password_stdin", False):
        requests.append(("ssh_password", "ssh-password"))

    if not requests:
        return

    if len(requests) > 1:
        flags = ", ".join(f"--{label}-stdin" for _, label in requests)
        raise SystemExit(
            f"Error: only one of {flags} may be used per invocation "
            f"(stdin can only feed one secret)."
        )

    attr, label = requests[0]
    existing = getattr(args, attr, None)
    if existing:
        raise SystemExit(
            f"Error: --{label} and --{label}-stdin are mutually exclusive."
        )

    try:
        value = read_secret_from_stdin(label=label)
    except StdinSecretError as exc:
        raise SystemExit(f"Error: {exc}")

    setattr(args, attr, value)


def _resolve_startup_log_path(argv: list[str]) -> Path | None:
    env_profile = os.environ.get("SQLIT_PROFILE_STARTUP") == "1"
    env_exit = os.environ.get("SQLIT_PROFILE_STARTUP_EXIT") == "1"
    env_log_path = os.environ.get("SQLIT_PROFILE_STARTUP_FILE", "").strip() or None

    profile_enabled = env_profile or env_exit or bool(env_log_path)
    log_path = Path(env_log_path).expanduser() if env_log_path else None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--profile-startup" or arg == "--profile-startup-exit":
            profile_enabled = True
        elif arg.startswith("--profile-startup-file="):
            log_path = Path(arg.split("=", 1)[1]).expanduser()
            profile_enabled = True
        elif arg == "--profile-startup-file" and i + 1 < len(argv):
            log_path = Path(argv[i + 1]).expanduser()
            profile_enabled = True
            i += 1
        i += 1

    if profile_enabled and log_path is None:
        log_path = Path(".sqlit") / "startup.txt"
    return log_path


def _resolve_startup_import_settings(argv: list[str]) -> tuple[Path | None, float]:
    env_log_path = os.environ.get("SQLIT_PROFILE_STARTUP_IMPORTS_FILE", "").strip() or None
    env_enabled = os.environ.get("SQLIT_PROFILE_STARTUP_IMPORTS") == "1" or bool(env_log_path)
    env_min_ms = _parse_float_value(os.environ.get("SQLIT_PROFILE_STARTUP_IMPORTS_MIN_MS"), 1.0)

    enabled = env_enabled
    log_path = Path(env_log_path).expanduser() if env_log_path else None
    min_ms = env_min_ms

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--profile-startup-imports":
            enabled = True
        elif arg.startswith("--profile-startup-imports-file="):
            log_path = Path(arg.split("=", 1)[1]).expanduser()
            enabled = True
        elif arg == "--profile-startup-imports-file" and i + 1 < len(argv):
            log_path = Path(argv[i + 1]).expanduser()
            enabled = True
            i += 1
        elif arg.startswith("--profile-startup-imports-min-ms="):
            min_ms = _parse_float_value(arg.split("=", 1)[1], min_ms)
        elif arg == "--profile-startup-imports-min-ms" and i + 1 < len(argv):
            min_ms = _parse_float_value(argv[i + 1], min_ms)
            i += 1
        i += 1

    if enabled and log_path is None:
        log_path = Path(".sqlit") / "startup-imports.txt"
    return log_path, min_ms


def _exec_restart(argv: list[str]) -> None:
    if not argv:
        argv = [sys.executable]
    exe = argv[0]
    has_sep = os.sep in exe or (os.altsep and os.altsep in exe)
    # execv doesn't search PATH; use execvp for bare commands (e.g. "sqlit").
    if has_sep:
        os.execv(exe, argv)
    else:
        os.execvp(exe, argv)


def _build_runtime(
    args: argparse.Namespace,
    startup_mark: float,
    *,
    project_dir: Path | None = None,
) -> RuntimeConfig:
    settings_path = Path(args.settings).expanduser() if args.settings else None
    max_rows = args.max_rows if args.max_rows and args.max_rows > 0 else None
    mock_install = args.mock_install if args.mock_install != "real" else None
    mock_pipx = args.mock_pipx if args.mock_pipx != "auto" else None
    startup_log_path = Path(args.profile_startup_file).expanduser() if args.profile_startup_file else None
    startup_exit = bool(args.profile_startup_exit)
    startup_import_log_path = (
        Path(args.profile_startup_imports_file).expanduser() if args.profile_startup_imports_file else None
    )
    startup_import_min_ms = (
        float(args.profile_startup_imports_min_ms)
        if args.profile_startup_imports_min_ms is not None
        else 1.0
    )

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

    import_profile_enabled = bool(args.profile_startup_imports) or startup_import_log_path is not None
    if import_profile_enabled and startup_import_log_path is None:
        startup_import_log_path = Path(".sqlit") / "startup-imports.txt"

    profile_startup = (
        bool(args.profile_startup)
        or startup_log_path is not None
        or startup_exit
        or import_profile_enabled
    )
    if profile_startup and startup_log_path is None:
        startup_log_path = Path(".sqlit") / "startup.txt"

    return RuntimeConfig(
        settings_path=settings_path,
        project_dir=project_dir,
        theme=getattr(args, "theme", None),
        max_rows=max_rows,
        debug_mode=bool(args.debug),
        debug_idle_scheduler=bool(args.debug_idle_scheduler),
        profile_startup=profile_startup,
        startup_mark=startup_mark if profile_startup or args.debug else None,
        startup_log_path=startup_log_path,
        startup_exit_after_refresh=startup_exit,
        startup_import_log_path=startup_import_log_path,
        startup_import_min_ms=startup_import_min_ms,
        mock=mock_config,
    )


def _cmd_completion(shell: str) -> int:
    """Print the argcomplete activation snippet for the given shell."""
    try:
        import argcomplete
    except ImportError:
        print(
            "Shell completion requires the 'argcomplete' package.\n"
            "Install it with: pip install 'sqlit-tui[completion]'",
            file=sys.stderr,
        )
        return 1

    try:
        snippet = argcomplete.shellcode(["sqlit"], shell=shell)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - depends on argcomplete version
        print(
            f"Could not generate completion for {shell!r}: {exc}\n"
            "Your argcomplete version may not support this shell; "
            "try upgrading: pip install -U argcomplete",
            file=sys.stderr,
        )
        return 1

    print(snippet)
    return 0


def main() -> int:
    """Entry point for the CLI."""
    startup_mark = time.perf_counter()
    startup_log_path = _resolve_startup_log_path(sys.argv)
    startup_import_log_path, startup_import_min_ms = _resolve_startup_import_settings(sys.argv)
    configure_startup_profiler(
        log_path=startup_log_path,
        start_mark=startup_mark,
        init_mark=startup_mark,
        clear=True,
    )
    enable_import_timing(
        log_path=startup_import_log_path,
        min_ms=startup_import_min_ms,
    )
    log_startup_step("cli_start")

    # Extract positional project-dir before argparse so we can route
    # connections/history/starred into <project>/.sqlit/.
    with startup_span("cli_extract_project_dir"):
        project_dir, filtered_argv = _extract_project_dir(sys.argv)
    # Extract connection URL before argparse (URLs conflict with subcommands)
    with startup_span("cli_extract_connection_url"):
        connection_url, filtered_argv = _extract_connection_url(filtered_argv)

    log_startup_step("cli_parser_start")
    from sqlit import __version__
    parser = argparse.ArgumentParser(
        prog="sqlit",
        description="A terminal UI for SQL databases",
        epilog=(
            "Connect via URL: sqlit mysql://user:pass@host/db, "
            "sqlit sqlite:///path/to/db.sqlite\n"
            "Project mode: sqlit . or sqlit /path/to/project — "
            "connections, history, and starred queries live in "
            "<project>/.sqlit/ instead of the global config."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
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
    parser.add_argument(
        "--password",
        help="Temporary connection password (or use --password-stdin to read from stdin)",
    )
    parser.add_argument(
        "--password-stdin",
        dest="password_stdin",
        action="store_true",
        help="Read the password from stdin (one line, trailing newline stripped)",
    )
    parser.add_argument("--file-path", help="Temporary connection file path (SQLite/DuckDB)")
    parser.add_argument(
        "--auth-type",
        choices=[t.value for t in AuthType],
        help="Temporary connection auth type (SQL Server only)",
    )
    parser.add_argument("--supabase-region", help="Supabase region (temporary connection)")
    parser.add_argument("--supabase-project-id", help="Supabase project id (temporary connection)")
    parser.add_argument(
        "--supabase-aws-shard",
        help="Supabase pooler shard prefix (temporary connection, e.g. aws-0, aws-1)",
    )
    parser.add_argument(
        "--settings",
        metavar="PATH",
        help="Path to settings JSON file (overrides the one in the sqlit config directory)",
    )
    parser.add_argument(
        "--theme",
        metavar="NAME",
        help="Theme to use (e.g., dracula, gruvbox, tokyo-night, textual-ansi for terminal colors)",
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
        "--profile-startup-file",
        metavar="PATH",
        help="Write startup timing diagnostics to a file (implies --profile-startup).",
    )
    parser.add_argument(
        "--profile-startup-exit",
        action="store_true",
        help="Exit after the first UI refresh (implies --profile-startup).",
    )
    parser.add_argument(
        "--profile-startup-imports",
        action="store_true",
        help="Log per-module import timings to .sqlit/startup-imports.txt.",
    )
    parser.add_argument(
        "--profile-startup-imports-file",
        metavar="PATH",
        help="Write per-module import timings to a file.",
    )
    parser.add_argument(
        "--profile-startup-imports-min-ms",
        type=float,
        metavar="MS",
        help="Only log imports slower than MS (default: 1.0).",
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
    parser.add_argument(
        "-c",
        "--connection",
        metavar="NAME",
        help="Connect to a saved connection by name (opens TUI with only this connection)",
    ).completer = complete_connection_names  # type: ignore[attr-defined]

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
        help=(
            "Connection URL (e.g., postgresql://user:pass@host:5432/db). "
            "Requires --name. Use --url-stdin to read it from stdin instead."
        ),
    )
    add_parser.add_argument(
        "--url-stdin",
        dest="url_stdin",
        action="store_true",
        help="Read the connection URL from stdin (one line, trailing newline stripped)",
    )
    add_parser.add_argument(
        "--name",
        "-n",
        dest="url_name",
        help="Connection name (required when using --url / --url-stdin)",
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
        provider_parser.add_argument("--password-command", dest="password_command", help="Shell command to retrieve the database password")
        provider_parser.add_argument("--ssh-password-command", dest="ssh_password_command", help="Shell command to retrieve the SSH password")
        _add_stdin_secret_flags(provider_parser, include_ssh=True)
        provider_parser.add_argument(
            "--alert",
            metavar="MODE",
            help="Per-connection query alert mode: off|delete|write",
        )

    edit_parser = conn_subparsers.add_parser("edit", help="Edit an existing connection")
    edit_parser.add_argument(
        "connection_name", help="Name of connection to edit"
    ).completer = complete_connection_names  # type: ignore[attr-defined]
    edit_parser.add_argument("--name", "-n", help="New connection name")
    edit_parser.add_argument("--server", "-s", help="Server address")
    edit_parser.add_argument("--host", help="Alias for --server (e.g. Cloudflare D1 Account ID)")
    edit_parser.add_argument("--port", "-P", help="Port")
    edit_parser.add_argument("--database", "-d", help="Database name")
    edit_parser.add_argument("--username", "-u", help="Username")
    edit_parser.add_argument(
        "--password",
        "-p",
        help="Password (or use --password-stdin to read from stdin)",
    )
    edit_parser.add_argument(
        "--auth-type",
        "-a",
        choices=[t.value for t in AuthType],
        help="Authentication type (SQL Server only)",
    )
    edit_parser.add_argument("--file-path", help="Database file path (SQLite only)")
    edit_parser.add_argument("--password-command", dest="password_command", help="Shell command to retrieve the database password")
    edit_parser.add_argument("--ssh-password-command", dest="ssh_password_command", help="Shell command to retrieve the SSH password")
    _add_stdin_secret_flags(edit_parser, include_ssh=True)
    edit_parser.add_argument(
        "--alert",
        metavar="MODE",
        help="Per-connection query alert mode: off|delete|write|unset (clears the override)",
    )

    delete_parser = conn_subparsers.add_parser("delete", help="Delete a connection")
    delete_parser.add_argument(
        "connection_name", help="Name of connection to delete"
    ).completer = complete_connection_names  # type: ignore[attr-defined]

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
        provider_parser.add_argument("--password-command", dest="password_command", help="Shell command to retrieve the database password")
        provider_parser.add_argument("--ssh-password-command", dest="ssh_password_command", help="Shell command to retrieve the SSH password")
        _add_stdin_secret_flags(provider_parser, include_ssh=True)
        provider_parser.add_argument(
            "--alert",
            metavar="MODE",
            help="Per-connection query alert mode: off|delete|write",
        )

    query_parser = subparsers.add_parser("query", help="Execute a SQL query")
    query_parser.add_argument(
        "--connection", "-c", required=True, help="Connection name to use"
    ).completer = complete_connection_names  # type: ignore[attr-defined]
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

    # Query alert management
    alerts_parser = subparsers.add_parser(
        "alerts",
        help="Manage query confirmation alert overrides",
        description=(
            "Manage query alert overrides. Hierarchy: database > connection > global."
        ),
    )
    alerts_subparsers = alerts_parser.add_subparsers(dest="alerts_command", help="Alert commands")
    alerts_subparsers.add_parser("list", help="Show global and all configured overrides")

    alerts_set = alerts_subparsers.add_parser("set", help="Set an alert mode at a scope")
    alerts_set.add_argument("mode", help="off | delete | write")
    alerts_set.add_argument(
        "--connection",
        "-c",
        help="Target a specific saved connection (omit for global)",
    ).completer = complete_connection_names  # type: ignore[attr-defined]
    alerts_set.add_argument(
        "--database",
        "-d",
        help="Target a database on the connection (requires --connection)",
    )

    alerts_unset = alerts_subparsers.add_parser(
        "unset", help="Clear an alert override (falls back to the next scope)"
    )
    alerts_unset.add_argument(
        "--connection",
        "-c",
        help="Connection whose override to clear",
    ).completer = complete_connection_names  # type: ignore[attr-defined]
    alerts_unset.add_argument(
        "--database",
        "-d",
        help="Database whose override to clear (requires --connection)",
    )

    completion_parser = subparsers.add_parser(
        "completion",
        help="Print a shell completion script for sqlit",
        description=(
            "Print the shell completion activation snippet for sqlit.\n"
            "Requires the optional 'argcomplete' dependency: pip install 'sqlit-tui[completion]'\n\n"
            "  bash:  eval \"$(sqlit completion bash)\"   # add to ~/.bashrc\n"
            "  zsh:   eval \"$(sqlit completion zsh)\"    # add to ~/.zshrc\n"
            "  fish:  sqlit completion fish | source     # add to ~/.config/fish/config.fish"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    completion_parser.add_argument(
        "shell",
        choices=["bash", "zsh", "fish"],
        help="Shell to print the completion script for",
    )

    log_startup_step("cli_parser_end")

    # Shell completion: argcomplete inspects the fully-built parser and exits
    # here (before runtime/services are built and the TUI is imported) when a
    # completion request is in progress. No-op when argcomplete isn't installed
    # or we're running normally.
    try:
        import argcomplete
    except ImportError:
        pass
    else:
        argcomplete.autocomplete(parser)

    with startup_span("cli_parse_args"):
        args = parser.parse_args(filtered_argv[1:])  # Skip program name
    _resolve_stdin_secrets(args)
    log_startup_step("cli_parse_end")

    # `sqlit completion <shell>` prints an activation snippet and exits without
    # touching the runtime or services.
    if args.command == "completion":
        return _cmd_completion(args.shell)

    with startup_span("runtime_build"):
        runtime = _build_runtime(args, startup_mark, project_dir=project_dir)

    with startup_span("services_build"):
        services = build_app_services(runtime)
    if args.command is None:
        from sqlit.domains.connections.app.url_parser import parse_connection_url
        with startup_span("import_ssmstui"):
            from sqlit.domains.shell.app.main import SSMSTUI

        if args.mock:
            from sqlit.domains.connections.app.mocks import get_mock_profile, list_mock_profiles

            mock_profile = get_mock_profile(args.mock)
            if mock_profile is None:
                print(f"Unknown mock profile: {args.mock}")
                print(f"Available profiles: {', '.join(list_mock_profiles())}")
                return 1
            services.apply_mock_profile(mock_profile)

        startup_config = None
        exclusive_connection = False
        try:
            # Check for saved connection by name first
            if args.connection:
                saved_connections = services.connection_store.load_all(load_credentials=False)
                matching = [c for c in saved_connections if c.name == args.connection]
                if not matching:
                    print(f"Error: Connection '{args.connection}' not found")
                    print("Available connections:")
                    for conn in saved_connections:
                        print(f"  - {conn.name}")
                    return 1
                startup_config = matching[0]
                exclusive_connection = True
            # Check for connection URL (extracted before argparse)
            elif connection_url:
                startup_config = parse_connection_url(
                    connection_url,
                    name=getattr(args, "name", None),
                )
            else:
                startup_config = _build_temp_connection(args)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        # Spawn the worker before the Textual App is constructed; see
        # _prewarm_process_worker for why this matters on macOS.
        process_worker_client = _prewarm_process_worker(runtime)
        app = SSMSTUI(
            services=services,
            startup_connection=startup_config,
            exclusive_connection=exclusive_connection,
            process_worker_client=process_worker_client,
        )
        exit_code = _run_app(app)
        if exit_code != 0:
            return exit_code
        if getattr(app, "_restart_requested", False):
            argv = getattr(app, "_restart_argv", None) or app._compute_restart_argv()
            try:
                _exec_restart(argv)
            except OSError as exc:
                print(f"Failed to restart sqlit: {exc}", file=sys.stderr)
                return 1
        return 0

    from sqlit.domains.connections.cli.commands import (
        cmd_connection_create,
        cmd_connection_delete,
        cmd_connection_edit,
        cmd_connection_list,
    )
    from sqlit.domains.query.cli.commands import cmd_query

    if args.command == "connect":
        with startup_span("import_ssmstui"):
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

        from sqlit.domains.connections.cli.commands import _apply_alert_option

        alert_error = _apply_alert_option(temp_config, getattr(args, "alert", None))
        if alert_error:
            print(f"Error: {alert_error}")
            return 1

        process_worker_client = _prewarm_process_worker(runtime)
        app = SSMSTUI(
            services=services,
            startup_connection=temp_config,
            process_worker_client=process_worker_client,
        )
        return _run_app(app)

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

    if args.command == "alerts":
        from sqlit.domains.query.cli.alerts_commands import (
            cmd_alerts_list,
            cmd_alerts_set,
            cmd_alerts_unset,
        )

        if args.alerts_command == "list":
            return cmd_alerts_list(args, services=services)
        if args.alerts_command == "set":
            return cmd_alerts_set(args, services=services)
        if args.alerts_command == "unset":
            return cmd_alerts_unset(args, services=services)
        alerts_parser.print_help()
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
    except ValueError as err:
        raise ValueError(f"Invalid database type '{db_type}'") from err

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
