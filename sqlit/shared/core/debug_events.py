"""Debug event bus and helpers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

DebugHandler = Callable[["DebugEvent"], None]


@dataclass(frozen=True)
class DebugEvent:
    """Structured debug event payload."""

    name: str
    ts: float
    iso: str
    category: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class DebugEventBus:
    """Lightweight observer for debug events."""

    def __init__(self) -> None:
        self._handlers: list[DebugHandler] = []

    def subscribe(self, handler: DebugHandler) -> None:
        if handler not in self._handlers:
            self._handlers.append(handler)

    def unsubscribe(self, handler: DebugHandler) -> None:
        try:
            self._handlers.remove(handler)
        except ValueError:
            pass

    def emit(self, name: str, *, category: str = "", **data: Any) -> None:
        if not self._handlers:
            return
        now = time.time()
        iso = datetime.fromtimestamp(now).isoformat(timespec="milliseconds")
        event = DebugEvent(name=name, ts=now, iso=iso, category=category or "", data=data)
        for handler in list(self._handlers):
            try:
                handler(event)
            except Exception:
                continue


def _coerce_debug_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _coerce_debug_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce_debug_value(item) for item in value]
    return str(value)


def coerce_debug_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Make debug payload safe for JSON serialization."""
    return {str(key): _coerce_debug_value(value) for key, value in data.items()}


def serialize_debug_event(event: DebugEvent) -> str:
    payload = {
        "time": event.iso,
        "name": event.name,
        "category": event.category,
        "data": coerce_debug_payload(event.data),
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def format_debug_data(data: dict[str, Any], *, max_len: int = 120) -> str:
    if not data:
        return ""
    parts: list[str] = []
    for key in sorted(data):
        value = data[key]
        text = str(value)
        if len(text) > max_len:
            text = f"{text[:max_len - 3]}..."
        parts.append(f"{key}={text}")
    return " ".join(parts)


_DEBUG_EMITTER: Callable[..., None] | None = None


def set_debug_emitter(emitter: Callable[..., None] | None) -> None:
    """Register a global debug event emitter."""
    global _DEBUG_EMITTER
    _DEBUG_EMITTER = emitter


def emit_debug_event(name: str, *, category: str = "", **data: Any) -> None:
    """Emit a debug event via the global emitter if configured."""
    if _DEBUG_EMITTER is None:
        return
    try:
        _DEBUG_EMITTER(name, category=category or "", **data)
    except Exception:
        pass
