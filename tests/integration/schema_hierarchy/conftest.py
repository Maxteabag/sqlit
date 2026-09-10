"""Explicit opt-in; missing requested drivers/services are failures, not skips."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from .support import provider_database

PROVIDERS = ["postgresql", "mssql", "snowflake", "supabase", "sqlite"]


def pytest_generate_tests(metafunc):
    if "provider_case" not in metafunc.fixturenames:
        return
    names = os.environ.get("SQLIT_SCHEMA_PROVIDERS", ",".join(PROVIDERS)).split(",")
    unknown = set(names) - set(PROVIDERS)
    if unknown:
        raise ValueError(f"Unknown schema integration providers: {sorted(unknown)}")
    if metafunc.function.__name__ == "test_ancillary_metadata_and_definitions_are_scoped":
        names = [name for name in names if name in {"postgresql", "mssql", "supabase"}]
    elif metafunc.function.__name__ == "test_process_worker_metadata_matches_direct_provider":
        names = [name for name in names if name in {"postgresql", "mssql"}]
    metafunc.parametrize("provider_case", names, indirect=True, scope="module")


@pytest.fixture(scope="module")
def provider_case(request, tmp_path_factory):
    if os.environ.get("SQLIT_SCHEMA_INTEGRATION") != "1":
        pytest.skip("Set SQLIT_SCHEMA_INTEGRATION=1 to run disposable provider integration tests")
    with provider_database(request.param, tmp_path_factory.mktemp("schema-" + request.param)) as case:
        yield case


@pytest.fixture
def capture_dir():
    value = os.environ.get("SQLIT_SCHEMA_CAPTURE_DIR")
    return Path(value) if value else None
