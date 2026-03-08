"""Process worker lifecycle helpers."""

from __future__ import annotations

from typing import Any

from sqlit.shared.ui.lifecycle import LifecycleHooksMixin
from sqlit.shared.ui.protocols import QueryMixinHost


class ProcessWorkerLifecycleMixin(LifecycleHooksMixin):
    """Shared process worker lifecycle helpers."""

    _process_worker_client: Any | None = None
    _process_worker_client_error: str | None = None
    _process_worker_last_used: float | None = None
    _process_worker_idle_timer: Any | None = None

    def _use_process_worker(self: QueryMixinHost, provider: Any) -> bool:
        runtime = getattr(self.services, "runtime", None)
        if not runtime or not getattr(runtime, "process_worker", False):
            return False
        if bool(getattr(getattr(runtime, "mock", None), "enabled", False)):
            return False
        try:
            from sqlit.domains.process_worker.app.support import supports_process_worker
        except Exception:
            return True
        return supports_process_worker(provider)

    def _get_process_worker_client(self: QueryMixinHost) -> Any | None:
        client = getattr(self, "_process_worker_client", None)
        if client is not None:
            try:
                from sqlit.shared.core.debug_events import emit_debug_event

                emit_debug_event(
                    "process_worker.use",
                    category="process_worker",
                    cached=True,
                    path="sync",
                )
            except Exception:
                pass
            self._touch_process_worker()
            return client
        start = None
        try:
            from sqlit.domains.process_worker.app.process_worker_client import ProcessWorkerClient
            from sqlit.shared.core.debug_events import emit_debug_event
            import time

            start = time.perf_counter()
            client = ProcessWorkerClient()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            emit_debug_event(
                "process_worker.startup",
                category="process_worker",
                method="main-thread",
                elapsed_ms=elapsed_ms,
                success=True,
            )
            emit_debug_event(
                "process_worker.use",
                category="process_worker",
                cached=False,
                path="sync",
            )
            self._process_worker_client = client
            self._process_worker_client_error = None
            self._touch_process_worker()
            return client
        except Exception as exc:
            try:
                from sqlit.shared.core.debug_events import emit_debug_event
                import time

                elapsed_ms = (time.perf_counter() - start) * 1000.0 if start is not None else None
                emit_debug_event(
                    "process_worker.startup",
                    category="process_worker",
                    method="main-thread",
                    elapsed_ms=elapsed_ms,
                    success=False,
                    error=str(exc),
                )
            except Exception:
                pass
            self._process_worker_client_error = str(exc)
            try:
                self.log.error(f"Failed to start process worker: {exc}")
            except Exception:
                pass
            return None

    async def _get_process_worker_client_async(self: QueryMixinHost) -> Any | None:
        import asyncio
        import sys

        client = getattr(self, "_process_worker_client", None)
        if client is not None:
            try:
                from sqlit.shared.core.debug_events import emit_debug_event

                emit_debug_event(
                    "process_worker.use",
                    category="process_worker",
                    cached=True,
                    path="async",
                )
            except Exception:
                pass
            self._touch_process_worker()
            return client
        start = None
        try:
            from sqlit.domains.process_worker.app.process_worker_client import ProcessWorkerClient
            from sqlit.shared.core.debug_events import emit_debug_event
            import time

            start = time.perf_counter()
            if sys.platform == "darwin":
                # Avoid forking from a background thread on macOS; it can crash pre-exec.
                client = ProcessWorkerClient()
                method = "main-thread"
            else:
                client = await asyncio.to_thread(ProcessWorkerClient)
                method = "to-thread"
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            emit_debug_event(
                "process_worker.startup",
                category="process_worker",
                method=method,
                elapsed_ms=elapsed_ms,
                success=True,
            )
            emit_debug_event(
                "process_worker.use",
                category="process_worker",
                cached=False,
                path="async",
            )
            self._process_worker_client = client
            self._process_worker_client_error = None
            self._touch_process_worker()
            return client
        except Exception as exc:
            try:
                from sqlit.shared.core.debug_events import emit_debug_event
                import time

                elapsed_ms = (time.perf_counter() - start) * 1000.0 if start is not None else None
                emit_debug_event(
                    "process_worker.startup",
                    category="process_worker",
                    method="main-thread",
                    elapsed_ms=elapsed_ms,
                    success=False,
                    error=str(exc),
                )
            except Exception:
                pass
            self._process_worker_client_error = str(exc)
            try:
                self.log.error(f"Failed to start process worker: {exc}")
            except Exception:
                pass
            return None

    def _close_process_worker_client(self: QueryMixinHost) -> None:
        client = getattr(self, "_process_worker_client", None)
        if client is None:
            return
        try:
            client.close()
        except Exception:
            pass
        self._process_worker_client = None
        self._clear_process_worker_auto_shutdown()

    def _close_process_worker_client_async(self: QueryMixinHost) -> None:
        client = getattr(self, "_process_worker_client", None)
        if client is None:
            return
        self._process_worker_client = None
        self._clear_process_worker_auto_shutdown()

        def work() -> None:
            try:
                client.close()
            except Exception:
                pass

        try:
            self.run_worker(work, name="close-process-worker", thread=True, exclusive=False)
        except Exception:
            try:
                client.close()
            except Exception:
                pass

    def _touch_process_worker(self: QueryMixinHost) -> None:
        import time

        self._process_worker_last_used = time.monotonic()
        self._arm_process_worker_auto_shutdown()

    def _clear_process_worker_auto_shutdown(self: QueryMixinHost) -> None:
        timer = getattr(self, "_process_worker_idle_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._process_worker_idle_timer = None

    def _arm_process_worker_auto_shutdown(self: QueryMixinHost) -> None:
        import time

        runtime = getattr(self.services, "runtime", None)
        if runtime is None:
            return
        auto_seconds = float(getattr(runtime, "process_worker_auto_shutdown_s", 0) or 0)
        if auto_seconds <= 0:
            self._clear_process_worker_auto_shutdown()
            return

        self._clear_process_worker_auto_shutdown()
        last_used = getattr(self, "_process_worker_last_used", None)
        if last_used is None and getattr(self, "_process_worker_client", None) is not None:
            last_used = time.monotonic()
            self._process_worker_last_used = last_used

        def _maybe_shutdown() -> None:
            if last_used is None:
                return
            if getattr(self, "query_executing", False):
                self._arm_process_worker_auto_shutdown()
                return
            if getattr(self, "_process_worker_last_used", None) != last_used:
                return
            self._close_process_worker_client()

        self._process_worker_idle_timer = self.set_timer(auto_seconds, _maybe_shutdown)

    def _schedule_process_worker_warm(self: QueryMixinHost) -> None:
        runtime = getattr(self.services, "runtime", None)
        if runtime is None or not getattr(runtime, "process_worker_warm_on_idle", False):
            return
        if bool(getattr(getattr(runtime, "mock", None), "enabled", False)):
            return
        from sqlit.domains.shell.app.idle_scheduler import Priority, get_idle_scheduler

        scheduler = get_idle_scheduler()
        if scheduler is None:
            return
        scheduler.cancel_all(name="process-worker-warm")

        def _warm() -> None:
            if not getattr(self.services.runtime, "process_worker", False):
                return
            if not getattr(self.services.runtime, "process_worker_warm_on_idle", False):
                return
            if bool(getattr(getattr(self.services.runtime, "mock", None), "enabled", False)):
                return
            self.run_worker(
                self._get_process_worker_client_async(),
                name="process-worker-warm",
                exclusive=False,
            )

        scheduler.request_idle_callback(
            _warm,
            priority=Priority.LOW,
            name="process-worker-warm",
        )

    def _cancel_process_worker_warm(self: QueryMixinHost) -> None:
        from sqlit.domains.shell.app.idle_scheduler import get_idle_scheduler

        scheduler = get_idle_scheduler()
        if scheduler is None:
            return
        scheduler.cancel_all(name="process-worker-warm")

    def _on_disconnect(self: QueryMixinHost) -> None:
        parent_disconnect = getattr(super(), "_on_disconnect", None)
        if callable(parent_disconnect):
            parent_disconnect()
        self._close_process_worker_client_async()
