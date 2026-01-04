"""Integration tests for UI stalls during connection flows."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from textual.widgets import OptionList

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.explorer.ui.tree import builder as tree_builder
from sqlit.domains.query.store.history import QueryHistoryEntry
from sqlit.domains.query.ui.screens.query_history import QueryHistoryScreen
from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.app.runtime import RuntimeConfig

TARGET_CONNECTION = "timebestillerserver/Timebestiller"
TARGET_QUERY = "select * from auditlogs"
EXPLORER_WATCHDOG_MS = 500.0
TELESCOPE_WATCHDOG_MS = 500.0
TIMEOUT_S = 30.0
STALL_WINDOW_S = 10.0


def _real_config_dir() -> Path:
    return Path.home() / ".sqlit"


def _watchdog_path(app: SSMSTUI) -> Path:
    return getattr(app, "_ui_stall_watchdog_log_path", _real_config_dir() / "ui_stall_watchdog.txt")


def _connections_path() -> Path:
    return _real_config_dir() / "connections.json"


def _history_path() -> Path:
    return _real_config_dir() / "query_history.json"


def _load_real_connections() -> list[ConnectionConfig]:
    path = _connections_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_connections: list[dict]
    if isinstance(payload, list):
        raw_connections = payload
    elif isinstance(payload, dict):
        raw_connections = payload.get("connections", []) if isinstance(payload.get("connections"), list) else []
    else:
        return []
    configs: list[ConnectionConfig] = []
    for raw in raw_connections:
        if not isinstance(raw, dict):
            continue
        try:
            configs.append(ConnectionConfig.from_dict(raw))
        except Exception:
            continue
    return configs


class FileHistoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _load_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def load_all(self) -> list[QueryHistoryEntry]:
        entries: list[QueryHistoryEntry] = []
        for raw in self._load_raw():
            if not isinstance(raw, dict):
                continue
            try:
                entries.append(QueryHistoryEntry.from_dict(raw))
            except Exception:
                continue
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def load_for_connection(self, connection_name: str) -> list[QueryHistoryEntry]:
        return [entry for entry in self.load_all() if entry.connection_name == connection_name]

    def save_query(self, connection_name: str, query: str) -> None:
        _ = connection_name
        _ = query


def _read_new_watchdog_lines(path: Path, offset: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        return [line.strip() for line in handle if line.strip()]


def _max_stall_ms(lines: list[str], *, ignore_connect: bool = False) -> float:
    pattern = re.compile(r"\]\s+([0-9.]+)\s+ms")
    max_ms = 0.0
    for line in lines:
        if ignore_connect and "connect=1" in line:
            continue
        match = pattern.search(line)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        max_ms = max(max_ms, value)
    return max_ms


def _get_history_index(screen: QueryHistoryScreen) -> int | None:
    entries = getattr(screen, "_merged_entries", None) or []
    if not entries:
        try:
            entries = screen._merge_entries()
        except Exception:
            return None
    for idx, entry in enumerate(entries):
        try:
            query = (entry.query or "").lower()
            conn = entry.connection_name
        except Exception:
            continue
        if TARGET_QUERY in query and conn == TARGET_CONNECTION:
            return idx
    return None


async def _wait_for_connection(app: SSMSTUI, pilot, *, timeout_s: float) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if app.current_config and app.current_config.name == TARGET_CONNECTION:
            if getattr(app, "_connecting_config", None) is None:
                return True
        await pilot.pause(0.2)
    return False


async def _wait_for_connection_node(app: SSMSTUI, pilot, *, timeout_s: float) -> Any | None:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        for candidate in app.object_tree.root.children:
            data = getattr(candidate, "data", None)
            config = getattr(data, "config", None)
            if config and config.name == TARGET_CONNECTION:
                return candidate
        tree_builder.refresh_tree(app)
        await pilot.pause(0.2)
    return None


async def _wait_for_query_text(app: SSMSTUI, pilot, *, timeout_s: float) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        try:
            query_text = app.query_input.text
        except Exception:
            query_text = ""
        if TARGET_QUERY in query_text.lower():
            return True
        await pilot.pause(0.1)
    return False


@pytest.mark.integration
@pytest.mark.mssql
@pytest.mark.asyncio
async def test_explorer_connect_no_stall() -> None:
    """Explorer connection should not trigger a UI stall."""
    runtime = RuntimeConfig.from_env()
    runtime.process_worker = True
    runtime.process_worker_warm_on_idle = False
    app = SSMSTUI(runtime=runtime)
    log_path = _watchdog_path(app)
    offset = log_path.stat().st_size if log_path.exists() else 0
    connections = _load_real_connections()
    if not any(conn.name == TARGET_CONNECTION for conn in connections):
        pytest.skip(f"Missing connection: {TARGET_CONNECTION}")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)

        app.connections = connections
        tree_builder.refresh_tree(app)
        await pilot.pause(0.2)

        node = await _wait_for_connection_node(app, pilot, timeout_s=5.0)
        if node is None:
            pytest.skip(f"Missing connection in tree: {TARGET_CONNECTION}")

        app.services.runtime.ui_stall_watchdog_ms = EXPLORER_WATCHDOG_MS
        app._start_ui_stall_watchdog()

        app.object_tree.move_cursor(node)
        app.action_connect_selected()

        if not await _wait_for_connection(app, pilot, timeout_s=TIMEOUT_S):
            pytest.fail(f"Failed to connect to {TARGET_CONNECTION}")

        await pilot.pause(0.5)
        app.exit()

    lines = _read_new_watchdog_lines(log_path, offset)
    max_ms = _max_stall_ms(lines)
    assert max_ms <= EXPLORER_WATCHDOG_MS, f"Explorer connect stall {max_ms:.1f} ms"


@pytest.mark.integration
@pytest.mark.mssql
@pytest.mark.asyncio
async def test_telescope_query_no_stall() -> None:
    """Telescope history selection should not stall the UI."""
    runtime = RuntimeConfig.from_env()
    runtime.process_worker = True
    runtime.process_worker_warm_on_idle = False
    app = SSMSTUI(runtime=runtime)
    log_path = _watchdog_path(app)
    offset = log_path.stat().st_size if log_path.exists() else 0
    connections = _load_real_connections()
    if not any(conn.name == TARGET_CONNECTION for conn in connections):
        pytest.skip(f"Missing connection: {TARGET_CONNECTION}")
    history_store = FileHistoryStore(_history_path())
    history_entries = history_store.load_all()
    if not any(
        entry.connection_name == TARGET_CONNECTION and TARGET_QUERY in entry.query.lower()
        for entry in history_entries
    ):
        pytest.skip("Target history entry not found")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)

        app.services.runtime.ui_stall_watchdog_ms = TELESCOPE_WATCHDOG_MS
        app._start_ui_stall_watchdog()

        app.connections = connections
        app._history_store = history_store
        app.services.history_store = history_store

        app.action_telescope()
        await pilot.pause(0.5)

        screen = next(
            (s for s in app.screen_stack if isinstance(s, QueryHistoryScreen)),
            None,
        )
        if screen is None:
            pytest.fail("Telescope screen not found")

        idx = _get_history_index(screen)
        if idx is None:
            pytest.skip("Target history entry not found")

        option_list = screen.query_one("#history-list", OptionList)
        option_list.highlighted = idx
        option_list.focus()
        await pilot.pause(0.2)
        await pilot.press("enter")
        await pilot.pause(0.2)

        if not await _wait_for_query_text(app, pilot, timeout_s=TIMEOUT_S):
            pytest.fail("Telescope query not populated in time")

        await pilot.pause(STALL_WINDOW_S)
        app.exit()

    lines = _read_new_watchdog_lines(log_path, offset)
    max_ms = _max_stall_ms(lines, ignore_connect=True)
    assert max_ms <= TELESCOPE_WATCHDOG_MS, f"Telescope query stalled {max_ms:.1f} ms"
