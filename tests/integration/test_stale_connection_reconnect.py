"""Integration tests for reconnecting after stale database connections.

Use --run-docker-container to spin up local test containers when providers are unavailable.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from sqlit.domains.explorer.domain.tree_nodes import (
    ColumnNode,
    ConnectionNode,
    IndexNode,
    TriggerNode,
)
from sqlit.domains.shell.app.main import SSMSTUI
from tests.fixtures.mariadb import (
    MARIADB_HOST,
    MARIADB_PASSWORD,
    MARIADB_PORT,
    MARIADB_USER,
)
from tests.fixtures.mssql import (
    MSSQL_HOST,
    MSSQL_PASSWORD,
    MSSQL_PORT,
    MSSQL_USER,
)
from tests.fixtures.mysql import MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER
from tests.fixtures.oracle import ORACLE_HOST, ORACLE_PASSWORD, ORACLE_PORT, ORACLE_USER
from tests.fixtures.postgres import (
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from tests.fixtures.utils import is_port_open, wait_for_port
from tests.helpers import ConnectionConfig
from tests.integration.browsing_base import (
    find_connection_node,
    find_database_node,
    find_folder_node,
    find_node_by_type,
    find_table_node,
    has_loading_children,
    wait_for_condition,
)

PROVIDERS = ("mysql", "mariadb", "mssql", "postgres", "oracle")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_COMPOSE_FILE = Path(__file__).resolve().parents[2] / "infra" / "docker" / "docker-compose.test.yml"
_COMPOSE_CMD: list[str] | None = None
_STARTED_SERVICES: dict[str, bool] = {}


@dataclass(frozen=True)
class DockerServiceSpec:
    service: str
    container_name: str
    host: str
    port: int
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    db_type: str
    host: str
    port: int
    username: str
    password: str
    database: str
    supports_idle: bool
    connection_id_sql: str
    table_name: str
    index_name: str
    trigger_name: str


_DOCKER_SERVICES = {
    "mysql": DockerServiceSpec(
        service="mysql",
        container_name="sqlit-test-mysql",
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        timeout_seconds=60.0,
    ),
    "mariadb": DockerServiceSpec(
        service="mariadb",
        container_name="sqlit-test-mariadb",
        host=MARIADB_HOST,
        port=MARIADB_PORT,
        timeout_seconds=60.0,
    ),
    "mssql": DockerServiceSpec(
        service="mssql",
        container_name="sqlit-test-mssql",
        host=MSSQL_HOST,
        port=MSSQL_PORT,
        timeout_seconds=90.0,
    ),
    "postgres": DockerServiceSpec(
        service="postgres",
        container_name="sqlit-test-postgres",
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        timeout_seconds=60.0,
    ),
    "oracle": DockerServiceSpec(
        service="oracle",
        container_name="sqlit-test-oracle",
        host=ORACLE_HOST,
        port=ORACLE_PORT,
        timeout_seconds=180.0,
    ),
}


def _is_local_host(host: str) -> bool:
    host_value = host.lower()
    return host_value in _LOCAL_HOSTS or host_value.startswith("127.")


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _resolve_compose_cmd() -> list[str] | None:
    global _COMPOSE_CMD
    if _COMPOSE_CMD is not None:
        return _COMPOSE_CMD
    if shutil.which("docker") is not None:
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            _COMPOSE_CMD = ["docker", "compose"]
            return _COMPOSE_CMD
    if shutil.which("docker-compose") is not None:
        _COMPOSE_CMD = ["docker-compose"]
        return _COMPOSE_CMD
    return None


def _run_compose(*args: str) -> subprocess.CompletedProcess:
    cmd = _resolve_compose_cmd()
    if cmd is None:
        raise RuntimeError("Docker Compose is not available")
    return subprocess.run(
        [*cmd, "-f", str(_COMPOSE_FILE), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _container_exists(container_name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _ensure_provider_service(request: Any, provider: str) -> None:
    service = _DOCKER_SERVICES.get(provider)
    if service is None:
        return
    if is_port_open(service.host, service.port):
        return
    if not request.config.getoption("--run-docker-container", default=False):
        return
    if not _is_local_host(service.host):
        pytest.skip(f"{provider} host '{service.host}' is not local; cannot start Docker service")
    if not _docker_available():
        pytest.skip("Docker is not available")
    if not _COMPOSE_FILE.exists():
        pytest.skip(f"Docker Compose file not found: {_COMPOSE_FILE}")
    if provider not in _STARTED_SERVICES:
        existed_before = _container_exists(service.container_name)
        try:
            _run_compose("up", "-d", service.service)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            pytest.skip(f"Failed to start Docker service '{service.service}': {exc}")
        _STARTED_SERVICES[provider] = existed_before
    if not wait_for_port(service.host, service.port, timeout=service.timeout_seconds):
        pytest.skip(
            f"Docker service '{service.service}' did not open port {service.port} on {service.host}"
        )


@pytest.fixture(scope="session", autouse=True)
def _cleanup_docker_services() -> None:
    yield
    for provider, existed_before in sorted(_STARTED_SERVICES.items()):
        service = _DOCKER_SERVICES.get(provider)
        if service is None:
            continue
        try:
            _run_compose("stop", service.service)
            if not existed_before:
                _run_compose("rm", "-f", "-s", service.service)
        except Exception:
            pass


@pytest.fixture
def provider_spec(request: Any) -> ProviderSpec:
    provider = request.param
    _ensure_provider_service(request, provider)

    if provider == "mysql":
        database = request.getfixturevalue("mysql_db")
        return ProviderSpec(
            key="mysql",
            db_type="mysql",
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            username=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database,
            supports_idle=True,
            connection_id_sql="SELECT CONNECTION_ID()",
            table_name="test_users",
            index_name="idx_test_users_email",
            trigger_name="trg_test_users_audit",
        )
    if provider == "mariadb":
        database = request.getfixturevalue("mariadb_db")
        return ProviderSpec(
            key="mariadb",
            db_type="mariadb",
            host=MARIADB_HOST,
            port=MARIADB_PORT,
            username=MARIADB_USER,
            password=MARIADB_PASSWORD,
            database=database,
            supports_idle=True,
            connection_id_sql="SELECT CONNECTION_ID()",
            table_name="test_users",
            index_name="idx_test_users_email",
            trigger_name="trg_test_users_audit",
        )
    if provider == "mssql":
        database = request.getfixturevalue("mssql_db")
        return ProviderSpec(
            key="mssql",
            db_type="mssql",
            host=MSSQL_HOST,
            port=MSSQL_PORT,
            username=MSSQL_USER,
            password=MSSQL_PASSWORD,
            database=database,
            supports_idle=False,
            connection_id_sql="SELECT @@SPID",
            table_name="test_users",
            index_name="idx_test_users_email",
            trigger_name="trg_test_users_audit",
        )
    if provider == "postgres":
        database = request.getfixturevalue("postgres_db")
        return ProviderSpec(
            key="postgres",
            db_type="postgresql",
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            username=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=database,
            supports_idle=False,
            connection_id_sql="SELECT pg_backend_pid()",
            table_name="test_users",
            index_name="idx_test_users_email",
            trigger_name="trg_test_users_audit",
        )
    if provider == "oracle":
        database = request.getfixturevalue("oracle_db")
        return ProviderSpec(
            key="oracle",
            db_type="oracle",
            host=ORACLE_HOST,
            port=ORACLE_PORT,
            username=ORACLE_USER,
            password=ORACLE_PASSWORD,
            database=database,
            supports_idle=False,
            connection_id_sql="",
            table_name="TEST_USERS",
            index_name="IDX_TEST_USERS_EMAIL",
            trigger_name="TRG_TEST_USERS_AUDIT",
        )

    raise AssertionError(f"Unknown provider: {provider}")


def _build_connection_config(spec: ProviderSpec) -> ConnectionConfig:
    name = f"test-stale-{spec.key}-{os.getpid()}"

    if spec.key == "mssql":
        server = spec.host
        if spec.port and spec.port != 1433:
            server = f"{spec.host},{spec.port}"
        return ConnectionConfig(
            name=name,
            db_type=spec.db_type,
            server=server,
            port="",
            database="",
            username=spec.username,
            password=spec.password,
            options={"auth_type": "sql"},
        )

    if spec.key == "oracle":
        return ConnectionConfig(
            name=name,
            db_type=spec.db_type,
            server=spec.host,
            port=str(spec.port),
            database=spec.database,
            username=spec.username,
            password=spec.password,
        )

    return ConnectionConfig(
        name=name,
        db_type=spec.db_type,
        server=spec.host,
        port=str(spec.port),
        database="",
        username=spec.username,
        password=spec.password,
    )


def _has_column_children(node: Any) -> bool:
    return any(isinstance(child.data, ColumnNode) for child in node.children)


def _has_connected_tables_folder(app: SSMSTUI) -> bool:
    if app.current_config is None:
        return False
    connected_node = find_connection_node(app.object_tree.root, app.current_config.name)
    if connected_node is None:
        return False
    return find_folder_node(connected_node, "tables") is not None


async def _run_db_call(app: SSMSTUI, fn: Any, *args: Any) -> Any:
    session = getattr(app, "_session", None)
    if session is not None:
        return await session.executor.run_async(fn, *args)
    return await asyncio.to_thread(fn, *args)


def _execute_sql(conn: Any, sql: str, fetch_one: bool = False) -> Any:
    cursor = conn.cursor()
    cursor.execute(sql)
    if fetch_one:
        return cursor.fetchone()
    return None


def _close_db_connection(conn: Any) -> None:
    close_fn = getattr(conn, "close", None)
    if callable(close_fn):
        close_fn()


async def _set_wait_timeout(app: SSMSTUI, timeout_seconds: int) -> None:
    sql = f"SET SESSION wait_timeout = {timeout_seconds}"
    await _run_db_call(app, _execute_sql, app.current_connection, sql, False)


async def _get_connection_id(app: SSMSTUI, spec: ProviderSpec) -> int:
    row = await _run_db_call(app, _execute_sql, app.current_connection, spec.connection_id_sql, True)
    if not row:
        raise AssertionError("Failed to fetch connection id")
    return int(row[0])


async def _close_connection(app: SSMSTUI) -> None:
    conn = app.current_connection
    if conn is None:
        return
    await _run_db_call(app, _close_db_connection, conn)


async def _kill_connection(spec: ProviderSpec, connection_id: int) -> None:
    if spec.key == "mysql":
        try:
            import pymysql
        except ImportError:
            pytest.skip("PyMySQL is not installed")

        def work() -> None:
            conn = pymysql.connect(
                host=spec.host,
                port=int(spec.port),
                database=spec.database,
                user=spec.username,
                password=spec.password,
                connect_timeout=10,
            )
            try:
                cursor = conn.cursor()
                cursor.execute(f"KILL {connection_id}")
            finally:
                conn.close()

        await asyncio.to_thread(work)
        return

    if spec.key == "mariadb":
        try:
            import mariadb
        except ImportError:
            pytest.skip("mariadb is not installed")

        def work() -> None:
            conn = mariadb.connect(
                host=spec.host,
                port=int(spec.port),
                database=spec.database,
                user=spec.username,
                password=spec.password,
                connect_timeout=10,
            )
            try:
                cursor = conn.cursor()
                cursor.execute(f"KILL {connection_id}")
            finally:
                conn.close()

        await asyncio.to_thread(work)
        return

    if spec.key == "mssql":
        try:
            import mssql_python  # type: ignore[import]
        except ImportError:
            pytest.skip("mssql-python is not installed")

        def work() -> None:
            server = spec.host
            if spec.port and spec.port != 1433:
                server = f"{spec.host},{spec.port}"
            conn_str = (
                f"SERVER={server};"
                "DATABASE=master;"
                f"UID={spec.username};"
                f"PWD={spec.password};"
                "Encrypt=yes;TrustServerCertificate=yes;"
            )
            conn = mssql_python.connect(conn_str)
            conn.autocommit = True  # type: ignore[assignment]
            try:
                cursor = conn.cursor()
                cursor.execute(f"KILL {connection_id}")
            finally:
                conn.close()

        await asyncio.to_thread(work)
        return

    if spec.key == "postgres":
        try:
            import psycopg2
        except ImportError:
            pytest.skip("psycopg2 is not installed")

        def work() -> None:
            conn = psycopg2.connect(
                host=spec.host,
                port=spec.port,
                database=spec.database,
                user=spec.username,
                password=spec.password,
                connect_timeout=10,
            )
            conn.autocommit = True
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT pg_terminate_backend(%s)", (connection_id,))
            finally:
                conn.close()

        await asyncio.to_thread(work)
        return

    raise AssertionError(f"Unsupported provider: {spec.key}")


async def _wait_for_schema_idle(app: SSMSTUI, pilot: Any) -> None:
    await wait_for_condition(
        pilot,
        lambda: not getattr(app, "_schema_indexing", False),
        timeout_seconds=20.0,
        description="schema indexing to finish",
    )


async def _wait_for_folder_loaded(pilot: Any, node: Any, description: str) -> None:
    await wait_for_condition(
        pilot,
        lambda: not has_loading_children(node) and len(node.children) > 0,
        timeout_seconds=10.0,
        description=description,
    )


async def _wait_for_columns_loaded(pilot: Any, node: Any) -> None:
    await wait_for_condition(
        pilot,
        lambda: not has_loading_children(node) and _has_column_children(node),
        timeout_seconds=10.0,
        description="columns to load",
    )


async def _wait_for_autocomplete_columns(app: SSMSTUI, pilot: Any, table_key: str) -> None:
    await wait_for_condition(
        pilot,
        lambda: bool(app._schema_cache.get("columns", {}).get(table_key)),
        timeout_seconds=10.0,
        description="autocomplete columns to load",
    )


async def _make_connection_stale(
    app: SSMSTUI,
    pilot: Any,
    spec: ProviderSpec,
    stale_method: str,
) -> None:
    if stale_method == "idle":
        if not spec.supports_idle:
            raise AssertionError(f"Idle timeouts are not supported for {spec.key}")
        await _set_wait_timeout(app, 1)
        await pilot.pause(2.0)
        return
    if stale_method == "kill":
        if spec.key == "oracle":
            await _close_connection(app)
            await pilot.pause(0.5)
            return
        connection_id = await _get_connection_id(app, spec)
        await _kill_connection(spec, connection_id)
        await pilot.pause(0.5)
        return
    raise AssertionError(f"Unknown stale method: {stale_method}")


async def _connect_and_prepare_tree(
    app: SSMSTUI,
    pilot: Any,
    spec: ProviderSpec,
    *,
    load_indexes: bool = False,
    load_triggers: bool = False,
) -> tuple[Any, Any, Any, Any, Any]:
    config = _build_connection_config(spec)

    app.connections = [config]
    app.refresh_tree()
    await pilot.pause(0.1)

    await wait_for_condition(
        pilot,
        lambda: len(app.object_tree.root.children) > 0,
        timeout_seconds=5.0,
        description="tree to be populated with connections",
    )

    app.connect_to_server(config)
    await wait_for_condition(
        pilot,
        lambda: app.current_connection is not None,
        timeout_seconds=15.0,
        description="connection to be established",
    )

    connected_node = find_connection_node(app.object_tree.root, config.name)
    if connected_node is None:
        raise AssertionError("Connected node not found")

    supports_multiple = bool(
        app.current_provider and app.current_provider.capabilities.supports_multiple_databases
    )
    if supports_multiple:
        await wait_for_condition(
            pilot,
            lambda: find_database_node(app.object_tree.root, spec.database) is not None,
            timeout_seconds=10.0,
            description="database node to appear",
        )

        db_node = find_database_node(app.object_tree.root, spec.database)
        if db_node is None:
            raise AssertionError(f"Database node '{spec.database}' not found")

        db_node.expand()
        await pilot.pause(0.3)
    else:
        db_node = connected_node
        db_node.expand()
        await pilot.pause(0.3)

    tables_folder = find_folder_node(db_node, "tables")
    if tables_folder is None:
        raise AssertionError("Tables folder not found")

    tables_folder.expand()
    await pilot.pause(0.3)
    await _wait_for_folder_loaded(pilot, tables_folder, "tables to be loaded")

    table_node = find_table_node(tables_folder, spec.table_name)
    if table_node is None:
        raise AssertionError(f"{spec.table_name} table not found")

    index_node = None
    if load_indexes:
        indexes_folder = find_folder_node(db_node, "indexes")
        if indexes_folder is None:
            raise AssertionError("Indexes folder not found")
        indexes_folder.expand()
        await pilot.pause(0.3)
        await _wait_for_folder_loaded(pilot, indexes_folder, "indexes to be loaded")
        index_node = find_node_by_type(indexes_folder, IndexNode, spec.index_name)
        if index_node is None:
            raise AssertionError(f"{spec.index_name} index not found")

    trigger_node = None
    if load_triggers:
        triggers_folder = find_folder_node(db_node, "triggers")
        if triggers_folder is None:
            raise AssertionError("Triggers folder not found")
        triggers_folder.expand()
        await pilot.pause(0.3)
        await _wait_for_folder_loaded(pilot, triggers_folder, "triggers to be loaded")
        trigger_node = find_node_by_type(triggers_folder, TriggerNode, spec.trigger_name)
        if trigger_node is None:
            raise AssertionError(f"{spec.trigger_name} trigger not found")

    await _wait_for_schema_idle(app, pilot)

    return config, db_node, table_node, index_node, trigger_node


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_spec", PROVIDERS, indirect=True)
@pytest.mark.parametrize("stale_method", ["idle", "kill"])
async def test_columns_reconnect_after_stale_connection(
    provider_spec: ProviderSpec, stale_method: str
) -> None:
    if stale_method == "idle" and not provider_spec.supports_idle:
        pytest.skip("Idle timeout not supported for provider")

    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        _config, _db_node, table_node, _index_node, _trigger_node = await _connect_and_prepare_tree(
            app, pilot, provider_spec
        )

        await _make_connection_stale(app, pilot, provider_spec, stale_method)

        table_node.expand()
        await pilot.pause(0.2)

        await _wait_for_columns_loaded(pilot, table_node)
        assert _has_column_children(table_node)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_spec", PROVIDERS, indirect=True)
async def test_object_info_after_kill(provider_spec: ProviderSpec) -> None:
    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        _config, _db_node, _table_node, index_node, trigger_node = await _connect_and_prepare_tree(
            app, pilot, provider_spec, load_indexes=True, load_triggers=True
        )

        if index_node is None or trigger_node is None:
            raise AssertionError("Expected index and trigger nodes")

        await _make_connection_stale(app, pilot, provider_spec, "kill")

        app.object_tree.move_cursor(index_node)
        app.action_select_table()
        await pilot.pause(0.2)
        assert app._last_result_columns == ["Property", "Value"]

        app.object_tree.move_cursor(trigger_node)
        app.action_select_table()
        await pilot.pause(0.2)
        assert app._last_result_columns == ["Property", "Value"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_spec", PROVIDERS, indirect=True)
async def test_autocomplete_columns_after_kill(provider_spec: ProviderSpec) -> None:
    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        await _connect_and_prepare_tree(app, pilot, provider_spec)

        table_key = provider_spec.table_name.lower()
        if table_key not in app._table_metadata:
            raise AssertionError(f"Expected table metadata to include {table_key}")
        app._schema_cache.get("columns", {}).pop(table_key, None)

        await _make_connection_stale(app, pilot, provider_spec, "kill")

        app._load_columns_for_table(table_key)
        await _wait_for_autocomplete_columns(app, pilot, table_key)

        columns = app._schema_cache.get("columns", {}).get(table_key, [])
        assert columns


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_spec", PROVIDERS, indirect=True)
async def test_table_selection_after_kill(provider_spec: ProviderSpec) -> None:
    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        _config, _db_node, table_node, _index_node, _trigger_node = await _connect_and_prepare_tree(
            app, pilot, provider_spec
        )

        await _make_connection_stale(app, pilot, provider_spec, "kill")

        app.object_tree.move_cursor(table_node)
        app.action_select_table()
        await pilot.pause(0.2)

        last_table = app._last_query_table
        assert last_table is not None
        assert last_table.get("columns")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_spec", PROVIDERS, indirect=True)
async def test_refresh_tree_after_kill(provider_spec: ProviderSpec) -> None:
    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        await _connect_and_prepare_tree(app, pilot, provider_spec)

        await _make_connection_stale(app, pilot, provider_spec, "kill")

        app.action_refresh_tree()
        await wait_for_condition(
            pilot,
            lambda: (
                find_database_node(app.object_tree.root, provider_spec.database) is not None
                or _has_connected_tables_folder(app)
            ),
            timeout_seconds=10.0,
            description="tree to show databases or tables after refresh",
        )
