"""Pytest configuration for Docker detection integration tests."""

import pytest


def pytest_addoption(parser):
    """Add custom command line options for Docker tests."""
    try:
        parser.addoption(
            "--run-docker-container",
            action="store_true",
            default=False,
            help="Run tests that create temporary Docker containers",
        )
    except ValueError:
        # Option already added
        pass


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (may require external services)",
    )
