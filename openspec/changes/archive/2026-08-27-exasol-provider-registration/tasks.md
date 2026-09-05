## 1. Connection schema

Corresponds to plan.md step 5. Write this group **before** group 3 — `provider.py` is the switch
that turns discovery on (design D1).

- [x] 1.1 Create `sqlit/domains/connections/providers/exasol/schema.py` with the module docstring
      `"""Connection schema for Exasol."""` and imports from `providers.schema_helpers`:
      `SSH_FIELDS`, `TLS_FIELDS`, `ConnectionSchema`, `FieldType`, `SchemaField`, `SelectOption`,
      `_port_field`, `_server_field`. Do **not** import `_username_field` / `_password_field` —
      design D3 declares those two fields explicitly.
- [x] 1.2 Add a module-level `_get_exasol_auth_options()` returning the three `SelectOption`s in
      order: `("password", "Username & Password")`, `("access_token", "OpenID Access Token")`,
      `("refresh_token", "OpenID Refresh Token")`. Mirrors
      `providers/snowflake/schema.py::_get_snowflake_auth_options`.
- [x] 1.3 Add the visibility predicates as module-level helpers taking a `dict` and reading
      `v.get("authenticator", "password")` — the `"password"` default matters: the spec scenario
      "Missing authenticator value falls back to password auth" requires `visible_when({})` to show
      username/password, matching `adapter.connect()`'s own `get_option` default.
- [x] 1.4 Declare `SCHEMA = ConnectionSchema(...)` with `db_type="exasol"`,
      `display_name="Exasol"` (exact case — design D5), `default_port="8563"`,
      `has_advanced_auth=True`, and `supports_ssh` left at its `True` default.
- [x] 1.5 Fields, in order: `_server_field()`, `_port_field("8563")`, then the `authenticator`
      `SchemaField` with `field_type=FieldType.DROPDOWN`, `options=_get_exasol_auth_options()` and
      `default="password"`.
- [x] 1.6 Add the `username` field explicitly: `required=True`, `group="credentials"`,
      `visible_when` = password-auth predicate. Required is safe because
      `providers/validation.py:30` skips hidden fields (design D3).
- [x] 1.7 Add the `password` field explicitly: `field_type=FieldType.PASSWORD`,
      `placeholder="(empty = ask every connect)"`, `group="credentials"`, `required=False`,
      `visible_when` = password-auth predicate.
- [x] 1.8 Add `access_token` and `refresh_token`, both `FieldType.PASSWORD`, `required=False`, each
      with a `visible_when` matching only its own `authenticator` value.
- [x] 1.9 Add the `schema` field: `required=False`, `placeholder="(empty = browse all)"`. Do
      **not** add a `database` field — the adapter reports `supports_multiple_databases is False`.
- [x] 1.10 Close the tuple with `+ SSH_FIELDS + TLS_FIELDS` (design D4 — `TLS_FIELDS` is what makes
      `adapter._tls_args()` reachable and step 13's `--tls-mode require` possible).
- [x] 1.11 Verify the module imports on its own and is still undiscovered:
      `uv run python -c "from sqlit.domains.connections.providers.exasol.schema import SCHEMA; print(SCHEMA.db_type, SCHEMA.display_name, len(SCHEMA.fields))"`
      then `uv run pytest tests/test_schema_capabilities.py -q` — must still pass at 29 providers,
      since no `provider.py` exists yet.

## 2. DatabaseType enum and picker order

Corresponds to plan.md step 6. Independent of group 1; both must precede group 3.

- [x] 2.1 In `sqlit/domains/connections/domain/config.py`, add `EXASOL = "exasol"` to
      `DatabaseType`, between `DB2` and `FIREBIRD`.
- [x] 2.2 Add `DatabaseType.EXASOL` to `DATABASE_TYPE_DISPLAY_ORDER`, immediately after
      `DatabaseType.TERADATA`. Design D8: this one is a **silent** requirement —
      `ui/screens/connection.py:331` builds the picker from exactly this list and no test covers its
      completeness, so omitting it passes every test and leaves Exasol unselectable.
- [x] 2.3 Confirm the enum edit alone now makes the capability suite fail (expected, and the reason
      this change is atomic): `uv run pytest tests/test_schema_capabilities.py -q` reports
      `test_database_type_enum_matches_schema` failing on exact set equality. Do not attempt to fix
      it here — group 3 closes it.

## 3. Provider registration

Corresponds to plan.md step 7. Write this **last** (design D1).

- [x] 3.1 Create `sqlit/domains/connections/providers/exasol/provider.py` with the docstring
      `"""Provider registration."""` and imports of `build_adapter_provider`, `register_provider`,
      `DockerDetector`, `DatabaseProvider`, `ProviderSpec`, and `SCHEMA` from the sibling
      `schema` module — following `providers/teradata/provider.py`.
- [x] 3.2 Add `_provider_factory(spec: ProviderSpec) -> DatabaseProvider` that imports
      `ExasolAdapter` **inside the function body** and returns
      `build_adapter_provider(spec, SCHEMA, ExasolAdapter())`. No module-scope adapter import
      (design D10).
- [x] 3.3 Add `_display_info(config: ConnectionConfig) -> str` returning `host:port/SCHEMA` from
      `config.tcp_endpoint` plus `config.get_option("schema", "")`, and `host:port` with no trailing
      slash when the schema is empty (design D7). Import `ConnectionConfig` under `TYPE_CHECKING`.
- [x] 3.4 Declare `SPEC = ProviderSpec(...)` with `db_type="exasol"`, `display_name="Exasol"`,
      `schema_path=("sqlit.domains.connections.providers.exasol.schema", "SCHEMA")`,
      `supports_ssh=True`, `is_file_based=False`, `has_advanced_auth=True`, `default_port="8563"`,
      `requires_auth=True`, `badge_label="Exasol"`, `url_schemes=("exasol", "exa")`.
- [x] 3.5 Add `docker_detector=DockerDetector(image_patterns=("exasol/docker-db",), env_vars={},
      default_user="sys")`. Design D6: `env_vars` is a **required** field — plan.md step 7's snippet
      omits it and would raise `TypeError` during discovery, breaking all 30 providers.
- [x] 3.6 Wire `display_info=_display_info` and `provider_factory=_provider_factory` into `SPEC`,
      then call `register_provider(SPEC)` at module scope.
- [x] 3.7 Cross-check the duplicated literals now that both objects exist: `db_type`,
      `display_name` and `default_port` must be character-identical between `SCHEMA` and `SPEC`
      (design D5) — this is what `test_provider_schema_ids_match_keys` and
      `test_display_names_match_schema` verify.

## 4. Change gate

The `ACT` group's gate. All of group 1, 2 and 3 must be complete before any of this runs.

- [x] 4.1 Run the primary gate: `uv run pytest tests/test_schema_capabilities.py -v` — all 9 tests
      pass, and `get_supported_db_types()` now returns 30 types including `"exasol"`.
- [x] 4.2 Confirm the registry metadata resolves:
      `uv run python -c "from sqlit.domains.connections.providers.registry import get_default_port, get_display_name, has_advanced_auth, supports_ssh; print(get_display_name('exasol'), get_default_port('exasol'), has_advanced_auth('exasol'), supports_ssh('exasol'))"`
      prints `Exasol 8563 True True`.
- [x] 4.3 Confirm the picker entry exists (the silent requirement from 2.2):
      `uv run python -c "from sqlit.domains.connections.domain.config import DATABASE_TYPE_DISPLAY_ORDER, DatabaseType, get_database_type_labels; print(DatabaseType.EXASOL in DATABASE_TYPE_DISPLAY_ORDER, get_database_type_labels()[DatabaseType.EXASOL])"`
      prints `True Exasol`.
- [x] 4.4 Confirm the adapter stays off the startup path: after importing the registry and listing
      supported types, `sqlit.domains.connections.providers.exasol.adapter` is absent from
      `sys.modules` (design D10 / spec scenario "Adapter module is not imported at startup").
- [x] 4.5 Spot-check the visibility matrix by hand, ahead of the real tests in plan.md step 9:
      evaluate each credential field's `visible_when` against `{"authenticator": "password"}`,
      `{"authenticator": "access_token"}`, `{"authenticator": "refresh_token"}` and `{}`, and confirm
      the results match the spec's matrix.
- [x] 4.6 Confirm no regressions in the wider suite: `uv run pytest tests/connections -q` and the
      unit-test job command from `.github/workflows/ci.yml:70-82` — no previously passing test
      fails.
- [x] 4.7 Run the lint half of the gate: `uv run ruff check sqlit && uv run mypy sqlit`. Both are
      dirty on `main` (and CI runs neither), so the bar is "zero findings attributable to
      `schema.py`, `provider.py` or the `config.py` edit, repo totals otherwise unchanged" —
      compare against the pre-change totals.
- [x] 4.8 Confirm `providers/exasol/adapter.py` is absent from the diff (spec: "Adapter is
      unchanged") and that the only shared file touched is `domain/config.py`, by addition only.
- [x] 4.9 Manual check: `uv run sqlit`, open the new-connection screen, select **Exasol**, and
      confirm the port prefills to 8563, the auth dropdown shows the three methods, switching
      methods swaps Password for Access Token / Refresh Token, and the TLS tab is present.
      Connecting is expected to raise sqlit's driver-install prompt — `pyexasol` is not installed
      until plan.md step 8.

## 5. Plan bookkeeping

- [x] 5.1 In `plan.md`, set steps 5, 6 and 7 to `done` in the Status table and update the progress
      count to `7 / 15 done`.
- [x] 5.2 Append a `plan.md` Session log row recording the `DockerDetector` correction (design D6 —
      `env_vars` is required, so step 7's snippet as written would break discovery for all 30
      providers) and the credential-visibility choice (design D3 — `username`/`password` declared
      explicitly because the shared helpers return frozen fields with no `visible_when`).
- [x] 5.3 Note in the Session log that plan.md steps 9-11 (unit tests) are now unblocked, and that
      step 8 remains the prerequisite for 10 and 11.
