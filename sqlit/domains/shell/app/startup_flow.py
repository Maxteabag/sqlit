"""Startup flow helpers for the main application."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.explorer.ui.tree import builder as tree_builder
from sqlit.domains.shell.app.idle_scheduler import init_idle_scheduler
from sqlit.shared.app.startup_profiler import write_line
from sqlit.shared.ui.protocols import AppProtocol


def run_on_mount(app: AppProtocol) -> None:
    """Initialize the app after mount."""
    app._startup_stamp("on_mount_start")
    app._restart_argv = app._compute_restart_argv()

    is_headless = bool(getattr(app, "is_headless", False))
    if not is_headless:
        app._idle_scheduler = init_idle_scheduler(app)
        app._idle_scheduler.start()

        if app._debug_idle_scheduler:
            app.idle_scheduler_bar.add_class("visible")
            app._idle_scheduler_bar_timer = app.set_interval(0.1, app._update_idle_scheduler_bar)

    app._theme_manager.register_builtin_themes()
    app._theme_manager.register_textarea_themes()

    settings = app._theme_manager.initialize()
    app._startup_stamp("settings_loaded")

    app._expanded_paths = set(settings.get("expanded_nodes", []))
    if "process_worker" in settings:
        app.services.runtime.process_worker = bool(settings.get("process_worker"))
    if "process_worker_warm_on_idle" in settings:
        app.services.runtime.process_worker_warm_on_idle = bool(
            settings.get("process_worker_warm_on_idle")
        )
    if "process_worker_auto_shutdown_s" in settings:
        try:
            app.services.runtime.process_worker_auto_shutdown_s = float(
                settings.get("process_worker_auto_shutdown_s") or 0
            )
        except (TypeError, ValueError):
            app.services.runtime.process_worker_auto_shutdown_s = 0.0
    if "ui_stall_watchdog_ms" in settings:
        try:
            app.services.runtime.ui_stall_watchdog_ms = float(
                settings.get("ui_stall_watchdog_ms") or 0
            )
        except (TypeError, ValueError):
            app.services.runtime.ui_stall_watchdog_ms = 0.0
    if "show_line_numbers" in settings:
        try:
            app.query_input.show_line_numbers = bool(settings.get("show_line_numbers"))
        except Exception:
            pass
    if "relative_line_numbers" in settings:
        try:
            app.query_input.relative_line_numbers = bool(settings.get("relative_line_numbers"))
        except Exception:
            pass
    app._startup_stamp("settings_applied")

    apply_mock_settings(app, settings)
    if app.services.runtime.mock.enabled:
        app.services.runtime.process_worker = False
        app.services.runtime.process_worker_warm_on_idle = False

    app.connections = app.services.connection_store.load_all(load_credentials=False)
    if app._startup_connection:
        setup_startup_connection(app, app._startup_connection)
    app._startup_stamp("connections_loaded")

    tree_builder.refresh_tree(app)
    app._startup_stamp("tree_refreshed")

    app.object_tree.focus()
    app._startup_stamp("tree_focused")
    if app.object_tree.root.children:
        app.object_tree.cursor_line = 0
    app._update_section_labels()
    maybe_restore_connection_screen(app)
    app._startup_stamp("restore_checked")
    if app._debug_mode:
        app.call_after_refresh(app._record_launch_ms)
    app.call_after_refresh(app._update_status_bar)
    app._update_footer_bindings()
    app._startup_stamp("footer_updated")
    _warn_on_missing_actions(app, is_headless)
    _warn_on_keyring_error(app, is_headless)
    if (
        app.services.runtime.process_worker
        and app.services.runtime.process_worker_warm_on_idle
        and not app.services.runtime.mock.enabled
        and hasattr(app, "_schedule_process_worker_warm")
    ):
        try:
            app._schedule_process_worker_warm()  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(app, "_start_ui_stall_watchdog"):
        try:
            app._start_ui_stall_watchdog()  # type: ignore[attr-defined]
        except Exception:
            pass
    startup_config = app._startup_connect_config
    if startup_config is not None:
        config = startup_config

        def _connect_startup() -> None:
            app.connect_to_server(config)

        app.call_after_refresh(_connect_startup)
    log_startup_timing(app)


def _warn_on_missing_actions(app: AppProtocol, is_headless: bool) -> None:
    from sqlit.core.action_validation import validate_actions

    missing = validate_actions(app)
    if not missing:
        return
    message = f"Missing actions: {', '.join(missing)}"
    if is_headless:
        print(f"[sqlit] {message}", file=sys.stderr)
        return
    try:
        app.notify(message, severity="warning")
    except Exception:
        print(f"[sqlit] {message}", file=sys.stderr)


def _warn_on_keyring_error(app: AppProtocol, is_headless: bool) -> None:
    from sqlit.domains.connections.app.credentials import get_keyring_probe_error

    error = get_keyring_probe_error()
    if not error:
        return
    message = f"Keyring unavailable: {error}. Saved passwords may not load. If this persists, see :commands for guidance."
    if is_headless:
        print(f"[sqlit] {message}", file=sys.stderr)
        return
    try:
        app.notify(message, severity="warning", timeout=15)
    except Exception:
        print(f"[sqlit] {message}", file=sys.stderr)


def apply_mock_settings(app: AppProtocol, settings: dict) -> None:
    app.services.apply_mock_settings(settings)


def setup_startup_connection(app: AppProtocol, config: ConnectionConfig) -> None:
    """Set up a startup connection to auto-connect after mount."""
    if not config.name:
        config.name = "Temp Connection"
    app._startup_connect_config = config


def log_startup_timing(app: AppProtocol) -> None:
    if not app._startup_profile:
        return
    now = time.perf_counter()
    since_start = (now - app._startup_mark) * 1000 if app._startup_mark is not None else None
    init_to_mount = (now - app._startup_init_time) * 1000

    parts = []
    if since_start is not None:
        parts.append(f"start_to_mount_ms={since_start:.2f}")
    parts.append(f"init_to_mount_ms={init_to_mount:.2f}")
    _emit_startup_line(app, f"[sqlit] startup {' '.join(parts)}")
    _log_startup_steps(app)

    def after_refresh() -> None:
        now_refresh = time.perf_counter()
        start_to_refresh = (now_refresh - app._startup_mark) * 1000 if app._startup_mark is not None else None
        init_to_refresh = (now_refresh - app._startup_init_time) * 1000

        _log_startup_step(app, "first_refresh", now_refresh)
        refresh_parts = []
        if start_to_refresh is not None:
            refresh_parts.append(f"start_to_first_refresh_ms={start_to_refresh:.2f}")
        refresh_parts.append(f"init_to_first_refresh_ms={init_to_refresh:.2f}")
        _emit_startup_line(app, f"[sqlit] startup {' '.join(refresh_parts)}")
        _maybe_exit_after_refresh(app)

    app.call_after_refresh(after_refresh)


def _log_startup_steps(app: AppProtocol) -> None:
    for name, ts in app._startup_events:
        _log_startup_step(app, name, ts)


def _log_startup_step(app: AppProtocol, name: str, timestamp: float) -> None:
    if not app._startup_profile:
        return
    parts = [f"step={name}"]
    if app._startup_mark is not None:
        parts.append(f"start_ms={(timestamp - app._startup_mark) * 1000:.2f}")
    parts.append(f"init_ms={(timestamp - app._startup_init_time) * 1000:.2f}")
    _emit_startup_line(app, f"[sqlit] startup {' '.join(parts)}")


def _emit_startup_line(app: AppProtocol, line: str) -> None:
    print(line, file=sys.stderr)
    write_line(line)


def _maybe_exit_after_refresh(app: AppProtocol) -> None:
    runtime = getattr(getattr(app, "services", None), "runtime", None)
    if not getattr(runtime, "startup_exit_after_refresh", False):
        return
    try:
        app.exit()
    except Exception:
        pass


def _get_restart_cache_path() -> Path:
    return Path(tempfile.gettempdir()) / "sqlit-driver-install-restore.json"


def maybe_restore_connection_screen(app: AppProtocol) -> None:
    """Restore an in-progress connection form after a driver-install restart."""
    cache_path = _get_restart_cache_path()
    if not cache_path.exists():
        return

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        try:
            cache_path.unlink(missing_ok=True)
        except Exception:
            pass
        return

    try:
        cache_path.unlink(missing_ok=True)
    except Exception:
        pass

    if not isinstance(payload, dict) or payload.get("version") != 1:
        return

    values = payload.get("values")
    if not isinstance(values, dict):
        return

    editing = bool(payload.get("editing"))
    original_name = payload.get("original_name")
    post_install_message = payload.get("post_install_message")
    active_tab = payload.get("active_tab")

    config = None
    if editing and isinstance(original_name, str) and original_name:
        config = next((c for c in app.connections if getattr(c, "name", None) == original_name), None)

    if config is None:
        config = ConnectionConfig(
            name=str(values.get("name", "")),
            db_type=str(values.get("db_type", "mssql") or "mssql"),
        )
        editing = False

    prefill_values = {
        "values": values,
        "active_tab": active_tab,
    }

    app._set_connection_screen_footer()

    from sqlit.domains.connections.ui.screens import ConnectionScreen

    app.push_screen(
        ConnectionScreen(
            config,
            editing=editing,
            prefill_values=prefill_values,
            post_install_message=post_install_message,
        ),
        app._wrap_connection_result,
    )
