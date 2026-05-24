"""Regression test for issue #186: paramiko 4 removed DSSKey, breaking sshtunnel."""

from __future__ import annotations

import sys
import types

import pytest

from sqlit.domains.connections.app.tunnel import ensure_ssh_tunnel_available
from sqlit.domains.connections.providers.exceptions import MissingDriverError


def test_ensure_ssh_tunnel_raises_missing_driver_when_paramiko_lacks_dsskey(monkeypatch):
    """A paramiko without DSSKey (i.e. 4.x) must surface as MissingDriverError, not AttributeError."""
    fake_paramiko = types.ModuleType("paramiko")
    fake_paramiko.__version__ = "4.0.0"  # type: ignore[attr-defined]
    # Intentionally no DSSKey attribute — simulating paramiko 4.

    fake_sshtunnel = types.ModuleType("sshtunnel")

    monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)
    monkeypatch.setitem(sys.modules, "sshtunnel", fake_sshtunnel)

    with pytest.raises(MissingDriverError) as excinfo:
        ensure_ssh_tunnel_available()

    assert excinfo.value.extra_name == "ssh"
    assert "paramiko" in str(excinfo.value.import_error or "").lower()


def test_ensure_ssh_tunnel_passes_when_paramiko_has_dsskey(monkeypatch):
    """A paramiko 3.x with DSSKey must not raise."""
    fake_paramiko = types.ModuleType("paramiko")
    fake_paramiko.__version__ = "3.5.0"  # type: ignore[attr-defined]
    fake_paramiko.DSSKey = object  # type: ignore[attr-defined]

    fake_sshtunnel = types.ModuleType("sshtunnel")

    monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)
    monkeypatch.setitem(sys.modules, "sshtunnel", fake_sshtunnel)

    ensure_ssh_tunnel_available()  # must not raise
