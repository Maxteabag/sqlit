"""Helpers for loading mock configuration from settings JSON."""

from __future__ import annotations

import os
from dataclasses import fields
from typing import Any

from .config import ConnectionConfig
from .db.adapters.base import ColumnInfo
from .mocks import MockDatabaseAdapter, MockProfile, get_mock_profile
from .services.docker_detector import ContainerStatus, DetectedContainer

# Global storage for mock docker containers
_mock_docker_containers: list[DetectedContainer] | None = None


def set_mock_docker_containers(containers: list[DetectedContainer] | None) -> None:
    """Set mock Docker containers for testing/demo purposes."""
    global _mock_docker_containers
    _mock_docker_containers = containers


def get_mock_docker_containers() -> list[DetectedContainer] | None:
    """Get mock Docker containers if set."""
    return _mock_docker_containers


def apply_mock_environment(settings: dict[str, Any]) -> None:
    """Apply environment-based mock settings for driver/install behavior."""
    mock_settings = settings.get("mock")
    if not isinstance(mock_settings, dict) or not mock_settings.get("enabled"):
        return

    drivers = mock_settings.get("drivers", {})
    if isinstance(drivers, dict):
        missing = drivers.get("missing")
        if isinstance(missing, list):
            os.environ["SQLIT_MOCK_MISSING_DRIVERS"] = ",".join(str(item).strip() for item in missing if str(item).strip())
        elif isinstance(missing, str) and missing.strip():
            os.environ["SQLIT_MOCK_MISSING_DRIVERS"] = missing.strip()
        elif missing == []:
            os.environ.pop("SQLIT_MOCK_MISSING_DRIVERS", None)

        install_result = str(drivers.get("install_result", "")).strip().lower()
        if install_result in {"success", "fail"}:
            os.environ["SQLIT_MOCK_INSTALL_RESULT"] = install_result
        elif install_result == "real":
            os.environ.pop("SQLIT_MOCK_INSTALL_RESULT", None)

        pipx = str(drivers.get("pipx", "")).strip().lower()
        if pipx in {"pipx", "pip", "unknown"}:
            os.environ["SQLIT_MOCK_PIPX"] = pipx
        elif pipx == "auto":
            os.environ.pop("SQLIT_MOCK_PIPX", None)

    # Parse and set mock Docker containers
    docker_containers = mock_settings.get("docker_containers")
    if isinstance(docker_containers, list):
        containers = _parse_docker_containers(docker_containers)
        set_mock_docker_containers(containers)


def build_mock_profile_from_settings(settings: dict[str, Any]) -> MockProfile | None:
    """Build a MockProfile from settings JSON."""
    mock_settings = settings.get("mock")
    if not isinstance(mock_settings, dict):
        return None

    if not mock_settings.get("enabled"):
        return None

    profile_name = str(mock_settings.get("profile") or "settings")
    base_profile = get_mock_profile(profile_name) or MockProfile(name=profile_name)

    connections = base_profile.connections
    if "connections" in mock_settings:
        connections = _parse_connections(mock_settings.get("connections"))

    adapters = dict(base_profile.adapters)
    adapters_config = mock_settings.get("adapters")
    if isinstance(adapters_config, dict):
        for db_type, adapter_config in adapters_config.items():
            if not isinstance(adapter_config, dict):
                continue
            adapters[str(db_type)] = _build_adapter_from_settings(str(db_type), adapter_config)

    use_default = base_profile.use_default_adapters
    if "use_default_adapters" in mock_settings:
        use_default = bool(mock_settings.get("use_default_adapters"))

    return MockProfile(
        name=profile_name,
        connections=connections,
        adapters=adapters,
        use_default_adapters=use_default,
    )


def _parse_connections(raw: Any) -> list[ConnectionConfig]:
    if not isinstance(raw, list):
        return []
    allowed_fields = {f.name for f in fields(ConnectionConfig)}
    connections: list[ConnectionConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        payload = {k: v for k, v in item.items() if k in allowed_fields}
        try:
            connections.append(ConnectionConfig(**payload))
        except TypeError:
            continue
    return connections


def _build_adapter_from_settings(db_type: str, config: dict[str, Any]) -> MockDatabaseAdapter:
    name = str(config.get("name") or db_type.title())
    default_schema = str(config.get("default_schema") or "")

    connect = config.get("connect") if isinstance(config.get("connect"), dict) else {}
    connect_result = str(connect.get("result") or "success")
    connect_error = str(connect.get("error_message") or "Connection failed")
    required_fields = connect.get("required_fields")
    if not isinstance(required_fields, list):
        required_fields = []
    required_fields = [str(field) for field in required_fields if str(field).strip()]
    allowed = connect.get("allowed")
    if not isinstance(allowed, list):
        allowed = []
    allowed = [item for item in allowed if isinstance(item, dict)]
    auth_error = str(connect.get("auth_error_message") or "Authentication failed")

    tables = _parse_table_list(config.get("tables"))
    views = _parse_table_list(config.get("views"))
    columns: dict[str, list[ColumnInfo]] = {}
    query_results: dict[str, tuple[list[str], list[tuple]]] = {}

    schemas = config.get("schemas")
    if isinstance(schemas, dict):
        for schema_name, schema_config in schemas.items():
            if not isinstance(schema_config, dict):
                continue
            schema = str(schema_name)
            _ingest_schema(schema, schema_config, tables, views, columns, query_results)

    raw_columns = config.get("columns")
    if isinstance(raw_columns, dict):
        for key, value in raw_columns.items():
            columns[str(key)] = _parse_columns(value)

    raw_query_results = config.get("query_results")
    if isinstance(raw_query_results, dict):
        for pattern, result in raw_query_results.items():
            parsed = _parse_query_result(result)
            if parsed:
                query_results[str(pattern)] = parsed

    default_query_result = None
    raw_default = config.get("default_query_result")
    if isinstance(raw_default, dict):
        parsed_default = _parse_query_result(raw_default)
        if parsed_default:
            default_query_result = parsed_default

    query_delay = 0.0
    raw_delay = config.get("query_delay")
    if isinstance(raw_delay, (int, float)):
        query_delay = float(raw_delay)

    return MockDatabaseAdapter(
        name=name,
        tables=tables,
        views=views,
        columns=columns,
        query_results=query_results,
        default_schema=default_schema,
        default_query_result=default_query_result,
        connect_result=connect_result,
        connect_error=connect_error,
        required_fields=required_fields,
        allowed_connections=allowed,
        auth_error=auth_error,
        query_delay=query_delay,
    )


def _ingest_schema(
    schema: str,
    schema_config: dict[str, Any],
    tables: list[tuple[str, str]],
    views: list[tuple[str, str]],
    columns: dict[str, list[ColumnInfo]],
    query_results: dict[str, tuple[list[str], list[tuple]]],
) -> None:
    schema_tables = schema_config.get("tables")
    if isinstance(schema_tables, dict):
        for table_name, table_config in schema_tables.items():
            if not isinstance(table_config, dict):
                continue
            table = str(table_name)
            tables.append((schema, table))
            cols = _parse_columns(table_config.get("columns"))
            if cols:
                columns[f"{schema}.{table}"] = cols
            rows = _parse_rows(table_config.get("rows"))
            if rows and cols:
                column_names = [col.name for col in cols]
                _add_table_query_results(schema, table, column_names, rows, query_results)
            table_query_results = table_config.get("query_results")
            if isinstance(table_query_results, dict):
                for pattern, result in table_query_results.items():
                    parsed = _parse_query_result(result)
                    if parsed:
                        query_results[str(pattern)] = parsed

    schema_views = schema_config.get("views")
    if isinstance(schema_views, dict):
        for view_name, view_config in schema_views.items():
            if not isinstance(view_config, dict):
                continue
            view = str(view_name)
            views.append((schema, view))
            cols = _parse_columns(view_config.get("columns"))
            if cols:
                columns[f"{schema}.{view}"] = cols
            rows = _parse_rows(view_config.get("rows"))
            if rows and cols:
                column_names = [col.name for col in cols]
                _add_table_query_results(schema, view, column_names, rows, query_results)


def _parse_table_list(raw: Any) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        return []
    tables: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        schema = str(item.get("schema") or "")
        name = str(item.get("name") or "")
        if name:
            tables.append((schema, name))
    return tables


def _parse_columns(raw: Any) -> list[ColumnInfo]:
    if not isinstance(raw, list):
        return []
    columns: list[ColumnInfo] = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
            data_type = str(item.get("type") or "")
            if name:
                columns.append(ColumnInfo(name=name, data_type=data_type or "text"))
    return columns


def _parse_rows(raw: Any) -> list[tuple]:
    if not isinstance(raw, list):
        return []
    rows: list[tuple] = []
    for row in raw:
        if isinstance(row, list):
            rows.append(tuple(row))
        elif isinstance(row, tuple):
            rows.append(row)
    return rows


def _parse_query_result(raw: Any) -> tuple[list[str], list[tuple]] | None:
    if not isinstance(raw, dict):
        return None
    columns = raw.get("columns")
    rows = raw.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return None
    column_names = [str(col) for col in columns]
    return column_names, _parse_rows(rows)


def _add_table_query_results(
    schema: str,
    table: str,
    columns: list[str],
    rows: list[tuple],
    query_results: dict[str, tuple[list[str], list[tuple]]],
) -> None:
    patterns = [
        f'"{schema}"."{table}"',
        f"{schema}.{table}",
        f'"{table}"',
        table,
    ]
    for pattern in patterns:
        query_results.setdefault(pattern, (columns, rows))


def _parse_docker_containers(raw: Any) -> list[DetectedContainer]:
    """Parse mock Docker containers from settings JSON."""
    if not isinstance(raw, list):
        return []

    containers: list[DetectedContainer] = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        container_id = str(item.get("container_id") or item.get("id") or "mock")
        container_name = str(item.get("container_name") or item.get("name") or "")
        if not container_name:
            continue

        db_type = str(item.get("db_type") or "")
        if not db_type:
            continue

        # Parse status
        status_str = str(item.get("status") or "running").lower()
        status = ContainerStatus.RUNNING if status_str == "running" else ContainerStatus.EXITED

        # Parse port
        port = item.get("port")
        if isinstance(port, int):
            port_val = port
        elif isinstance(port, str) and port.isdigit():
            port_val = int(port)
        else:
            port_val = None

        containers.append(
            DetectedContainer(
                container_id=container_id,
                container_name=container_name,
                db_type=db_type,
                host=str(item.get("host") or "localhost"),
                port=port_val,
                username=item.get("username") or item.get("user"),
                password=item.get("password"),
                database=item.get("database"),
                status=status,
                connectable=bool(status == ContainerStatus.RUNNING and port_val is not None),
            )
        )

    return containers
