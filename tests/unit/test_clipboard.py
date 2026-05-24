"""Tests for shared clipboard helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlit.shared.ui import clipboard


def test_get_system_clipboard_uses_macos_pbpaste(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="select 1")

    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    monkeypatch.setattr(clipboard.shutil, "which", lambda command: command)
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.get_system_clipboard_text() == "select 1"
    assert calls == [["pbpaste"]]


def test_copy_to_system_clipboard_uses_wayland_when_available(monkeypatch) -> None:
    calls: list[tuple[list[str], str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs["input"]))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(clipboard.shutil, "which", lambda command: command)
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.copy_to_system_clipboard("select 1")
    assert calls == [(["wl-copy", "--type", "text/plain"], "select 1")]


def test_get_system_clipboard_falls_back_to_pyperclip(monkeypatch) -> None:
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(clipboard.shutil, "which", lambda _command: None)
    monkeypatch.setattr("pyperclip.paste", lambda: "from pyperclip")

    assert clipboard.get_system_clipboard_text() == "from pyperclip"
