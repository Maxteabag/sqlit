"""CLI helper fixtures."""

from __future__ import annotations

import pytest

from tests.fixtures.utils import run_cli


@pytest.fixture(scope="session")
def cli_runner():
    """Provide the CLI runner function."""
    return run_cli


__all__ = [
    "cli_runner",
]
