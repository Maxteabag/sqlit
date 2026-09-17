# exasol-driver-packaging Specification

## Purpose
Defines how the Exasol driver is packaged, resolved and addressed by tooling: the `exasol`
optional-dependency extra that installs `pyexasol`, the same requirement inside the aggregate `all`
extra, its resolution into `uv.lock`, its declaration to the type checker, and the registered
`exasol` pytest marker.

The driver stays optional. `ExasolAdapter` imports it lazily through `_import_driver_module`, so an
environment without the extra receives sqlit's install prompt rather than an `ImportError`, and the
default install is unchanged.

Scope boundaries: adapter behaviour lives in `exasol-adapter`; the connection schema, `DatabaseType`
membership and `ProviderSpec` registration live in `exasol-provider-registration`; the unit tests
themselves live in `exasol-unit-coverage`.

## Requirements
### Requirement: Exasol driver is installable as a named optional extra

`pyproject.toml` SHALL declare an `exasol` entry under `[project.optional-dependencies]` requiring
`pyexasol>=2.0.0`, and the same requirement SHALL appear in the aggregate `all` extra. The extra
MUST NOT be promoted into `[project].dependencies`: `ExasolAdapter` imports its driver lazily
through `_import_driver_module`, so a user without the extra MUST continue to receive sqlit's
install prompt rather than an `ImportError` at startup.

The requirement string carries no inline environment marker even though `pyexasol` declares
`requires-python >=3.10,<3.15` against sqlit's unbounded `>=3.10`; `uv` attaches the interpreter
marker to the locked entry instead (design D6).

#### Scenario: Dedicated extra exists
- **WHEN** `[project.optional-dependencies]` in `pyproject.toml` is read
- **THEN** it contains `exasol = ["pyexasol>=2.0.0"]`
- **AND** the entry sits with the other single-provider extras, not inside `all`

#### Scenario: Aggregate extra includes the driver
- **WHEN** the `all` extra is read
- **THEN** it contains a `pyexasol>=2.0.0` requirement

#### Scenario: Extra installs successfully
- **WHEN** `uv sync --extra exasol` is run
- **THEN** it completes without a resolution error
- **AND** `uv run python -c "import pyexasol"` succeeds

#### Scenario: Driver is resolved in the lockfile
- **WHEN** `uv.lock` is inspected after the sync
- **THEN** it contains a `pyexasol` package entry
- **AND** that entry is reachable from the `exasol` and `all` extras of `sqlit-tui`

#### Scenario: Default install is unaffected
- **WHEN** `[project].dependencies` is read
- **THEN** it does not mention `pyexasol`
- **AND** an environment without the extra can still import `sqlit` and open the connection picker

#### Scenario: Resolution across the declared Python range succeeds
- **WHEN** `uv lock` resolves against sqlit's declared `requires-python >=3.10`
- **THEN** it completes without an error naming Python 3.15
- **AND** the `pyexasol` lock entry carries the interpreter marker rather than the `pyproject.toml`
  requirement string

### Requirement: The driver module is declared to the type checker

`"pyexasol"` SHALL be listed in the `[[tool.mypy.overrides]]` `module` array that sets
`ignore_missing_imports`, alongside the other driver modules.

This entry is currently inert — `mypy` excludes `tests/` and `sqlit/` names `pyexasol` only inside a
string literal passed to `_import_driver_module`, so there is no import for mypy to resolve. It is
declared for consistency with `hdbcli` and `teradatasql`, which are lazily imported the same way and
are already listed, and so that the override is in place if a `TYPE_CHECKING` import of the driver is
ever added. Because the entry is inert, a clean `mypy` run does NOT constitute evidence that it was
added (design D4).

#### Scenario: Override list includes the driver
- **WHEN** the mypy `ignore_missing_imports` override module list is read
- **THEN** it contains `"pyexasol"`

#### Scenario: Type checking stays clean
- **WHEN** `uv run mypy sqlit` is run with the extra installed
- **THEN** it reports no new errors relative to the pre-change baseline

### Requirement: Exasol tests are addressable by a registered marker

`[tool.pytest.ini_options].markers` SHALL contain `"exasol: Exasol database tests"`, matching the
wording of the neighbouring per-database markers.

No test introduced by this change carries the marker. The driver-free unit tests belong to the
default job and stay unmarked, matching `tests/connections/providers/hana/test_get_columns.py`. The
marker is registered ahead of the Docker integration test so that test can apply it without a
`PytestUnknownMarkWarning` (design D7).

#### Scenario: Marker is registered
- **WHEN** `uv run pytest --markers` is run
- **THEN** `exasol` appears in the output with the description `Exasol database tests`

#### Scenario: No unknown-mark warning is possible
- **WHEN** a test is decorated with `@pytest.mark.exasol`
- **THEN** pytest does not emit `PytestUnknownMarkWarning` for it

#### Scenario: Marker selects nothing yet
- **WHEN** `uv run pytest -m exasol` is run against the tree produced by this change
- **THEN** zero tests are selected, because no test is marked yet
