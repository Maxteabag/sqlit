"""Shared node metadata for cloud tree rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CloudNodeData:
    provider_id: str
    option_id: str | None = None
