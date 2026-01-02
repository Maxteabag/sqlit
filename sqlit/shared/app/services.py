"""Service container and builders for sqlit."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.driver import (
    ConfigurableDriverResolver,
    DefaultDriverResolver,
    DriverResolver,
    attach_driver_resolver,
)
from sqlit.shared.app.runtime import RuntimeConfig
from sqlit.shared.core.processes import (
    AsyncProcessRunner,
    AsyncSubprocessRunner,
    FixedResultAsyncRunner,
    FixedResultSyncRunner,
    SubprocessRunner,
    SyncProcessRunner,
)
from sqlit.shared.core.protocols import (
    ConnectionStoreProtocol,
    HistoryStoreProtocol,
    ProviderFactoryProtocol,
    SettingsStoreProtocol,
    TunnelFactoryProtocol,
)
from sqlit.shared.core.system_probe import SystemProbe, SystemProbeProtocol

if TYPE_CHECKING:
    pass


@dataclass
class ProviderFactoryWithResolver:
    base_factory: ProviderFactoryProtocol
    resolver: DriverResolver

    def __call__(self, db_type: str) -> Any:
        provider = self.base_factory(db_type)
        attach_driver_resolver(provider, self.resolver)
        return provider

    def set_resolver(self, resolver: DriverResolver) -> None:
        self.resolver = resolver

    def set_base_factory(self, factory: ProviderFactoryProtocol) -> None:
        self.base_factory = factory


def _wrap_provider_factory(factory: ProviderFactoryProtocol, resolver: DriverResolver) -> ProviderFactoryProtocol:
    if isinstance(factory, ProviderFactoryWithResolver):
        factory.set_resolver(resolver)
        return factory
    return ProviderFactoryWithResolver(factory, resolver)


def _normalize_install_method_hint(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"pipx", "pip", "unknown", "uvx", "uv", "conda"}:
        return normalized
    return None


def build_system_probe(runtime: RuntimeConfig, *, base_probe: SystemProbeProtocol | None = None) -> SystemProbeProtocol:
    base_probe = base_probe or SystemProbe()
    hint = _normalize_install_method_hint(runtime.mock.pipx_mode)
    overrides: dict[str, Any] = {}
    if hint:
        overrides["install_method"] = hint
    if runtime.mock.pipx_mode == "no-pip":
        overrides["pip_available"] = False
    if not overrides:
        return base_probe

    from sqlit.shared.core.system_probe_fake import FakeSystemProbe

    return FakeSystemProbe.from_probe(base_probe, **overrides)


def build_driver_resolver(runtime: RuntimeConfig) -> DriverResolver:
    requested = runtime.mock.missing_drivers or set()
    missing = {item.strip().lower() for item in requested if item and item.strip()}
    force_import_error = bool(runtime.mock.driver_error)
    skip_checks = bool(runtime.mock.enabled) and not missing and not force_import_error
    if missing or force_import_error or skip_checks:
        return ConfigurableDriverResolver(
            missing_db_types=missing,
            force_import_error=force_import_error,
            skip_checks=skip_checks,
        )
    return DefaultDriverResolver()


def build_process_runners(
    runtime: RuntimeConfig,
    *,
    sync_runner: SyncProcessRunner | None = None,
    async_runner: AsyncProcessRunner | None = None,
) -> tuple[SyncProcessRunner, AsyncProcessRunner]:
    install_result = (runtime.mock.install_result or "").strip().lower()
    if install_result in {"success", "ok", "pass"}:
        return (
            FixedResultSyncRunner(returncode=0, stdout="Mocked install succeeded."),
            FixedResultAsyncRunner(returncode=0, lines=["Mocked install succeeded.", "Done"]),
        )
    if install_result in {"fail", "error"}:
        return (
            FixedResultSyncRunner(returncode=1, stderr="Mocked install failed."),
            FixedResultAsyncRunner(returncode=1, lines=["Mocked install failed.", "Done"]),
        )
    return sync_runner or SubprocessRunner(), async_runner or AsyncSubprocessRunner()


@dataclass
class AppServices:
    """Container for runtime services and factories."""

    runtime: RuntimeConfig
    system_probe: SystemProbeProtocol
    connection_store: ConnectionStoreProtocol
    settings_store: SettingsStoreProtocol
    history_store: HistoryStoreProtocol
    starred_store: Any
    credentials_service: Any
    provider_factory: ProviderFactoryProtocol
    driver_resolver: DriverResolver
    tunnel_factory: TunnelFactoryProtocol
    session_factory: Callable[[Any], Any]
    docker_detector: Callable[[], tuple[Any, list[Any]]]
    cloud_discovery: CloudDiscovery
    install_strategy: InstallStrategyProvider
    sync_process_runner: SyncProcessRunner
    async_process_runner: AsyncProcessRunner

    def apply_mock_profile(self, profile: Any | None) -> None:
        """Switch services into/out of mock profile mode."""
        from sqlit.domains.connections.app.credentials import PlaintextCredentialsService
        from sqlit.domains.connections.app.session import ConnectionSession
        from sqlit.domains.connections.app.tunnel import create_noop_tunnel
        from sqlit.domains.connections.store.memory import InMemoryConnectionStore
        from sqlit.domains.query.store.memory import InMemoryHistoryStore, InMemoryStarredStore

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
        self.refresh_runtime_services()

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
        self.refresh_runtime_services()

    def refresh_runtime_services(self) -> None:
        """Rebuild runtime-derived services after mock settings change."""
        self.system_probe = build_system_probe(self.runtime)
        setter = getattr(self.install_strategy, "set_probe", None)
        if callable(setter):
            setter(self.system_probe)

        self.driver_resolver = build_driver_resolver(self.runtime)
        self.provider_factory = _wrap_provider_factory(self.provider_factory, self.driver_resolver)
        from sqlit.domains.connections.discovery.docker_detector import (
            DockerContainerScanner,
            StaticDockerContainerScanner,
        )
        if isinstance(self.docker_detector, (DockerContainerScanner, StaticDockerContainerScanner)):
            self.docker_detector = build_docker_detector(self.runtime)
        cloud_state_provider = build_cloud_state_provider(self.runtime)
        setter = getattr(self.cloud_discovery, "set_state_provider", None)
        if callable(setter):
            setter(cloud_state_provider)
        self.sync_process_runner, self.async_process_runner = build_process_runners(
            self.runtime,
            sync_runner=self.sync_process_runner,
            async_runner=self.async_process_runner,
        )


def build_app_services(
    runtime: RuntimeConfig,
    *,
    connection_store: ConnectionStoreProtocol | None = None,
    settings_store: SettingsStoreProtocol | None = None,
    history_store: HistoryStoreProtocol | None = None,
    starred_store: Any | None = None,
    credentials_service: Any | None = None,
    provider_factory: ProviderFactoryProtocol | None = None,
    system_probe: SystemProbeProtocol | None = None,
    driver_resolver: DriverResolver | None = None,
    tunnel_factory: TunnelFactoryProtocol | None = None,
    session_factory: Callable[[Any], Any] | None = None,
    docker_detector: Callable[[], tuple[Any, list[Any]]] | None = None,
    cloud_discovery: CloudDiscovery | None = None,
    install_strategy: InstallStrategyProvider | None = None,
    sync_process_runner: SyncProcessRunner | None = None,
    async_process_runner: AsyncProcessRunner | None = None,
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
    from sqlit.shared.app.startup_profiler import configure as configure_startup_profiler
    from sqlit.shared.app.startup_profiler import enable_import_timing
    from sqlit.shared.app.startup_profiler import span as startup_span

    configure_startup_profiler(
        log_path=runtime.startup_log_path,
        start_mark=runtime.startup_mark,
        init_mark=runtime.startup_mark,
    )
    enable_import_timing(
        log_path=runtime.startup_import_log_path,
        min_ms=runtime.startup_import_min_ms,
    )

    with startup_span("build_settings_store"):
        settings_store = settings_store or SettingsStore(file_path=runtime.settings_path)
    with startup_span("build_credentials_service"):
        credentials_service = credentials_service or build_credentials_service(settings_store)
    if credentials_service is None:
        raise RuntimeError("Credentials service is not available.")
    with startup_span("build_connection_store"):
        connection_store = connection_store or ConnectionStore(credentials_service=credentials_service)
    with startup_span("build_history_store"):
        history_store = history_store or HistoryStore()
    with startup_span("build_starred_store"):
        starred_store = starred_store or StarredStore()

    if hasattr(connection_store, "set_credentials_service"):
        connection_store.set_credentials_service(credentials_service)

    with startup_span("build_system_probe"):
        system_probe = system_probe or build_system_probe(runtime)
    with startup_span("build_driver_resolver"):
        driver_resolver = driver_resolver or build_driver_resolver(runtime)
    with startup_span("build_provider_factory"):
        provider_factory = _wrap_provider_factory(provider_factory or get_provider, driver_resolver)
    with startup_span("build_tunnel_factory"):
        tunnel_factory = tunnel_factory or create_ssh_tunnel
    with startup_span("build_process_runners"):
        sync_process_runner, async_process_runner = build_process_runners(
            runtime,
            sync_runner=sync_process_runner,
            async_runner=async_process_runner,
        )

    if session_factory is None:
        def _default_session_factory(config: Any) -> Any:
            return ConnectionSession.create(
                config,
                provider_factory=provider_factory,
                tunnel_factory=tunnel_factory,
            )
        session_factory = _default_session_factory

    if install_strategy is not None:
        setter = getattr(install_strategy, "set_probe", None)
        if callable(setter):
            setter(system_probe)

    with startup_span("build_cloud_state_provider"):
        cloud_state_provider = build_cloud_state_provider(runtime)
    if cloud_discovery is not None:
        setter = getattr(cloud_discovery, "set_state_provider", None)
        if callable(setter):
            setter(cloud_state_provider)

    with startup_span("build_docker_detector"):
        docker_detector = docker_detector or build_docker_detector(runtime)
    with startup_span("build_cloud_discovery"):
        cloud_discovery = cloud_discovery or CloudDiscovery(cloud_state_provider)
    with startup_span("build_install_strategy"):
        install_strategy = install_strategy or InstallStrategyProvider(system_probe)

    services = AppServices(
        runtime=runtime,
        system_probe=system_probe,
        connection_store=connection_store,
        settings_store=settings_store,
        history_store=history_store,
        starred_store=starred_store,
        credentials_service=credentials_service,
        provider_factory=provider_factory,
        driver_resolver=driver_resolver,
        tunnel_factory=tunnel_factory,
        session_factory=session_factory,
        docker_detector=docker_detector,
        cloud_discovery=cloud_discovery,
        install_strategy=install_strategy,
        sync_process_runner=sync_process_runner,
        async_process_runner=async_process_runner,
    )

    if runtime.mock.profile is not None:
        runtime.mock.profile.query_delay = runtime.mock.query_delay
        runtime.mock.profile.demo_rows = runtime.mock.demo_rows
        runtime.mock.profile.demo_long_text = runtime.mock.demo_long_text
        services.apply_mock_profile(runtime.mock.profile)
    return services


def build_docker_detector(runtime: RuntimeConfig) -> Callable[[], tuple[Any, list[Any]]]:
    """Create a docker detector callable for the current runtime."""
    from sqlit.domains.connections.discovery.docker_detector import (
        DockerContainerScanner,
        StaticDockerContainerScanner,
    )

    containers = runtime.mock.docker_containers
    if containers is not None:
        return StaticDockerContainerScanner(containers)
    return DockerContainerScanner()


CloudStateProvider = Callable[[list[Any]], dict[str, Any] | None]


class EmptyCloudStateProvider:
    def __call__(self, providers: list[Any]) -> dict[str, Any] | None:
        return None


class MockCloudStateProvider:
    def __call__(self, providers: list[Any]) -> dict[str, Any] | None:
        from sqlit.domains.connections.discovery.cloud.mock import get_mock_cloud_states

        states = get_mock_cloud_states()
        return {p.id: states[p.id] for p in providers if p.id in states}


def build_cloud_state_provider(runtime: RuntimeConfig) -> CloudStateProvider:
    if runtime.mock.cloud:
        return MockCloudStateProvider()
    return EmptyCloudStateProvider()


class CloudDiscovery:
    """Cloud discovery helper with injectable state providers."""

    def __init__(self, state_provider: CloudStateProvider | None = None) -> None:
        self._state_provider = state_provider or EmptyCloudStateProvider()

    def set_state_provider(self, state_provider: CloudStateProvider) -> None:
        self._state_provider = state_provider

    def load_seed_states(self, providers: list[Any]) -> dict[str, Any] | None:
        return self._state_provider(providers)

    def discover(self, provider: Any, state: Any) -> Any:
        return provider.discover(state)


class InstallStrategyProvider:
    """Install strategy helper using an injected system probe."""

    def __init__(self, probe: SystemProbeProtocol) -> None:
        self._probe = probe

    def set_probe(self, probe: SystemProbeProtocol) -> None:
        self._probe = probe

    def detect(self, *, extra_name: str, package_name: str) -> Any:
        from sqlit.domains.connections.app.install_strategy import detect_strategy

        return detect_strategy(
            extra_name=extra_name,
            package_name=package_name,
            probe=self._probe,
        )

    def detect_install_method(self) -> str:
        from sqlit.domains.connections.app.install_strategy import detect_install_method

        return detect_install_method(
            probe=self._probe,
        )

    def get_install_options(self, *, extra_name: str | None, package_name: str) -> list[Any]:
        from sqlit.domains.connections.app.install_strategy import get_install_options

        return get_install_options(
            package_name=package_name,
            extra_name=extra_name,
            probe=self._probe,
        )

    def format_manual_instructions(self, *, extra_name: str | None, package_name: str, reason: str) -> str:
        from sqlit.domains.connections.app.install_strategy import _format_manual_instructions

        return _format_manual_instructions(
            package_name=package_name,
            extra_name=extra_name,
            reason=reason,
            probe=self._probe,
        )
