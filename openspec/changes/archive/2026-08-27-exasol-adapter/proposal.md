## Why

sqlit ships ~29 database providers but not Exasol. Exasol is a native WebSocket-protocol
analytics database with no DB-API 2.0 driver, so it cannot reuse the `CursorBasedAdapter`
path that most existing providers share — it needs a purpose-built adapter before it can
become a selectable provider.

This change delivers that adapter (plan.md steps 1-4). It is deliberately scoped *below*
provider registration: `providers/catalog.py` discovers a subpackage only once it has a
`provider.py`, so shipping the adapter without one keeps Exasol invisible to the UI, the
connection picker, and `tests/test_schema_capabilities.py`. The repo therefore never passes
through a state where Exasol is selectable but crashes on connect.

**Correction found during implementation:** `_discover_providers` did *not* behave that way.
It imported `<name>/provider.py` for **every** subpackage unconditionally - no existence
check, no `except` - so an adapter-only package broke discovery app-wide rather than staying
inert (`get_supported_db_types()` raised `ModuleNotFoundError`, and
`tests/test_schema_capabilities.py` went from 9 passed to 4 failed). This change therefore
also makes discovery skip subpackages that have no `provider` module.

## What Changes

- New provider package `sqlit/domains/connections/providers/exasol/` containing `__init__.py`
  and `adapter.py`. **No `provider.py`** — registration is a later change.
- `providers/catalog.py::_discover_providers` skips a subpackage when
  `importlib.util.find_spec` finds no `provider` module in it, so a package staged below
  registration cannot break discovery for the other 29 providers.
- New `ExasolAdapter(DatabaseAdapter)` — subclassing `DatabaseAdapter` directly rather than
  `CursorBasedAdapter`, because pyexasol exposes no `.cursor()`.
- Capability properties declaring Exasol's shape: schema-only (no database layer), stored
  procedures yes, indexes/triggers/sequences no.
- `connect()` mapping three auth methods (password / OpenID access token / OpenID refresh
  token) and all five shared `tls_mode` values onto pyexasol's `encryption` +
  `websocket_sslopt` kwargs.
- Introspection via `conn.meta.*`, which wraps each query in Exasol's
  `/*snapshot execution*/` hint and so cannot be blocked by metadata locks.
- Query execution against pyexasol's `ExaStatement`, including `max_rows` truncation
  detection and an `execute_test_query` override (the base implementation calls
  `conn.cursor()`).
- Exasol-style identifier quoting (double quotes, `"` doubled) and `LIMIT`-based
  `build_select_query`.

Not breaking: nothing imports this package until a later change adds `provider.py`.

## Capabilities

### New Capabilities
- `exasol-adapter`: Connecting to an Exasol database (auth methods, TLS mapping, driver
  import), introspecting its schemas/tables/views/columns/procedures, and executing queries
  and statements through pyexasol's non-DB-API WebSocket interface.

### Modified Capabilities
<!-- None. openspec/specs/ is empty; no existing capability's requirements change. -->

## Impact

- **New files:** `sqlit/domains/connections/providers/exasol/__init__.py`,
  `sqlit/domains/connections/providers/exasol/adapter.py`.
- **Modified files:** `sqlit/domains/connections/providers/catalog.py` - five lines making
  provider discovery tolerant of a subpackage with no `provider.py` (see the correction
  above). Behaviour is unchanged for all 29 registered providers.
- **Dependency:** takes a runtime dependency on `pyexasol` — but only lazily, through the
  inherited `_import_driver_module()`, so a missing driver surfaces sqlit's normal install
  prompt rather than an ImportError. Declaring the `exasol` extra in `pyproject.toml` is
  plan.md step 8, a separate change; until it lands, `pyexasol` is not installed and the
  adapter's `connect()` is untestable end-to-end (its behaviour is covered by plan.md
  steps 10-11).
- **Reused, unmodified:** `providers/adapters/base.py` (`DatabaseAdapter`, `ColumnInfo`,
  `IndexInfo`, `TriggerInfo`, `SequenceInfo`, `TableInfo`), `providers/tls.py`
  (`get_tls_mode`, `tls_mode_verifies_cert`, `get_tls_files`), `providers/metadata.py`
  (`get_default_port`), `providers/driver.py` (`import_driver_module`).
- **No test-suite impact:** the package is unreachable from the registry, so no existing
  test changes behaviour. `tests/test_schema_capabilities.py` passes 9/9 and
  `get_supported_db_types()` returns the same 29 providers, without `exasol`.
- **Gate:** `ruff check sqlit && mypy sqlit`. Note that both tools are dirty on `main`
  (117 ruff findings, 430 mypy errors, and CI runs neither), so the gate is applied as
  "zero findings attributable to the changed files, repo totals unchanged".
