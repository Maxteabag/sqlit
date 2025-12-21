"""Application services for sqlit.

This package provides shared business logic used by both the TUI and CLI,
ensuring consistent behavior across interfaces.

Services:
- QueryService: Unified query execution with history tracking
- ConnectionSession: Connection lifecycle management with cleanup guarantees
- DatabaseExecutor: Serialized database operation execution
- CredentialsService: Secure credential storage using OS keyring

Protocols:
- AdapterProtocol: Interface for database adapters
- HistoryStoreProtocol: Interface for query history storage
- ConnectionStoreProtocol: Interface for connection storage
- SettingsStoreProtocol: Interface for settings storage
"""

from .cancellable import CancellableQuery
from .credentials import (
    CredentialsService,
    KeyringCredentialsService,
    PlaintextCredentialsService,
    get_credentials_service,
    reset_credentials_service,
    set_credentials_service,
)
from .docker_detector import (
    ContainerStatus,
    DetectedContainer,
    DockerStatus,
    container_to_connection_config,
    detect_database_containers,
    get_docker_status,
)
from .executor import DatabaseExecutor
from .protocols import (
    AdapterFactoryProtocol,
    AdapterProtocol,
    ConnectionStoreProtocol,
    HistoryStoreProtocol,
    SettingsStoreProtocol,
    TunnelFactoryProtocol,
)
from .query import NonQueryResult, QueryResult, QueryService, is_select_query
from .session import ConnectionSession

__all__ = [
    # Query service
    "QueryService",
    "QueryResult",
    "NonQueryResult",
    "is_select_query",
    # Session
    "ConnectionSession",
    # Executor
    "DatabaseExecutor",
    # Cancellable query
    "CancellableQuery",
    # Credentials service
    "CredentialsService",
    "KeyringCredentialsService",
    "PlaintextCredentialsService",
    "get_credentials_service",
    "set_credentials_service",
    "reset_credentials_service",
    # Docker detection
    "ContainerStatus",
    "DockerStatus",
    "DetectedContainer",
    "get_docker_status",
    "detect_database_containers",
    "container_to_connection_config",
    # Protocols
    "AdapterProtocol",
    "AdapterFactoryProtocol",
    "HistoryStoreProtocol",
    "TunnelFactoryProtocol",
    "ConnectionStoreProtocol",
    "SettingsStoreProtocol",
]
