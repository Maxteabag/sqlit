"""Schema-based validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlit.domains.connections.providers.model import ConfigValidator
from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema, FieldType


@dataclass
class SchemaConfigValidator(ConfigValidator):
    schema: ConnectionSchema

    def normalize(self, config: Any) -> Any:
        endpoint = getattr(config, "tcp_endpoint", None)
        if (
            endpoint
            and not endpoint.port
            and self.schema.default_port
            and any(field.name == "port" for field in self.schema.fields)
        ):
            endpoint.port = self.schema.default_port
        return config

    def validate(self, config: Any) -> None:
        values = config.to_form_values()
        for field in self.schema.fields:
            if field.visible_when and not field.visible_when(values):
                continue
            if field.required:
                value = values.get(field.name)
                if field.field_type == FieldType.PASSWORD and value in (None, ""):
                    # Passwords can be prompted at connect time or explicitly empty.
                    continue
                if value is None or str(value).strip() == "":
                    raise ValueError(f"{field.label} is required")
