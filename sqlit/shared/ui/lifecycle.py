"""Lifecycle hooks for cross-mixin communication.

This module provides a clean way for mixins to react to lifecycle events
(like connect/disconnect) without tight coupling between mixins.

Usage:
    class MyMixin(LifecycleHooksMixin):
        def _on_disconnect(self) -> None:
            super()._on_disconnect()
            # Clean up my state
            self._my_cache = None

Important: Always call super()._on_<event>() to ensure all mixins in the
chain receive the event.
"""

from __future__ import annotations


class LifecycleHooksMixin:
    """Base mixin providing lifecycle hook methods.

    Mixins that need to react to lifecycle events should:
    1. Override the relevant _on_* method
    2. Call super()._on_*() first to propagate to other mixins
    3. Perform their cleanup/setup

    Available hooks:
    - _on_disconnect: Called when disconnecting from a database
    - _on_connect: Called after successfully connecting to a database
    """

    def _on_disconnect(self) -> None:
        """Called when disconnecting from a database.

        Override this method to clean up connection-specific state.
        Always call super()._on_disconnect() first.
        """
        pass

    def _on_connect(self) -> None:
        """Called after successfully connecting to a database.

        Override this method to initialize connection-specific state.
        Always call super()._on_connect() first.
        """
        pass
