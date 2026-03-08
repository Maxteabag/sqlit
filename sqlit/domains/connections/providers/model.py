"""Core provider model and capability protocols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.providers.docker import DockerDetector
    from sqlit.domains.connections.providers.driver import DriverDescriptor
    from sqlit.domains.connections.providers.explorer_nodes import ExplorerNodeProvider
    from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema


@dataclass(frozen=True)
class ProviderMetadata:
    db_type: str
    display_name: str
    badge_label: str
    default_port: str
    supports_ssh: bool
    is_file_based: bool
    has_advanced_auth: bool
    requires_auth: bool
    url_schemes: tuple[str, ...]


@dataclass(frozen=True)
class SchemaCapabilities:
    supports_multiple_databases: bool
    supports_cross_database_queries: bool
    supports_stored_procedures: bool
    supports_indexes: bool
    supports_triggers: bool
    supports_sequences: bool
    default_schema: str
    system_databases: frozenset[str]


@runtime_checkable
class ConnectionFactory(Protocol):
    def connect(self, config: ConnectionConfig) -> Any: ...


@runtime_checkable
class QueryExecutor(Protocol):
    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        ...

    def execute_non_query(self, conn: Any, query: str) -> int: ...


@runtime_checkable
class Dialect(Protocol):
    def quote_identifier(self, name: str) -> str: ...

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        ...

    def format_table_name(self, schema: str | None, table: str) -> str: ...


@runtime_checkable
class SchemaInspector(Protocol):
    def get_databases(self, conn: Any) -> list[str]: ...

    def get_tables(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]: ...

    def get_views(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]: ...

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[Any]:
        ...


@runtime_checkable
class IndexInspector(Protocol):
    def get_indexes(self, conn: Any, database: str | None = None) -> list[Any]: ...

    def get_index_definition(self, conn: Any, index_name: str, table_name: str, database: str | None = None) -> dict[str, Any]:
        ...


@runtime_checkable
class TriggerInspector(Protocol):
    def get_triggers(self, conn: Any, database: str | None = None) -> list[Any]: ...

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        ...


@runtime_checkable
class SequenceInspector(Protocol):
    def get_sequences(self, conn: Any, database: str | None = None) -> list[Any]: ...

    def get_sequence_definition(self, conn: Any, sequence_name: str, database: str | None = None) -> dict[str, Any]:
        ...


@runtime_checkable
@runtime_checkable
class ProcedureInspector(Protocol):
    def get_procedures(self, conn: Any, database: str | None = None) -> list[Any]: ...


class ConfigValidator(Protocol):
    def normalize(self, config: ConnectionConfig) -> ConnectionConfig: ...

    def validate(self, config: ConnectionConfig) -> None: ...


@dataclass(frozen=True)
class ProviderSpec:
    db_type: str
    display_name: str
    schema_path: tuple[str, str]
    supports_ssh: bool = True
    is_file_based: bool = False
    has_advanced_auth: bool = False
    default_port: str = ""
    requires_auth: bool = True
    badge_label: str = ""
    url_schemes: tuple[str, ...] = ()
    docker_detector: DockerDetector | None = None
    display_info: Callable[[ConnectionConfig], str] | None = None
    provider_factory: Callable[[ProviderSpec], DatabaseProvider] | None = None


@dataclass
class DatabaseProvider:
    metadata: ProviderMetadata
    schema: ConnectionSchema
    capabilities: SchemaCapabilities
    driver: DriverDescriptor | None
    connection_factory: ConnectionFactory
    query_executor: QueryExecutor
    schema_inspector: SchemaInspector
    dialect: Dialect
    config_validator: ConfigValidator
    docker_detector: DockerDetector | None
    explorer_nodes: ExplorerNodeProvider
    display_info: Callable[[ConnectionConfig], str]
    apply_database_override: Callable[[ConnectionConfig, str | None], ConnectionConfig]
    post_connect: Callable[[Any, ConnectionConfig], None]
    post_connect_warnings: Callable[[ConnectionConfig], list[str]]
    get_auth_type: Callable[[ConnectionConfig], Any | None]
