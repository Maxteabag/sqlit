"""Service container and builders for sqlit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlit.shared.app.runtime import RuntimeConfig
from sqlit.shared.core.protocols import (
    ConnectionStoreProtocol,
    HistoryStoreProtocol,
    ProviderFactoryProtocol,
    SettingsStoreProtocol,
    TunnelFactoryProtocol,
)


@dataclass
class AppServices:
    """Container for runtime services and factories."""

    runtime: RuntimeConfig
    connection_store: ConnectionStoreProtocol
    settings_store: SettingsStoreProtocol
    history_store: HistoryStoreProtocol
    starred_store: Any
    credentials_service: Any
    provider_factory: ProviderFactoryProtocol
    tunnel_factory: TunnelFactoryProtocol
    session_factory: Callable[[Any], Any]
    docker_detector: Callable[[], tuple[Any, list[Any]]]
    cloud_discovery: "CloudDiscovery"
    install_strategy: "InstallStrategyProvider"

    def apply_mock_profile(self, profile: Any | None) -> None:
        """Switch services into/out of mock profile mode."""
        from sqlit.domains.connections.app.credentials import PlaintextCredentialsService
        from sqlit.domains.connections.store.memory import InMemoryConnectionStore
        from sqlit.domains.connections.app.session import ConnectionSession
        from sqlit.domains.connections.app.tunnel import create_noop_tunnel
        from sqlit.domains.query.store.memory import InMemoryHistoryStore
        from sqlit.domains.query.store.memory import InMemoryStarredStore

        self.runtime.mock.profile = profile
        self.runtime.mock.enabled = bool(profile)

        if profile is None:
            return

        profile.query_delay = self.runtime.mock.query_delay
        profile.demo_rows = self.runtime.mock.demo_rows
        profile.demo_long_text = self.runtime.mock.demo_long_text

        self.credentials_service = PlaintextCredentialsService()
        self.connection_store = InMemoryConnectionStore(profile.connections)
        self.provider_factory = profile.get_provider
        self.tunnel_factory = create_noop_tunnel
        self.session_factory = lambda config: ConnectionSession.create(
            config,
            provider_factory=self.provider_factory,
            tunnel_factory=self.tunnel_factory,
        )
        self.history_store = InMemoryHistoryStore()
        self.starred_store = InMemoryStarredStore()

    def apply_mock_settings(self, settings: dict[str, Any]) -> None:
        """Apply mock settings from settings.json into runtime/services."""
        from sqlit.domains.connections.app.mock_settings import parse_mock_settings

        mock_settings = parse_mock_settings(settings)
        if mock_settings is None:
            return

        self.runtime.mock.enabled = True
        self.runtime.mock.missing_drivers = mock_settings.missing_drivers
        self.runtime.mock.install_result = mock_settings.install_result
        self.runtime.mock.pipx_mode = mock_settings.pipx_mode
        self.runtime.mock.docker_containers = mock_settings.docker_containers

        if mock_settings.profile is not None:
            self.apply_mock_profile(mock_settings.profile)


def build_app_services(
    runtime: RuntimeConfig,
    *,
    connection_store: ConnectionStoreProtocol | None = None,
    settings_store: SettingsStoreProtocol | None = None,
    history_store: HistoryStoreProtocol | None = None,
    starred_store: Any | None = None,
    credentials_service: Any | None = None,
    provider_factory: ProviderFactoryProtocol | None = None,
    tunnel_factory: TunnelFactoryProtocol | None = None,
    session_factory: Callable[[Any], Any] | None = None,
    docker_detector: Callable[[], tuple[Any, list[Any]]] | None = None,
    cloud_discovery: CloudDiscovery | None = None,
    install_strategy: InstallStrategyProvider | None = None,
) -> AppServices:
    """Build the default service container for the app."""
    from sqlit.domains.connections.app.credentials import build_credentials_service
    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.app.tunnel import create_ssh_tunnel
    from sqlit.domains.connections.providers.catalog import get_provider
    from sqlit.domains.connections.store.connections import ConnectionStore
    from sqlit.domains.query.store.history import HistoryStore
    from sqlit.domains.query.store.starred import StarredStore
    from sqlit.domains.shell.store.settings import SettingsStore

    settings_store = settings_store or SettingsStore(file_path=runtime.settings_path)
    credentials_service = credentials_service or build_credentials_service(settings_store)
    connection_store = connection_store or ConnectionStore(credentials_service=credentials_service)
    history_store = history_store or HistoryStore()
    starred_store = starred_store or StarredStore()

    if hasattr(connection_store, "set_credentials_service"):
        connection_store.set_credentials_service(credentials_service)

    provider_factory = provider_factory or get_provider
    tunnel_factory = tunnel_factory or create_ssh_tunnel

    if session_factory is None:
        session_factory = lambda config: ConnectionSession.create(
            config,
            provider_factory=provider_factory,
            tunnel_factory=tunnel_factory,
        )

    services = AppServices(
        runtime=runtime,
        connection_store=connection_store,
        settings_store=settings_store,
        history_store=history_store,
        starred_store=starred_store,
        credentials_service=credentials_service,
        provider_factory=provider_factory,
        tunnel_factory=tunnel_factory,
        session_factory=session_factory,
        docker_detector=docker_detector or build_docker_detector(runtime),
        cloud_discovery=cloud_discovery or CloudDiscovery(runtime),
        install_strategy=install_strategy or InstallStrategyProvider(runtime),
    )

    if runtime.mock.profile is not None:
        runtime.mock.profile.query_delay = runtime.mock.query_delay
        runtime.mock.profile.demo_rows = runtime.mock.demo_rows
        runtime.mock.profile.demo_long_text = runtime.mock.demo_long_text
        services.apply_mock_profile(runtime.mock.profile)
    return services


def build_docker_detector(runtime: RuntimeConfig) -> Callable[[], tuple[Any, list[Any]]]:
    """Create a docker detector callable respecting runtime mock settings."""
    def detect() -> tuple[Any, list[Any]]:
        from sqlit.domains.connections.discovery.docker_detector import detect_database_containers

        return detect_database_containers(mock_containers=runtime.mock.docker_containers)

    return detect


class CloudDiscovery:
    """Cloud discovery helper honoring runtime mock settings."""

    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime

    def load_mock_states(self, providers: list[Any]) -> dict[str, Any] | None:
        if not self._runtime.mock.cloud:
            return None
        from sqlit.domains.connections.discovery.cloud.mock import get_mock_cloud_states

        states = get_mock_cloud_states()
        return {p.id: states[p.id] for p in providers if p.id in states}

    def discover(self, provider: Any, state: Any) -> Any:
        return provider.discover(state)


class InstallStrategyProvider:
    """Install strategy helper honoring runtime mock settings."""

    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime

    def detect(self, *, extra_name: str, package_name: str) -> Any:
        from sqlit.domains.connections.app.install_strategy import detect_strategy

        return detect_strategy(
            extra_name=extra_name,
            package_name=package_name,
            mock_pipx=self._runtime.mock.pipx_mode,
            mock_no_pip=self._runtime.mock.pipx_mode == "no-pip",
            mock_driver_error=self._runtime.mock.driver_error,
        )
