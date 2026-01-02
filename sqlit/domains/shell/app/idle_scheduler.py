"""Idle scheduler - execute work when the user isn't interacting.

Inspired by browser's requestIdleCallback API. Queues up work and executes it
during idle periods to avoid UI hiccups.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sqlit.shared.ui.protocols import AppProtocol


class Priority(Enum):
    """Job priority levels."""
    LOW = auto()      # Can wait indefinitely
    NORMAL = auto()   # Should run soon-ish
    HIGH = auto()     # Run at next idle opportunity


@dataclass
class IdleJob:
    """A unit of work to execute during idle time."""
    callback: Callable[[], Any] | Callable[[], Coroutine[Any, Any, Any]]
    priority: Priority = Priority.NORMAL
    is_async: bool = False
    name: str = ""
    created_at: float = field(default_factory=time.time)

    def __lt__(self, other: IdleJob) -> bool:
        # Higher priority first, then older jobs first
        if self.priority != other.priority:
            return self.priority.value > other.priority.value
        return self.created_at < other.created_at


class IdleScheduler:
    """Schedules work to run during user idle periods.

    Usage:
        scheduler = IdleScheduler(app)
        scheduler.start()

        # Queue work
        scheduler.request_idle_callback(lambda: print("doing work"))

        # Or with async
        scheduler.request_idle_callback(async_func, is_async=True)

        # Call this on any user interaction
        scheduler.on_user_activity()
    """

    def __init__(
        self,
        app: AppProtocol,
        idle_threshold_ms: float = 500,      # Consider idle after 500ms of no activity
        max_work_chunk_ms: float = 16,       # Max time to work before checking for activity (~1 frame)
        check_interval_ms: float = 150,      # How often to check if we should work
        max_queue_size: int = 1000,          # Prevent unbounded growth
    ) -> None:
        self.app = app
        self.idle_threshold_ms = idle_threshold_ms
        self.max_work_chunk_ms = max_work_chunk_ms
        self.check_interval_ms = check_interval_ms
        self.max_queue_size = max_queue_size

        self._queue: deque[IdleJob] = deque()
        self._last_activity_time: float = time.time()
        self._running = False
        self._timer: Any = None
        self._paused = False

        # Stats for debugging
        self._jobs_completed = 0
        self._jobs_dropped = 0
        self._total_work_time_ms = 0.0

    @property
    def is_idle(self) -> bool:
        """Check if user is considered idle."""
        elapsed_ms = (time.time() - self._last_activity_time) * 1000
        return elapsed_ms >= self.idle_threshold_ms

    @property
    def time_until_idle_ms(self) -> float:
        """Time remaining until user is considered idle."""
        elapsed_ms = (time.time() - self._last_activity_time) * 1000
        return max(0, self.idle_threshold_ms - elapsed_ms)

    @property
    def pending_jobs(self) -> int:
        """Number of jobs waiting to be executed."""
        return len(self._queue)

    def on_user_activity(self) -> None:
        """Call this whenever the user interacts with the app.

        Should be hooked into key presses, mouse events, etc.
        """
        self._last_activity_time = time.time()

    def request_idle_callback(
        self,
        callback: Callable[[], Any] | Callable[[], Coroutine[Any, Any, Any]],
        priority: Priority = Priority.NORMAL,
        is_async: bool = False,
        name: str = "",
    ) -> bool:
        """Queue a callback to run during idle time.

        Args:
            callback: Function to execute (sync or async)
            priority: Job priority (HIGH runs first)
            is_async: True if callback is an async function
            name: Optional name for debugging

        Returns:
            True if queued, False if queue is full
        """
        if len(self._queue) >= self.max_queue_size:
            self._jobs_dropped += 1
            return False

        job = IdleJob(
            callback=callback,
            priority=priority,
            is_async=is_async,
            name=name,
        )

        # Insert maintaining priority order
        # For simplicity, just append and sort when executing
        self._queue.append(job)
        return True

    def cancel_all(self, name: str | None = None) -> int:
        """Cancel pending jobs.

        Args:
            name: If provided, only cancel jobs with this name.
                  If None, cancel all jobs.

        Returns:
            Number of jobs cancelled
        """
        if name is None:
            count = len(self._queue)
            self._queue.clear()
            return count

        original_len = len(self._queue)
        self._queue = deque(job for job in self._queue if job.name != name)
        return original_len - len(self._queue)

    def start(self) -> None:
        """Start the idle scheduler."""
        if self._running:
            return
        self._running = True
        self._schedule_check()

    def stop(self) -> None:
        """Stop the idle scheduler."""
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer = None

    def pause(self) -> None:
        """Temporarily pause processing (queue still accepts jobs)."""
        self._paused = True

    def resume(self) -> None:
        """Resume processing after pause."""
        self._paused = False

    def _schedule_check(self) -> None:
        """Schedule the next idle check."""
        if not self._running:
            return

        # Use Textual's timer
        delay = self.check_interval_ms / 1000
        self._timer = self.app.set_timer(delay, self._check_and_work)

    def _check_and_work(self) -> None:
        """Check if idle and do work if so."""
        if not self._running or self._paused:
            self._schedule_check()
            return

        if not self._queue:
            self._schedule_check()
            return

        if not self.is_idle:
            # User is active, wait until they're idle
            self._schedule_check()
            return

        # We're idle! Do some work
        self._do_work_chunk()

        # Schedule next check
        self._schedule_check()

    def _do_work_chunk(self) -> None:
        """Execute jobs for up to max_work_chunk_ms."""
        start_time = time.time()
        max_time = self.max_work_chunk_ms / 1000

        # Sort queue by priority (do this lazily)
        sorted_jobs = sorted(self._queue)
        self._queue = deque(sorted_jobs)

        while self._queue:
            # Check if we've exceeded our time budget
            elapsed = time.time() - start_time
            if elapsed >= max_time:
                break

            # Check if user became active
            if not self.is_idle:
                break

            # Execute next job
            job = self._queue.popleft()
            try:
                if job.is_async:
                    # Schedule async job to run
                    self.app.call_later(self._run_async_job, job)
                else:
                    job.callback()
                self._jobs_completed += 1
            except Exception as e:
                # Log but don't crash
                self.app.log.error(f"IdleScheduler job failed: {job.name or 'unnamed'}: {e}")

        # Track stats
        self._total_work_time_ms += (time.time() - start_time) * 1000

        # Refresh status bar if debug mode is on
        if hasattr(self.app, "_debug_idle_scheduler") and self.app._debug_idle_scheduler:
            if hasattr(self.app, "_update_status_bar"):
                self.app._update_status_bar()

    async def _run_async_job(self, job: IdleJob) -> None:
        """Run an async job."""
        try:
            callback = cast(Callable[[], Coroutine[Any, Any, Any]], job.callback)
            await callback()
            self._jobs_completed += 1
        except Exception as e:
            self.app.log.error(f"IdleScheduler async job failed: {job.name or 'unnamed'}: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get scheduler statistics for debugging."""
        return {
            "pending_jobs": len(self._queue),
            "jobs_completed": self._jobs_completed,
            "jobs_dropped": self._jobs_dropped,
            "total_work_time_ms": round(self._total_work_time_ms, 2),
            "is_idle": self.is_idle,
            "time_until_idle_ms": round(self.time_until_idle_ms, 2),
            "is_running": self._running,
            "is_paused": self._paused,
        }


# Convenience function for simple usage
_global_scheduler: IdleScheduler | None = None


def get_idle_scheduler() -> IdleScheduler | None:
    """Get the global idle scheduler instance."""
    return _global_scheduler


def init_idle_scheduler(app: AppProtocol, **kwargs: Any) -> IdleScheduler:
    """Initialize the global idle scheduler."""
    global _global_scheduler
    _global_scheduler = IdleScheduler(app, **kwargs)
    return _global_scheduler


def request_idle_callback(
    callback: Callable[[], Any],
    priority: Priority = Priority.NORMAL,
    is_async: bool = False,
    name: str = "",
) -> bool:
    """Queue a callback to run during idle time (uses global scheduler).

    Returns False if no scheduler is initialized or queue is full.
    """
    if _global_scheduler is None:
        return False
    return _global_scheduler.request_idle_callback(callback, priority, is_async, name)


def on_user_activity() -> None:
    """Signal user activity (uses global scheduler)."""
    if _global_scheduler:
        _global_scheduler.on_user_activity()
