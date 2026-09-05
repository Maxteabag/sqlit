## Why

The `exasol-adapter` and `exasol-provider-registration` changes made Exasol a fully selectable
provider, but two things are still missing before it can be upstreamed: **the driver cannot be
installed** (`pip install sqlit-tui[exasol]` fails — there is no `exasol` extra, and `pyexasol` is
absent from `uv.lock`), and **not one line of `ExasolAdapter` is covered by a test**. Every
behavioural decision recorded in the two previous changes — the token-vs-password credential
branch, the TLS mode mapping, `stmt.result_type` being checked before any fetch, `rowcount()` being
a method, `conn.meta.*` returning UPPERCASE-keyed dicts — is currently a claim in a design document
with nothing asserting it.

This change closes both gaps: it makes the driver installable and locks the adapter's behaviour
into the default CI job. It is plan.md steps 8, 9, 10 and 11.

## What Changes

- **Modified** `pyproject.toml` — a new `exasol = ["pyexasol>=2.0.0"]` optional-dependency extra,
  the same pin added to the aggregate `all` extra, `"pyexasol"` added to the mypy
  `ignore_missing_imports` override list, and an `"exasol: Exasol database tests"` pytest marker.
- **Regenerated** `uv.lock` — `uv sync --extra exasol` resolves `pyexasol` (and its `websocket-client`
  / `packaging` dependencies) into the lockfile.
- **New** `tests/connections/providers/exasol/test_schema.py` — asserts the `visible_when`
  predicates on `SCHEMA` show exactly the credential fields belonging to the selected
  `authenticator`, and hide the other two methods' fields. Needs no driver.
- **New** `tests/connections/providers/exasol/test_connect.py` — mocked `pyexasol` module,
  asserting the kwargs `connect()` actually passes: the correct credentials per `authenticator`
  **and the absence of the unused ones**, the `tls_mode` → `encryption` / `websocket_sslopt`
  mapping for all five modes, and `extra_options` passthrough.
- **New** `tests/connections/providers/exasol/test_adapter.py` — mocked connection, asserting the
  introspection row-shape contract (`conn.meta.*` read by UPPERCASE key), primary-key detection,
  the `execute_query` truncation flag at the `max_rows` boundary, the `result_type` guard firing
  before any fetch, `rowcount()` called as a method, and `quote_identifier` escaping.
- **New** `tests/connections/providers/exasol/__init__.py` — empty, matching the existing
  `tests/connections/providers/hana/__init__.py`.
- No changes to any file under `sqlit/`. The adapter is not being modified; it is being pinned.

## Capabilities

### New Capabilities

- `exasol-driver-packaging`: `pyexasol` is installable as a named extra, resolvable in the
  lockfile, declared to mypy, and Exasol tests are addressable by marker.
- `exasol-unit-coverage`: driver-free unit tests that pin the schema's conditional field
  visibility and every behavioural decision in `ExasolAdapter`, running in the default CI job.

### Modified Capabilities

None. `openspec/specs/exasol-provider-registration` describes behaviour that this change asserts
but does not alter — no requirement in it changes.

## Impact

- **Dependencies**: adds `pyexasol>=2.0.0` as an *optional* dependency. Nothing in the default
  install changes; `sqlit` still imports the driver lazily, so a user without the extra sees the
  normal install prompt rather than an `ImportError`.
- **Lockfile**: `uv.lock` is already carrying an unrelated pre-existing drift on this branch (the
  stale `mariadb` package entry, dropped when the `mariadb` extra switched to `PyMySQL`). Running
  `uv sync` folds that refresh in alongside the `pyexasol` addition — see design D5.
- **CI**: the three new test files are collected by the existing unit-test job with no workflow
  change, because they live under `tests/connections/` and are not in its `--ignore` list. Test
  count rises; runtime does not measurably.
- **Python support**: `pyexasol` declares `requires-python >=3.10,<3.15` against sqlit's unbounded
  `>=3.10`. This constrains the aggregate `all` extra on future interpreters — see design D6.
- **Not affected**: no `sqlit/` source file, no Docker compose service, no integration test, no
  workflow file, no documentation. Those are plan.md steps 12-15.
