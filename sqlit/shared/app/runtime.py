"""Runtime configuration for sqlit."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os


@dataclass
class MockConfig:
    """Mock-related runtime configuration."""

    enabled: bool = False
    profile: Any | None = None
    missing_drivers: set[str] = field(default_factory=set)
    install_result: str | None = None
    pipx_mode: str | None = None
    query_delay: float = 0.0
    demo_rows: int = 0
    demo_long_text: bool = False
    cloud: bool = False
    docker_containers: list[Any] | None = None
    driver_error: bool = False


@dataclass
class RuntimeConfig:
    """Runtime configuration provided by CLI or tests."""

    settings_path: Path | None = None
    max_rows: int | None = None
    debug_mode: bool = False
    debug_idle_scheduler: bool = False
    profile_startup: bool = False
    startup_mark: float | None = None
    mock: MockConfig = field(default_factory=MockConfig)

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        def _parse_startup_mark(value: str | None) -> float | None:
            if not value:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _parse_int(value: str | None) -> int | None:
            if not value:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def _parse_float(value: str | None) -> float:
            if not value:
                return 0.0
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        settings_path = os.environ.get("SQLIT_SETTINGS_PATH", "").strip() or None
        max_rows = _parse_int(os.environ.get("SQLIT_MAX_ROWS"))
        missing_drivers = os.environ.get("SQLIT_MOCK_MISSING_DRIVERS", "")
        missing_driver_set = {item.strip() for item in missing_drivers.split(",") if item.strip()}

        mock_config = MockConfig(
            missing_drivers=missing_driver_set,
            install_result=os.environ.get("SQLIT_MOCK_INSTALL_RESULT", "").strip().lower() or None,
            pipx_mode=os.environ.get("SQLIT_MOCK_PIPX", "").strip().lower() or None,
            query_delay=_parse_float(os.environ.get("SQLIT_MOCK_QUERY_DELAY")),
            demo_rows=_parse_int(os.environ.get("SQLIT_DEMO_ROWS")) or 0,
            demo_long_text=os.environ.get("SQLIT_DEMO_LONG_TEXT") == "1",
            cloud=os.environ.get("SQLIT_MOCK_CLOUD") == "1",
            driver_error=os.environ.get("SQLIT_MOCK_DRIVER_ERROR") == "1",
        )

        return cls(
            settings_path=Path(settings_path).expanduser() if settings_path else None,
            max_rows=max_rows,
            debug_mode=os.environ.get("SQLIT_DEBUG") == "1",
            debug_idle_scheduler=os.environ.get("SQLIT_DEBUG_IDLE_SCHEDULER") == "1",
            profile_startup=os.environ.get("SQLIT_PROFILE_STARTUP") == "1",
            startup_mark=_parse_startup_mark(os.environ.get("SQLIT_STARTUP_MARK")),
            mock=mock_config,
        )
