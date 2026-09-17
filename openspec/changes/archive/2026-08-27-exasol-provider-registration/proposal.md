## Why

The `exasol-adapter` change landed a complete `ExasolAdapter` but deliberately stopped short of
registration, so Exasol is still invisible: it is absent from the connection picker, from
`get_supported_db_types()`, from the CLI, and from every provider lookup. This change flips the
switch — it makes Exasol a selectable provider.

Registration is **all-or-nothing** and cannot be split across sessions.
`tests/test_schema_capabilities.py::TestCatalogConsistency::test_database_type_enum_matches_schema`
asserts `{t.value for t in DatabaseType} == set(get_supported_db_types())` — an *exact set
equality*. Adding `provider.py` without the enum member fails it; adding the enum member without
`provider.py` fails it too. The same test class calls `get_connection_schema(db_type)` for every
discovered type and asserts `schema.db_type == db_type` and
`schema.display_name == get_display_name(db_type)`, so `schema.py` must exist and agree with
`ProviderSpec` in the same commit. This change is therefore plan.md's atomic group `ACT`
(steps 5, 6, 7) in full, and nothing less.

## What Changes

- **New** `sqlit/domains/connections/providers/exasol/schema.py` — a `ConnectionSchema` with
  `db_type="exasol"`, `display_name="Exasol"`, `default_port="8563"`, `has_advanced_auth=True`,
  and the field set: `server`, `port`, an `authenticator` dropdown (Username & Password / OpenID
  Access Token / OpenID Refresh Token), `username`, `password`, `access_token`, `refresh_token`,
  `schema`, followed by the shared `SSH_FIELDS + TLS_FIELDS` tails.
- Credential fields are **conditionally visible**: `username` and `password` only under
  `authenticator == "password"`, `access_token` and `refresh_token` only under their own method.
  This requires declaring `username`/`password` explicitly rather than reusing
  `_username_field()` / `_password_field()`, whose returned `SchemaField` is frozen and carries no
  `visible_when`.
- **Modified** `sqlit/domains/connections/domain/config.py` — `EXASOL = "exasol"` added to the
  `DatabaseType` enum, and `DatabaseType.EXASOL` added to `DATABASE_TYPE_DISPLAY_ORDER` after
  `TERADATA`. Both are required: the enum for catalog consistency, the display order because
  `ui/screens/connection.py:331` builds the picker's `Select` options strictly from that list.
- **New** `sqlit/domains/connections/providers/exasol/provider.py` — a `ProviderSpec` plus
  `register_provider(SPEC)`, with a `provider_factory` that imports `ExasolAdapter` lazily, a
  `DockerDetector` for `exasol/docker-db`, and a `display_info` rendering `host:port/SCHEMA`.
- **Correction to plan.md step 7:** its snippet writes
  `DockerDetector(image_patterns=("exasol/docker-db",), default_user="sys")`, but `env_vars` is a
  **required** field on `DockerDetector` (`providers/docker.py:23`). As written the call raises
  `TypeError` at import time — which, because `provider.py` is imported during discovery, would
  break provider discovery for all 30 providers rather than just Exasol. This change passes
  `env_vars={}`.

Not breaking: no existing provider, schema, or test changes behaviour. The only shared file
touched is `domain/config.py`, and only by addition.

## Capabilities

### New Capabilities
- `exasol-provider-registration`: Exasol's presence in the provider catalog — its connection
  schema and per-authenticator field visibility, its `DatabaseType` enum membership and position
  in the connection picker, and the `ProviderSpec` that binds schema, adapter, Docker detection
  and display formatting into a registered, selectable provider.

### Modified Capabilities
<!-- None. openspec/specs/ is empty, so no existing capability's requirements change. -->

## Impact

- **New files:** `sqlit/domains/connections/providers/exasol/schema.py`,
  `sqlit/domains/connections/providers/exasol/provider.py`.
- **Modified files:** `sqlit/domains/connections/domain/config.py` — two additive lines (one enum
  member, one display-order entry).
- **Consumed unchanged:** `providers/schema_helpers.py` (`ConnectionSchema`, `SchemaField`,
  `FieldType`, `SelectOption`, `SSH_FIELDS`, `TLS_FIELDS`, `_server_field`, `_port_field`),
  `providers/model.py` (`ProviderSpec`, `DatabaseProvider`), `providers/catalog.py`
  (`register_provider`), `providers/adapter_provider.py` (`build_adapter_provider`),
  `providers/docker.py` (`DockerDetector`), and `providers/exasol/adapter.py` from the previous
  change — untouched here.
- **Behaviour that turns on for free**, because it is all schema-driven:
  - the connection picker gains an "Exasol" entry (`ui/screens/connection.py:331`);
  - `cli/helpers.py:43` derives `--server/--host`, `--port`, `--authenticator`,
    `--access-token`, `--refresh-token`, `--schema` flags from the schema fields;
  - `providers/validation.py:30` enforces `required` only on *visible* fields, so `--username` is
    not demanded when authenticating with a token;
  - `config.py:232-246` routes the non-endpoint fields (`authenticator`, `access_token`,
    `refresh_token`, `schema`) into `config.options`, which is exactly where
    `adapter.connect()` reads them with `config.get_option(...)`.
- **Dependency:** none added. `pyexasol` is still not installed — the `exasol` extra is plan.md
  step 8, a separate change. Registration does not need it: `provider_factory` imports the
  adapter module lazily and `_import_driver_module` only runs on an actual connect, so
  discovery, the picker, and the test suite all work driverless.
- **Test-suite impact:** `tests/test_schema_capabilities.py` moves from 29 to 30 discovered
  providers and must stay 9/9 green — that is this change's gate. No test file is added here;
  the Exasol-specific unit tests are plan.md steps 9-11.
- **User-visible risk:** selecting Exasol in the picker and connecting without `pyexasol`
  installed now reaches sqlit's normal "install the driver" prompt rather than being impossible.
  That is the intended end state, but it is the first time Exasol is reachable from the UI.
- **Gate:** `uv run pytest tests/test_schema_capabilities.py -v` plus
  `uv run ruff check sqlit && uv run mypy sqlit`. As in the previous change, both linters are
  dirty on `main` (and CI runs neither), so the lint half of the gate is applied as "zero findings
  attributable to the changed files, repo totals unchanged".
