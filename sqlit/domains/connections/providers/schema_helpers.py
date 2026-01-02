"""Shared connection schema types and helpers.

Schema definitions live in each provider's schema.py module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class FieldType(Enum):
    TEXT = "text"
    PASSWORD = "password"
    SELECT = "select"
    DROPDOWN = "dropdown"
    FILE = "file"


@dataclass(frozen=True)
class SelectOption:
    """An option for a select field."""

    value: str
    label: str


@dataclass(frozen=True)
class SchemaField:
    name: str
    label: str
    field_type: FieldType = FieldType.TEXT
    required: bool = False
    default: str = ""
    placeholder: str = ""
    description: str = ""
    options: tuple[SelectOption, ...] = ()
    visible_when: Callable[[dict], bool] | None = None
    group: str | None = None
    advanced: bool = False
    tab: str = "general"


@dataclass(frozen=True)
class ConnectionSchema:
    db_type: str
    display_name: str
    fields: tuple[SchemaField, ...]
    supports_ssh: bool = True
    is_file_based: bool = False
    has_advanced_auth: bool = False
    default_port: str = ""
    requires_auth: bool = True  # Whether this database requires authentication


# Common field templates

def _server_field(placeholder: str = "localhost") -> SchemaField:
    return SchemaField(
        name="server",
        label="Server",
        placeholder=placeholder,
        required=True,
        group="server_port",
    )


def _port_field(default: str) -> SchemaField:
    return SchemaField(
        name="port",
        label="Port",
        placeholder=default,
        default=default,
        group="server_port",
    )


def _database_field(placeholder: str = "(empty = browse all)", required: bool = False) -> SchemaField:
    return SchemaField(
        name="database",
        label="Database",
        placeholder=placeholder,
        required=required,
    )


def _username_field(required: bool = True) -> SchemaField:
    return SchemaField(
        name="username",
        label="Username",
        placeholder="username",
        required=required,
        group="credentials",
    )


def _password_field() -> SchemaField:
    return SchemaField(
        name="password",
        label="Password",
        field_type=FieldType.PASSWORD,
        placeholder="(empty = ask every connect)",
        group="credentials",
    )


def _file_path_field(placeholder: str) -> SchemaField:
    return SchemaField(
        name="file_path",
        label="Database File",
        field_type=FieldType.FILE,
        placeholder=placeholder,
        required=True,
    )


def _ssh_enabled(v: dict) -> bool:
    return v.get("ssh_enabled") == "enabled"


def _ssh_auth_is_key(v: dict) -> bool:
    return _ssh_enabled(v) and v.get("ssh_auth_type") == "key"


def _ssh_auth_is_password(v: dict) -> bool:
    return _ssh_enabled(v) and v.get("ssh_auth_type") == "password"


def _get_ssh_fields() -> tuple[SchemaField, ...]:
    return (
        SchemaField(
            name="ssh_enabled",
            label="Tunnel",
            field_type=FieldType.SELECT,
            options=(
                SelectOption("disabled", "Disabled"),
                SelectOption("enabled", "Enabled"),
            ),
            default="disabled",
            tab="ssh",
        ),
        SchemaField(
            name="ssh_host",
            label="Host",
            placeholder="bastion.example.com",
            required=True,
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_port",
            label="Port",
            placeholder="22",
            default="22",
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_username",
            label="Username",
            placeholder="ubuntu",
            required=True,
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_auth_type",
            label="Auth",
            field_type=FieldType.SELECT,
            options=(
                SelectOption("key", "Key File"),
                SelectOption("password", "Password"),
            ),
            default="key",
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_key_path",
            label="Key Path",
            field_type=FieldType.FILE,
            placeholder="~/.ssh/id_rsa",
            default="~/.ssh/id_rsa",
            visible_when=_ssh_auth_is_key,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_password",
            label="Password",
            field_type=FieldType.PASSWORD,
            placeholder="(empty = ask every connect)",
            visible_when=_ssh_auth_is_password,
            tab="ssh",
        ),
    )


SSH_FIELDS = _get_ssh_fields()


def _tls_mode_is_custom(v: dict) -> bool:
    mode = str(v.get("tls_mode", "default")).lower()
    return mode not in {"", "default", "disable"}


def _get_tls_mode_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("default", "Default (driver)"),
        SelectOption("disable", "Disable"),
        SelectOption("require", "Require (no verify)"),
        SelectOption("verify-ca", "Verify CA"),
        SelectOption("verify-full", "Verify Full"),
    )


def _get_tls_mode_field() -> SchemaField:
    return SchemaField(
        name="tls_mode",
        label="TLS Mode",
        field_type=FieldType.SELECT,
        options=_get_tls_mode_options(),
        default="default",
        tab="tls",
    )


def _get_tls_cert_fields() -> tuple[SchemaField, ...]:
    return (
        SchemaField(
            name="tls_ca",
            label="CA Certificate",
            field_type=FieldType.FILE,
            placeholder="/path/to/ca.pem",
            visible_when=_tls_mode_is_custom,
            tab="tls",
        ),
        SchemaField(
            name="tls_cert",
            label="Client Certificate",
            field_type=FieldType.FILE,
            placeholder="/path/to/client.pem",
            visible_when=_tls_mode_is_custom,
            tab="tls",
        ),
        SchemaField(
            name="tls_key",
            label="Client Key",
            field_type=FieldType.FILE,
            placeholder="/path/to/client.key",
            visible_when=_tls_mode_is_custom,
            tab="tls",
        ),
        SchemaField(
            name="tls_key_password",
            label="Key Password",
            field_type=FieldType.PASSWORD,
            placeholder="(optional)",
            visible_when=_tls_mode_is_custom,
            tab="tls",
        ),
    )


TLS_MODE_FIELD = _get_tls_mode_field()
TLS_CERT_FIELDS = _get_tls_cert_fields()
TLS_FIELDS = (TLS_MODE_FIELD,) + TLS_CERT_FIELDS


def _get_aws_region_options() -> tuple[SelectOption, ...]:
    """AWS regions shared by Supabase, Athena, and other AWS-based services."""
    regions = (
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "ca-central-1",
        "sa-east-1",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "eu-central-1",
        "eu-central-2",
        "eu-north-1",
        "ap-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-northeast-1",
        "ap-northeast-2",
    )
    return tuple(SelectOption(r, r) for r in regions)


def _get_str_option(config: dict[str, Any], key: str, default: str | None = None) -> str | None:
    value = config.get(key, default)
    if isinstance(value, str):
        return value
    return None
