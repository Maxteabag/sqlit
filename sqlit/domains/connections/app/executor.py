"""Database operation executor with connection serialization.

This module provides a DatabaseExecutor that serializes all database
operations for a connection session, ensuring thread-safe access to
database connections that may not support concurrent operations.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .session import ConnectionSession

T = TypeVar("T")


class DatabaseExecutor:
    """Serializes database operations for a connection session.

    All operations are submitted to a single-thread executor to ensure
    only one operation runs at a time on the connection. This prevents
    race conditions and ensures thread-safety for database drivers that
    don't support concurrent operations on a single connection.

    Usage:
        # Synchronous submission (returns Future)
        future = executor.submit(adapter.get_tables, connection, database)
        result = future.result()

        # Async usage (in async context)
        result = await executor.run_async(adapter.get_tables, connection, database)

    Attributes:
        session: The ConnectionSession this executor is bound to.
    """

    def __init__(self, session: ConnectionSession):
        """Initialize the executor.

        Args:
            session: The ConnectionSession this executor is bound to.
        """
        self._session = session
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="sqlit-db-",
        )
        self._lock = threading.Lock()
        self._current_future: Future | None = None
        self._shutdown = False

    @property
    def session(self) -> ConnectionSession:
        """Get the session this executor is bound to."""
        return self._session

    @property
    def is_shutdown(self) -> bool:
        """Check if the executor has been shut down."""
        return self._shutdown

    def submit(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
        """Submit an operation to the executor.

        Operations are serialized - only one runs at a time on the
        single-thread executor.

        Args:
            fn: The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            A Future that will contain the result.

        Raises:
            RuntimeError: If the executor has been shut down.
        """
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Executor has been shut down")
            future = self._executor.submit(fn, *args, **kwargs)
            self._current_future = future
            return future

    async def run_async(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run an operation and await the result.

        This is a convenience method for use in async contexts. It submits
        the operation to the executor and awaits the result.

        Args:
            fn: The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function.

        Raises:
            RuntimeError: If the executor has been shut down.
            Any exception raised by the function.
        """
        loop = asyncio.get_running_loop()
        future = self.submit(fn, *args, **kwargs)
        return await loop.run_in_executor(None, future.result)

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor.

        After shutdown, no new operations can be submitted.

        Args:
            wait: If True, wait for pending operations to complete.
                  If False, cancel pending operations immediately.
        """
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True

        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def __del__(self) -> None:
        """Destructor to ensure cleanup."""
        if not self._shutdown:
            self.shutdown(wait=False)
