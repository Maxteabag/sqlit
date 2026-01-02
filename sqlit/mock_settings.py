"""Legacy mock settings module - re-exports from new location.

This module exists for backwards compatibility with tests that import from
sqlit.mock_settings. The actual implementation is now in
sqlit.domains.connections.app.mock_settings.

The global mock docker containers approach has been replaced by
runtime.mock.docker_containers, so set_mock_docker_containers is a no-op.
"""

from sqlit.domains.connections.app.mock_settings import (
    MockSettings,
    build_mock_profile_from_settings,
    parse_mock_settings,
)
from sqlit.domains.connections.discovery.docker_detector import DetectedContainer

__all__ = [
    "MockSettings",
    "build_mock_profile_from_settings",
    "parse_mock_settings",
    "set_mock_docker_containers",
    "get_mock_docker_containers",
    "DetectedContainer",
]


def set_mock_docker_containers(containers: list[DetectedContainer] | None) -> None:
    """No-op for backwards compatibility.

    Mock docker containers are now stored in runtime.mock.docker_containers,
    not as a global variable.
    """
    pass


def get_mock_docker_containers() -> list[DetectedContainer] | None:
    """Returns None for backwards compatibility.

    Mock docker containers are now stored in runtime.mock.docker_containers,
    not as a global variable.
    """
    return None
