## ADDED Requirements

### Requirement: Exasol declares a connection schema
The provider package SHALL contain `schema.py` exporting a module-level `SCHEMA` of type
`ConnectionSchema` with `db_type="exasol"`, `display_name="Exasol"`, `default_port="8563"` and
`has_advanced_auth=True`. `supports_ssh` MUST be `True` (the dataclass default) so the shared tunnel
fields apply.

`db_type` and `display_name` are pinned by `tests/test_schema_capabilities.py`:
`test_provider_schema_ids_match_keys` requires `SCHEMA.db_type` to equal the registry key, and
`test_display_names_match_schema` requires `SCHEMA.display_name` to equal
`get_display_name("exasol")`, which resolves from `ProviderSpec`.

#### Scenario: Schema identity
- **WHEN** `SCHEMA` is inspected
- **THEN** `SCHEMA.db_type == "exasol"`
- **AND** `SCHEMA.display_name == "Exasol"`
- **AND** `SCHEMA.default_port == "8563"`
- **AND** `SCHEMA.has_advanced_auth is True`
- **AND** `SCHEMA.supports_ssh is True`

#### Scenario: Schema is reachable through the registry
- **WHEN** `get_connection_schema("exasol")` is called
- **THEN** it returns the same `ConnectionSchema` object exported by `schema.py`

### Requirement: Schema declares the Exasol field set
`SCHEMA.fields` SHALL contain, in order: `server`, `port`, `authenticator`, `username`, `password`,
`access_token`, `refresh_token`, `schema` — followed by `SSH_FIELDS` and then `TLS_FIELDS`
appended as tuples.

`server` and `port` SHALL use the shared `_server_field()` and `_port_field("8563")` helpers.
`schema` SHALL be optional with the placeholder `(empty = browse all)`, matching the adapter's
`default_schema` of `""`.

The field names are fixed by the already-shipped `adapter.py`, which reads `authenticator`,
`access_token`, `refresh_token` and `schema` via `config.get_option(...)`, and takes `user` and
`password` from `config.tcp_endpoint`.

#### Scenario: Endpoint and option fields are present
- **WHEN** `{f.name for f in SCHEMA.fields}` is computed
- **THEN** it is a superset of `{"server", "port", "authenticator", "username", "password", "access_token", "refresh_token", "schema"}`

#### Scenario: Shared SSH and TLS tails are appended
- **WHEN** `SCHEMA.fields` is inspected
- **THEN** every field in `SSH_FIELDS` is present
- **AND** every field in `TLS_FIELDS` is present, including `tls_mode`
- **AND** they appear after the Exasol-specific fields

#### Scenario: No database field
- **WHEN** `SCHEMA.fields` is inspected
- **THEN** no field is named `database`, because the adapter reports
  `supports_multiple_databases is False` and `get_databases()` returns an empty list

#### Scenario: Schema field is optional
- **WHEN** the `schema` field is inspected
- **THEN** `required is False`
- **AND** its placeholder communicates that leaving it empty browses all schemas

### Requirement: Authentication method is chosen from a dropdown
The `authenticator` field SHALL be a `FieldType.DROPDOWN` with `default="password"` and exactly
three options, in this order:

| value | label |
|---|---|
| `password` | `Username & Password` |
| `access_token` | `OpenID Access Token` |
| `refresh_token` | `OpenID Refresh Token` |

The values MUST match the branch labels in `adapter.connect()`, which compares
`config.get_option("authenticator", "password")` against `"access_token"` and `"refresh_token"` and
treats anything else as password auth.

The field MUST NOT be named `auth_type`: `ConnectionConfig.from_dict` special-cases that key as a
legacy top-level field and hoists it into `options`.

#### Scenario: Dropdown options
- **WHEN** the `authenticator` field is inspected
- **THEN** `field_type is FieldType.DROPDOWN`
- **AND** `default == "password"`
- **AND** its option values are `("password", "access_token", "refresh_token")`

#### Scenario: CLI exposes the choice
- **WHEN** the CLI parser is built from `SCHEMA`
- **THEN** an `--authenticator` flag exists
- **AND** its accepted `choices` are the three option values

#### Scenario: Field is not named auth_type
- **WHEN** `{f.name for f in SCHEMA.fields}` is computed
- **THEN** `"auth_type"` is absent

### Requirement: Credential fields are visible only for their own authentication method
Each credential field SHALL carry a `visible_when` predicate reading `authenticator` from the form
values, per this matrix:

| `authenticator` | visible credential fields | hidden credential fields |
|---|---|---|
| `password` (default) | `username`, `password` | `access_token`, `refresh_token` |
| `access_token` | `access_token` | `username`, `password`, `refresh_token` |
| `refresh_token` | `refresh_token` | `username`, `password`, `access_token` |

`username` and `password` MUST therefore be declared as explicit `SchemaField`s rather than reusing
`_username_field()` / `_password_field()`, whose returned frozen `SchemaField` carries
`visible_when=None`.

`username` SHALL be `required=True` and `password` SHALL be `required=False`; both SHALL use
`group="credentials"`. `access_token` and `refresh_token` SHALL be `FieldType.PASSWORD` so their
values are masked and treated as promptable secrets.

Visibility is behaviour, not presentation: `providers/validation.py:30` skips `required` checks on
hidden fields, and `cli/helpers.py:65` marks a flag argparse-required only when
`visible_when is None`.

#### Scenario: Password auth shows only username and password
- **WHEN** `visible_when({"authenticator": "password"})` is evaluated for each credential field
- **THEN** `username` and `password` are visible
- **AND** `access_token` and `refresh_token` are hidden

#### Scenario: Access token auth hides username and password
- **WHEN** `visible_when({"authenticator": "access_token"})` is evaluated for each credential field
- **THEN** `access_token` is visible
- **AND** `username`, `password` and `refresh_token` are hidden

#### Scenario: Refresh token auth hides username and password
- **WHEN** `visible_when({"authenticator": "refresh_token"})` is evaluated for each credential field
- **THEN** `refresh_token` is visible
- **AND** `username`, `password` and `access_token` are hidden

#### Scenario: Missing authenticator value falls back to password auth
- **WHEN** `visible_when({})` is evaluated — no `authenticator` key at all
- **THEN** `username` and `password` are visible
- **AND** both token fields are hidden
- **AND** this matches `adapter.connect()`, whose `get_option("authenticator", "password")` default
  takes the password branch

#### Scenario: Token auth does not demand a username
- **WHEN** a config with `authenticator == "access_token"` and an empty `username` is validated by
  `SchemaConfigValidator.validate`
- **THEN** no `ValueError` is raised, because the hidden `username` field's `required` flag is
  skipped

#### Scenario: Password auth demands a username
- **WHEN** a config with `authenticator == "password"` and an empty `username` is validated
- **THEN** `ValueError` is raised naming the Username field

#### Scenario: Username is not a globally required CLI flag
- **WHEN** the CLI parser is built from `SCHEMA`
- **THEN** `--username` is not argparse-required, because the field defines `visible_when`

#### Scenario: Token fields are masked
- **WHEN** the `access_token` and `refresh_token` fields are inspected
- **THEN** both have `field_type is FieldType.PASSWORD`

### Requirement: Exasol is a member of the DatabaseType enum
`DatabaseType` in `sqlit/domains/connections/domain/config.py` SHALL include
`EXASOL = "exasol"`, placed between `DB2` and `FIREBIRD`.

This is required by `test_database_type_enum_matches_schema`, which asserts
`{t.value for t in DatabaseType} == set(get_supported_db_types())` as an exact set equality — so
the enum member and the provider registration must land together.

#### Scenario: Enum member exists
- **WHEN** `DatabaseType.EXASOL` is accessed
- **THEN** its value is `"exasol"`

#### Scenario: Enum and provider catalog agree
- **WHEN** `test_database_type_enum_matches_schema` runs
- **THEN** the enum value set exactly equals `set(get_supported_db_types())`
- **AND** both sets contain `"exasol"`

### Requirement: Exasol appears in the connection picker
`DATABASE_TYPE_DISPLAY_ORDER` SHALL include `DatabaseType.EXASOL`, positioned after
`DatabaseType.TERADATA` among the enterprise engines.

`ui/screens/connection.py:331` builds the database-type `Select` options from exactly this list with
no further filtering, so a type absent from it is unreachable in the UI. No test covers the
constant's completeness, so omitting the entry fails silently — every test passes and Exasol is
still unselectable.

#### Scenario: Display order contains Exasol
- **WHEN** `DATABASE_TYPE_DISPLAY_ORDER` is inspected
- **THEN** `DatabaseType.EXASOL` is present
- **AND** it appears immediately after `DatabaseType.TERADATA`

#### Scenario: Picker renders an Exasol option
- **WHEN** the connection screen builds its database-type `Select`
- **THEN** an option labelled `Exasol` with value `exasol` is present

#### Scenario: Label resolves from the provider
- **WHEN** `get_database_type_labels()` is called
- **THEN** `labels[DatabaseType.EXASOL] == "Exasol"`

### Requirement: Exasol is registered as a provider
The provider package SHALL contain `provider.py` that builds a `ProviderSpec` and calls
`register_provider(SPEC)` at module scope, following `providers/teradata/provider.py`.

`SPEC` SHALL declare:

| Field | Value |
|---|---|
| `db_type` | `"exasol"` |
| `display_name` | `"Exasol"` |
| `schema_path` | `("sqlit.domains.connections.providers.exasol.schema", "SCHEMA")` |
| `supports_ssh` | `True` |
| `is_file_based` | `False` |
| `has_advanced_auth` | `True` |
| `default_port` | `"8563"` |
| `requires_auth` | `True` |
| `badge_label` | `"Exasol"` |
| `url_schemes` | `("exasol", "exa")` |

`display_name`, `db_type` and `default_port` MUST match `SCHEMA` exactly.

#### Scenario: Provider is discovered
- **WHEN** `get_supported_db_types()` is called
- **THEN** `"exasol"` is present
- **AND** the total provider count is 30

#### Scenario: Registry metadata resolves
- **WHEN** the registry is queried for `"exasol"`
- **THEN** `get_display_name("exasol") == "Exasol"`
- **AND** `get_default_port("exasol") == "8563"`
- **AND** `has_advanced_auth("exasol") is True`
- **AND** `supports_ssh("exasol") is True`
- **AND** `is_file_based("exasol") is False`

#### Scenario: URL schemes are claimed
- **WHEN** a connection URL with scheme `exasol://` or `exa://` is resolved
- **THEN** it maps to the Exasol provider

#### Scenario: Existing capability suite stays green
- **WHEN** `uv run pytest tests/test_schema_capabilities.py` is run
- **THEN** all 9 tests pass

### Requirement: Provider factory imports the adapter lazily
`SPEC.provider_factory` SHALL be a function that imports `ExasolAdapter` **inside its body** and
returns `build_adapter_provider(spec, SCHEMA, ExasolAdapter())`. `provider.py` MUST NOT import
`adapter.py` at module scope.

`provider.py` is imported for every provider during discovery, i.e. at startup; deferring the
adapter import keeps `adapter.py` and its `ssl` import off the startup path for a provider the user
may never select. Every existing provider does this.

#### Scenario: Adapter module is not imported at startup
- **WHEN** provider discovery completes without any Exasol connection being opened
- **THEN** `sqlit.domains.connections.providers.exasol.adapter` is absent from `sys.modules`

#### Scenario: Factory produces a working provider
- **WHEN** `SPEC.provider_factory(SPEC)` is called
- **THEN** a `DatabaseProvider` is returned
- **AND** its `schema` is the Exasol `SCHEMA`
- **AND** no `TypeError` about abstract methods is raised, since `ExasolAdapter` is concrete

#### Scenario: Registration needs no driver
- **WHEN** discovery, the picker and the capability suite run with `pyexasol` not installed
- **THEN** all succeed, because `_import_driver_module` runs only inside `connect()`

### Requirement: Docker detection recognises exasol/docker-db
`SPEC.docker_detector` SHALL be a `DockerDetector` with `image_patterns=("exasol/docker-db",)`,
`env_vars={}` and `default_user="sys"`.

`env_vars` is a **required** field on `DockerDetector` with no default. Omitting it raises
`TypeError` while `provider.py` is being imported during discovery, which breaks discovery for every
provider, not just Exasol. The empty mapping is also semantically correct: the `exasol/docker-db`
image takes no credential environment variables — its `sys` / `exasol` defaults are baked in — and
`get_credentials` resolves an empty mapping to `default_user`.

`default_user_requires_password` SHALL remain `False`, so `sys` is offered even when no password is
discovered.

#### Scenario: Image pattern matches
- **WHEN** `match_image("exasol/docker-db:latest-8")` is called
- **THEN** it returns `True`

#### Scenario: Unrelated image does not match
- **WHEN** `match_image("postgres:16")` is called on the Exasol detector
- **THEN** it returns `False`

#### Scenario: Default user is offered with no environment variables
- **WHEN** `get_credentials({})` is called
- **THEN** the returned `user` is `"sys"`
- **AND** no exception is raised for the empty `env_vars` mapping

#### Scenario: Detector construction does not break discovery
- **WHEN** `provider.py` is imported
- **THEN** no `TypeError` is raised for a missing `env_vars` argument

### Requirement: Connection display shows the target schema
`SPEC.display_info` SHALL render `host:port/SCHEMA` when a `schema` option is set, and fall back to
`host:port` when it is empty.

The default implementation (`adapter_provider.py:61`) appends `endpoint.database`, which Exasol never
populates — there is no `database` field and `supports_multiple_databases` is `False` — so without
this override two connections into the same cluster are indistinguishable in the list.

#### Scenario: Schema is shown when set
- **WHEN** `display_info` is called for a config with host `localhost`, port `8563` and the `schema`
  option `TEST_SQLIT`
- **THEN** the result is `localhost:8563/TEST_SQLIT`

#### Scenario: Falls back to host and port
- **WHEN** `display_info` is called for a config with no `schema` option
- **THEN** the result is `localhost:8563` with no trailing slash

### Requirement: The change leaves existing providers untouched
Registering Exasol SHALL NOT change behaviour for any of the 29 existing providers. The only shared
file modified is `domain/config.py`, by addition only: one enum member and one display-order entry.

`providers/exasol/adapter.py` MUST NOT be modified by this change.

#### Scenario: Existing providers still resolve
- **WHEN** `get_supported_db_types()` is called
- **THEN** all 29 previously registered types are still present

#### Scenario: Adapter is unchanged
- **WHEN** the diff for this change is inspected
- **THEN** `providers/exasol/adapter.py` does not appear in it

#### Scenario: Full unit suite is unaffected
- **WHEN** the unit-test job's pytest command is run
- **THEN** no previously passing test fails
