"""Shared helpers for query editing mixins."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingCommonMixin:
    """Common helper methods for query editing."""

    def _clear_leader_pending(self: QueryMixinHost) -> None:
        """Clear any leader pending state if supported by the host."""
        cancel = getattr(self, "_cancel_leader_pending", None)
        if callable(cancel):
            cancel()
