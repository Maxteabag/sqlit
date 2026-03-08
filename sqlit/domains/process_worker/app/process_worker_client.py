"""Process-based query execution client."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from multiprocessing import get_context
import os
import sys
from multiprocessing.connection import Connection
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.query.app.query_service import NonQueryResult, QueryResult
from sqlit.domains.connections.providers.adapters.base import ColumnInfo

from .process_worker import run_process_worker


@dataclass
class ProcessQueryOutcome:
    """Outcome for a process-executed query."""

    result: QueryResult | NonQueryResult | None
    elapsed_ms: float
    cancelled: bool = False
    error: str | None = None


class ProcessWorkerClient:
    """Runs queries in a separate process."""

    def __init__(self) -> None:
        self._conn: Connection | None = None
        self._process = None
        try:
            self._start_with_context(get_context("spawn"))
        except Exception as exc:
            self._maybe_fallback_start(exc)
        self._send_lock = threading.Lock()
        self._execute_lock = threading.Lock()
        self._next_id = 1
        self._closed = False
        self._current_id: int | None = None
        if self._conn is None or self._process is None:
            raise RuntimeError("Failed to start process worker.")

    def _start_with_context(self, ctx: Any) -> None:
        parent_conn, child_conn = ctx.Pipe(duplex=True)
        self._conn = parent_conn
        self._process = ctx.Process(
            target=run_process_worker,
            args=(child_conn,),
            daemon=True,
        )
        self._process.start()

    def _maybe_fallback_start(self, error: Exception) -> None:
        if not isinstance(error, ValueError):
            raise error
        message = str(error)
        if "fds_to_keep" not in message:
            raise error
        if os.name != "posix" or sys.platform.startswith("win"):
            raise error
        try:
            self._start_with_context(get_context("fork"))
        except Exception:
            raise error

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._send({"type": "shutdown"})
        except Exception:
            pass
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        if self._process is not None:
            if self._process.is_alive():
                self._process.join(timeout=1)
            if self._process.is_alive():
                self._process.terminate()

    def cancel_current(self) -> None:
        query_id = self._current_id
        if query_id is None:
            return
        try:
            self._send({"type": "cancel", "id": query_id})
        except Exception:
            pass

    def execute(self, query: str, config: ConnectionConfig, max_rows: int | None) -> ProcessQueryOutcome:
        with self._execute_lock:
            if self._closed:
                return ProcessQueryOutcome(result=None, elapsed_ms=0, error="Worker is closed.")

            query_id = self._next_id
            self._next_id += 1
            self._current_id = query_id

            payload = {
                "type": "exec",
                "id": query_id,
                "query": query,
                "config": config.to_dict(include_passwords=True),
                "db_type": config.db_type,
                "max_rows": max_rows,
            }
            self._send(payload)

            try:
                while True:
                    try:
                        message = self._conn.recv()
                    except EOFError:
                        return ProcessQueryOutcome(result=None, elapsed_ms=0, error="Worker connection closed.")
                    if message.get("id") != query_id:
                        continue
                    msg_type = message.get("type")
                    if msg_type == "result":
                        return ProcessQueryOutcome(
                            result=message.get("result"),
                            elapsed_ms=float(message.get("elapsed_ms", 0)),
                        )
                    if msg_type == "cancelled":
                        return ProcessQueryOutcome(result=None, elapsed_ms=0, cancelled=True)
                    if msg_type == "error":
                        return ProcessQueryOutcome(
                            result=None,
                            elapsed_ms=0,
                            error=str(message.get("message", "Worker error.")),
                        )
            finally:
                self._current_id = None

    def list_columns(
        self,
        *,
        config: ConnectionConfig,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> ProcessSchemaOutcome:
        with self._execute_lock:
            if self._closed:
                return ProcessSchemaOutcome(columns=None, error="Worker is closed.")

            query_id = self._next_id
            self._next_id += 1
            self._current_id = query_id

            payload = {
                "type": "schema",
                "op": "columns",
                "id": query_id,
                "config": config.to_dict(include_passwords=True),
                "db_type": config.db_type,
                "database": database,
                "schema": schema,
                "name": name,
            }
            self._send(payload)

            try:
                while True:
                    try:
                        message = self._conn.recv()
                    except EOFError:
                        return ProcessSchemaOutcome(columns=None, error="Worker connection closed.")
                    if message.get("id") != query_id:
                        continue
                    msg_type = message.get("type")
                    if msg_type == "schema" and message.get("op") == "columns":
                        columns = message.get("columns")
                        if isinstance(columns, list):
                            return ProcessSchemaOutcome(columns=columns)
                        return ProcessSchemaOutcome(columns=[])
                    if msg_type == "cancelled":
                        return ProcessSchemaOutcome(columns=None, cancelled=True)
                    if msg_type == "error":
                        return ProcessSchemaOutcome(
                            columns=None,
                            error=str(message.get("message", "Worker error.")),
                        )
            finally:
                self._current_id = None

    def list_folder_items(
        self,
        *,
        config: ConnectionConfig,
        database: str | None,
        folder_type: str,
    ) -> ProcessFolderOutcome:
        with self._execute_lock:
            if self._closed:
                return ProcessFolderOutcome(items=None, error="Worker is closed.")

            query_id = self._next_id
            self._next_id += 1
            self._current_id = query_id

            payload = {
                "type": "schema",
                "op": "folder_items",
                "id": query_id,
                "config": config.to_dict(include_passwords=True),
                "db_type": config.db_type,
                "database": database,
                "folder_type": folder_type,
            }
            self._send(payload)

            try:
                while True:
                    try:
                        message = self._conn.recv()
                    except EOFError:
                        return ProcessFolderOutcome(items=None, error="Worker connection closed.")
                    if message.get("id") != query_id:
                        continue
                    msg_type = message.get("type")
                    if msg_type == "schema" and message.get("op") == "folder_items":
                        items = message.get("items")
                        if isinstance(items, list):
                            return ProcessFolderOutcome(items=items)
                        return ProcessFolderOutcome(items=[])
                    if msg_type == "cancelled":
                        return ProcessFolderOutcome(items=None, cancelled=True)
                    if msg_type == "error":
                        return ProcessFolderOutcome(
                            items=None,
                            error=str(message.get("message", "Worker error.")),
                        )
            finally:
                self._current_id = None

    def _send(self, payload: dict[str, Any]) -> None:
        with self._send_lock:
            if self._conn is None:
                raise RuntimeError("Worker connection unavailable.")
            self._conn.send(payload)


@dataclass
class ProcessSchemaOutcome:
    """Outcome for a process-executed schema request."""

    columns: list[ColumnInfo] | None
    cancelled: bool = False
    error: str | None = None


@dataclass
class ProcessFolderOutcome:
    """Outcome for a process-executed folder listing request."""

    items: list[Any] | None
    cancelled: bool = False
    error: str | None = None
