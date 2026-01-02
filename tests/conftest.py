"""Pytest fixtures for sqlit integration tests."""

import pytest

from tests.fixtures.cli import *
from tests.fixtures.clickhouse import *
from tests.fixtures.cockroachdb import *
from tests.fixtures.d1 import *
from tests.fixtures.duckdb import *
from tests.fixtures.firebird import *
from tests.fixtures.mariadb import *
from tests.fixtures.mssql import *
from tests.fixtures.mysql import *
from tests.fixtures.oracle import *
from tests.fixtures.postgres import *
from tests.fixtures.ssh import *
from tests.fixtures.sqlite import *
from tests.fixtures.turso import *
from tests.fixtures.utils import *


@pytest.fixture(autouse=True)
def _reset_mock_docker_containers():
    """Ensure mock Docker containers do not leak between tests."""
    from sqlit.mock_settings import set_mock_docker_containers

    set_mock_docker_containers(None)
    yield
    set_mock_docker_containers(None)
