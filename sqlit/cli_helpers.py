"""CLI helpers for building provider-specific parsers and configs."""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from .config import ConnectionConfig
from .db.schema import ConnectionSchema, FieldType

CONNECTION_ARG_NAMES = {
    "name",
    "server",
    "host",
    "port",
    "database",
    "username",
    "password",
    "file_path",
    "auth_type",
    "supabase_region",
    "supabase_project_id",
    "ssh_enabled",
    "ssh_host",
    "ssh_port",
    "ssh_username",
    "ssh_auth_type",
    "ssh_key_path",
    "ssh_password",
    "driver",
    "oracle_role",
}


def add_schema_arguments(
    parser: argparse.ArgumentParser,
    schema: ConnectionSchema,
    *,
    include_name: bool,
    name_required: bool,
) -> None:
    """Add schema-driven arguments to a parser."""
    if include_name:
        parser.add_argument(
            "--name",
            "-n",
            required=name_required,
            help="Connection name",
        )

    for field in schema.fields:
        arg = f"--{field.name.replace('_', '-')}"
        help_text = field.description or field.placeholder or field.label
        kwargs: dict[str, Any] = {
            "help": help_text,
            "dest": field.name,
        }

        if field.name == "server":
            parser.add_argument(arg, "--host", **kwargs)
            continue

        if field.name == "ssh_enabled":
            parser.add_argument(arg, action="store_true", help=help_text, dest=field.name)
            continue

        if field.field_type in (FieldType.SELECT, FieldType.DROPDOWN) and field.options:
            kwargs["choices"] = [opt.value for opt in field.options]

        if field.default:
            kwargs["default"] = field.default

        if field.required and field.visible_when is None:
            kwargs["required"] = True

        parser.add_argument(arg, **kwargs)


def build_connection_config_from_args(
    schema: ConnectionSchema,
    args: Any,
    *,
    name: str | None,
    default_name: str | None = None,
    strict: bool = True,
) -> ConnectionConfig:
    """Build a ConnectionConfig from CLI args based on a provider schema."""
    raw_values = _extract_raw_values(schema, args)

    missing = _find_missing_required_fields(schema, raw_values)
    if missing:
        missing_args = ", ".join(f"--{field.replace('_', '-')}" for field in missing)
        raise ValueError(f"Missing required fields: {missing_args}")

    if strict:
        extras = _find_unexpected_fields(schema, args)
        if extras:
            extras_args = ", ".join(f"--{field.replace('_', '-')}" for field in extras)
            raise ValueError(f"Unexpected fields for {schema.display_name}: {extras_args}")

    config_name = name or default_name or f"Temp {schema.display_name}"
    config_values = {
        "name": config_name,
        "db_type": schema.db_type,
    }

    # Fields where None means "not set" vs "" means "explicitly empty"
    nullable_fields = {"password", "ssh_password"}

    for field in schema.fields:
        value = raw_values.get(field.name, "")
        if value is None and field.name not in nullable_fields:
            value = ""
        if field.name == "ssh_enabled":
            if isinstance(value, bool):
                config_values[field.name] = value
            else:
                config_values[field.name] = str(value).lower() == "enabled"
        else:
            config_values[field.name] = value

    if "port" in config_values and not config_values["port"]:
        config_values["port"] = schema.default_port or ""

    if schema.has_advanced_auth:
        auth_type = config_values.get("auth_type") or "sql"
        config_values["auth_type"] = auth_type
        config_values["trusted_connection"] = auth_type == "windows"

    return ConnectionConfig(**config_values)


def _extract_raw_values(schema: ConnectionSchema, args: Any) -> dict[str, Any]:
    raw_values: dict[str, Any] = {}
    for field in schema.fields:
        value = getattr(args, field.name, None)
        if field.name == "ssh_enabled" and isinstance(value, bool):
            value = "enabled" if value else "disabled"
        if (value is None or value == "") and field.default:
            value = field.default
        raw_values[field.name] = value
    return raw_values


def _find_missing_required_fields(schema: ConnectionSchema, raw_values: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in schema.fields:
        if not field.required:
            continue
        if field.visible_when and not field.visible_when(raw_values):
            continue
        value = raw_values.get(field.name)
        if value is None or value == "":
            missing.append(field.name)
    return missing


def _find_unexpected_fields(schema: ConnectionSchema, args: Any) -> list[str]:
    allowed = {field.name for field in schema.fields}
    extras: list[str] = []
    for field in CONNECTION_ARG_NAMES:
        if field in allowed or field == "name":
            continue
        value = getattr(args, field, None)
        if value is None or value == "" or value is False:
            continue
        extras.append(field)
    return extras


def iter_schema_arg_names(schema: ConnectionSchema) -> Iterable[str]:
    return (field.name for field in schema.fields)
