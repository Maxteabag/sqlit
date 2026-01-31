"""Schema data access for explorer UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlit.domains.connections.app.session import ConnectionSession
from sqlit.domains.connections.providers.adapters.base import ColumnInfo
from sqlit.domains.connections.providers.model import (
    IndexInspector,
    ProcedureInspector,
    SequenceInspector,
    TriggerInspector,
)

DbArgResolver = Callable[[str | None], str | None]
ReconnectFn = Callable[[str | None], bool]
ResultT = TypeVar("ResultT")


@dataclass
class ExplorerSchemaService:
    session: ConnectionSession
    object_cache: dict[str, dict[str, Any]]
    db_arg_resolver: DbArgResolver | None = None
    reconnect: ReconnectFn | None = None

    def _resolve_db_arg(self, database: str | None) -> str | None:
        if self.db_arg_resolver:
            return self.db_arg_resolver(database)
        return database

    def _run(self, fn: Callable[[], ResultT]) -> ResultT:
        return self.session.executor.submit(fn).result()

    def _resolve_reconnect_db(self, database: str | None) -> str | None:
        if database:
            return database
        endpoint = self.session.config.tcp_endpoint
        if endpoint and endpoint.database:
            return endpoint.database
        return database

    def _reconnect(self, database: str | None) -> bool:
        target_db = self._resolve_reconnect_db(database)
        if self.reconnect is not None:
            if self.reconnect(target_db):
                self.object_cache.clear()
                return True
            return False
        if not self.session.config.tcp_endpoint:
            return False
        try:
            self.session.switch_database(target_db or "")
            self.object_cache.clear()
            return True
        except Exception:
            return False

    def _run_with_retry(self, fn: Callable[[], ResultT], database: str | None) -> ResultT:
        try:
            return self._run(fn)
        except Exception:
            if not self._reconnect(database):
                raise
        return self._run(fn)

    def list_databases(self) -> list[str]:
        inspector = self.session.provider.schema_inspector
        return self._run_with_retry(
            lambda: inspector.get_databases(self.session.connection),
            None,
        )

    def list_columns(
        self,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> list[ColumnInfo]:
        inspector = self.session.provider.schema_inspector
        db_arg = self._resolve_db_arg(database)
        return self._run_with_retry(
            lambda: inspector.get_columns(self.session.connection, name, db_arg, schema),
            database,
        )

    def list_folder_items(self, folder_type: str, database: str | None) -> list[Any]:
        inspector = self.session.provider.schema_inspector
        caps = self.session.provider.capabilities
        db_arg = self._resolve_db_arg(database)
        cache_key = database or "__default__"
        obj_cache = self.object_cache

        def cached(key: str, loader: Callable[[], Any], *, allow_empty: bool = True) -> Any:
            if cache_key in obj_cache and key in obj_cache[cache_key]:
                data = obj_cache[cache_key][key]
                if allow_empty or data:
                    return data
            data = loader()
            if cache_key not in obj_cache:
                obj_cache[cache_key] = {}
            obj_cache[cache_key][key] = data
            return data

        if folder_type == "tables":
            raw_data = cached(
                "tables",
                lambda: self._run_with_retry(
                    lambda: inspector.get_tables(self.session.connection, db_arg),
                    database,
                ),
                allow_empty=self.session.provider.metadata.db_type != "duckdb",
            )
            return [("table", schema, name) for schema, name in raw_data]
        if folder_type == "views":
            raw_data = cached(
                "views",
                lambda: self._run_with_retry(
                    lambda: inspector.get_views(self.session.connection, db_arg),
                    database,
                ),
                allow_empty=self.session.provider.metadata.db_type != "duckdb",
            )
            return [("view", schema, name) for schema, name in raw_data]
        if folder_type == "databases":
            raw_data = cached(
                "databases",
                lambda: self._run_with_retry(
                    lambda: inspector.get_databases(self.session.connection),
                    None,
                ),
            )
            return list(raw_data)
        if folder_type == "indexes":
            if caps.supports_indexes and isinstance(inspector, IndexInspector):
                return [
                    ("index", item.name, item.table_name)
                    for item in self._run_with_retry(
                        lambda: inspector.get_indexes(self.session.connection, db_arg),
                        database,
                    )
                ]
            return []
        if folder_type == "triggers":
            if caps.supports_triggers and isinstance(inspector, TriggerInspector):
                return [
                    ("trigger", item.name, item.table_name)
                    for item in self._run_with_retry(
                        lambda: inspector.get_triggers(self.session.connection, db_arg),
                        database,
                    )
                ]
            return []
        if folder_type == "sequences":
            if caps.supports_sequences and isinstance(inspector, SequenceInspector):
                return [
                    ("sequence", item.name, "")
                    for item in self._run_with_retry(
                        lambda: inspector.get_sequences(self.session.connection, db_arg),
                        database,
                    )
                ]
            return []
        if folder_type == "procedures":
            if caps.supports_stored_procedures and isinstance(inspector, ProcedureInspector):
                raw_data = cached(
                    "procedures",
                    lambda: self._run_with_retry(
                        lambda: inspector.get_procedures(self.session.connection, db_arg),
                        database,
                    ),
                )
                return [("procedure", "", name) for name in raw_data]
            return []
        return []

    def get_index_definition(self, database: str | None, name: str, table_name: str) -> dict[str, Any] | None:
        inspector = self.session.provider.schema_inspector
        if not isinstance(inspector, IndexInspector):
            return None
        db_arg = self._resolve_db_arg(database)
        return self._run_with_retry(
            lambda: inspector.get_index_definition(self.session.connection, name, table_name, db_arg),
            database,
        )

    def get_trigger_definition(self, database: str | None, name: str, table_name: str) -> dict[str, Any] | None:
        inspector = self.session.provider.schema_inspector
        if not isinstance(inspector, TriggerInspector):
            return None
        db_arg = self._resolve_db_arg(database)
        return self._run_with_retry(
            lambda: inspector.get_trigger_definition(self.session.connection, name, table_name, db_arg),
            database,
        )

    def get_sequence_definition(self, database: str | None, name: str) -> dict[str, Any] | None:
        inspector = self.session.provider.schema_inspector
        if not isinstance(inspector, SequenceInspector):
            return None
        db_arg = self._resolve_db_arg(database)
        return self._run_with_retry(
            lambda: inspector.get_sequence_definition(self.session.connection, name, db_arg),
            database,
        )
