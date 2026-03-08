"""State models for the connection picker screen."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlit.domains.connections.discovery.cloud import ProviderState
    from sqlit.domains.connections.discovery.docker_detector import DetectedContainer


@dataclass
class FilterState:
    active: bool = False
    text: str = ""


@dataclass
class DockerState:
    containers: list[DetectedContainer] = field(default_factory=list)
    status_message: str | None = None
    loading: bool = False


@dataclass
class CloudState:
    states: dict[str, ProviderState] = field(default_factory=dict)
    loading_databases: set[str] = field(default_factory=set)
