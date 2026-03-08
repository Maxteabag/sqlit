"""Protocol for lifecycle hooks."""

from __future__ import annotations

from typing import Protocol


class LifecycleProtocol(Protocol):
    """Protocol for lifecycle hook methods.

    Mixins implementing lifecycle hooks should define these methods.
    """

    def _on_disconnect(self) -> None:
        """Called when disconnecting from a database."""
        ...

    def _on_connect(self) -> None:
        """Called after successfully connecting to a database."""
        ...
