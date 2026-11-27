"""CLI query command handlers."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from typing import Any

from sqlit.domains.connections.app.session import ConnectionSession
from sqlit.domains.connections.cli.prompts import prompt_for_password
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.query.app.query_service import (
    DialectQueryAnalyzer,
    NonQueryResult,
    QueryKind,
    QueryResult,
    QueryService,
)
from sqlit.shared.app.runtime import RuntimeConfig
from sqlit.shared.app.services import AppServices, build_app_services


_SQLITE_TRIVIA = re.compile(r"(?:[ \t\r\n\f;\ufeff]+|--[^\n]*|/\*.*?(?:\*/|\Z))+", re.DOTALL)


def _skip_sqlite_trivia(sql: str, start: int) -> int:
    match = _SQLITE_TRIVIA.match(sql, start)
    return match.end() if match else start


def _split_sqlite_script(sql: str) -> list[str]:
    """Find SQLite statement boundaries, including complete trigger bodies."""
    statements = []
    start = _skip_sqlite_trivia(sql, 0)
    for separator in re.finditer(";", sql):
        end = separator.end()
        if end <= start:
            continue
        statement = sql[start:end]
        if "\0" not in statement and sqlite3.complete_statement(statement):
            statements.append(statement)
            start = _skip_sqlite_trivia(sql, end)

    if start < len(sql):
        statements.append(sql[start:])
    return statements


def _find_connection(connections: list[ConnectionConfig], name: str) -> ConnectionConfig | None:
    for conn in connections:
        if conn.name == name:
            return conn
    return None


def _load_query_text(args: Any) -> tuple[str | None, str | None]:
    if args.query:
        return args.query, None
    if args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                return f.read(), None
        except FileNotFoundError:
            return None, f"Error: File '{args.file}' not found."
        except OSError as exc:
            return None, f"Error reading file: {exc}"
    return None, "Error: Either --query or --file must be provided."


def _get_query_service(
    services: AppServices,
    provider: Any,
    query_service: QueryService | None,
) -> QueryService:
    if query_service is not None:
        return query_service
    return QueryService(services.history_store, analyzer=DialectQueryAnalyzer(provider.dialect))


def _should_stream_results(
    *, max_rows: int | None, fmt: str, analyzer: DialectQueryAnalyzer, query: str, has_cursor: bool
) -> bool:
    return (
        max_rows is None
        and fmt in ("csv", "json")
        and analyzer.classify(query) == QueryKind.RETURNS_ROWS
        and has_cursor
    )


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


def _stream_output(cursor: Any, columns: list[str], fmt: str) -> int:
    if fmt == "csv":
        return _stream_csv_output(cursor, columns)
    return _stream_json_output(cursor, columns)


def _execute_sqlite_script(
    connection: sqlite3.Connection,
    statements: list[str],
    service: QueryService,
    connection_name: str,
    fmt: str,
    max_rows: int | None,
) -> QueryResult | NonQueryResult | None:
    # Keep SQLite's per-statement autocommit and honor explicit SQL transactions.
    connection.isolation_level = None
    for statement in statements[:-1]:
        # SQLite may report an error while stepping through result rows.
        with closing(connection.execute(statement)) as cursor:
            for _ in cursor:
                pass
        service._save_to_history(connection_name, statement)

    statement = statements[-1]
    with closing(connection.execute(statement)) as cursor:
        if not cursor.description:
            result = NonQueryResult(rows_affected=cursor.rowcount)
        else:
            columns = [col[0] for col in cursor.description]
            if max_rows is None and fmt in ("csv", "json"):
                row_count = _stream_output(cursor, columns, fmt)
                print(f"\n({row_count} row(s) returned)", file=sys.stderr)
                result = None
            else:
                fetched = cursor.fetchall() if max_rows is None else cursor.fetchmany(max_rows + 1)
                truncated = max_rows is not None and len(fetched) > max_rows
                if truncated:
                    for _ in cursor:
                        pass
                rows = [tuple(row) for row in fetched[:max_rows]]
                result = QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)
    service._save_to_history(connection_name, statement)
    return result


def _output_table(columns: list[str], rows: list[tuple], truncated: bool) -> None:
    """Output query results in table format with optimized width calculation."""
    max_col_width = 50

    # Only scan first 100 rows for performance
    col_widths = [min(len(col), max_col_width) for col in columns]
    for row in rows[:100]:
        for i, val in enumerate(row):
            val_str = str(val) if val is not None else "NULL"
            col_widths[i] = min(max_col_width, max(col_widths[i], len(val_str)))

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
    services: AppServices | None = None,
    session_factory: Callable[[ConnectionConfig], ConnectionSession] | None = None,
    query_service: QueryService | None = None,
) -> int:
    """Execute a SQL query against a connection."""
    services = services or build_app_services(RuntimeConfig.from_env())
    connections = services.connection_store.load_all()

    config = _find_connection(connections, args.connection)
    if config is None:
        print(f"Error: Connection '{args.connection}' not found.")
        return 1

    provider = services.provider_factory(config.db_type)
    if args.database:
        config = provider.apply_database_override(config, args.database)

    config = prompt_for_password(config)

    query, error = _load_query_text(args)
    if error:
        print(error)
        return 1
    if query is None:
        print("Error: No query provided.")
        return 1

    max_rows = args.limit if args.limit > 0 else None

    create_session = session_factory or services.session_factory
    service = _get_query_service(services, provider, query_service)
    analyzer = DialectQueryAnalyzer(provider.dialect)

    try:
        with create_session(config) as session:
            statements = _split_sqlite_script(query) if config.db_type == "sqlite" else []
            if len(statements) > 1:
                result = _execute_sqlite_script(
                    session.connection, statements, service, config.name, args.format, max_rows
                )
                if result is None:
                    return 0
            else:
                has_cursor = hasattr(session.connection, "cursor") and callable(getattr(session.connection, "cursor", None))

                if _should_stream_results(
                    max_rows=max_rows,
                    fmt=args.format,
                    analyzer=analyzer,
                    query=query,
                    has_cursor=has_cursor,
                ):
                    cursor = session.connection.cursor()
                    cursor.execute(query)

                    if not cursor.description:
                        print("Query executed successfully (no results)")
                        return 0

                    columns = [col[0] for col in cursor.description]

                    row_count = _stream_output(cursor, columns, args.format)
                    service._save_to_history(config.name, query)
                    print(f"\n({row_count} row(s) returned)", file=sys.stderr)
                    return 0

                result = service.execute(
                    connection=session.connection,
                    executor=session.provider.query_executor,
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
