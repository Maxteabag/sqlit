"""Map mutually exclusive provider secrets onto the existing keyring credential.

A Databricks/Exasol connection uses one authentication secret at a time. Keeping
it in endpoint.password reuses the credential store's save/load/rename semantics;
provider-specific field names remain available to forms and CLI configuration.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if TYPE_CHECKING:
    from typing import Any

    from sqlit.domains.connections.domain.config import ConnectionConfig

_CREDENTIAL_MODES = {
    'databricks': ('auth_type', 'pat', {'pat': 'access_token', 'oauth-m2m': 'client_secret'}),
    'exasol': ('authenticator', 'password', {'access_token': 'access_token', 'refresh_token': 'refresh_token'}),
}


def credential_option(config: ConnectionConfig) -> str | None:
    definition = _CREDENTIAL_MODES.get(config.db_type)
    if definition is None:
        return None
    selector, default, aliases = definition
    mode = config.options.get(selector, config.extra_options.get(selector, default))
    return aliases.get(mode)


def secret_option_names(config: ConnectionConfig) -> frozenset[str]:
    definition = _CREDENTIAL_MODES.get(config.db_type)
    return frozenset(definition[2].values()) if definition else frozenset()


def normalize_credential_options(config: ConnectionConfig) -> None:
    definition = _CREDENTIAL_MODES.get(config.db_type)
    if definition is None:
        return
    selector, _, _ = definition
    config.options = dict(config.options)
    config.extra_options = dict(config.extra_options)
    if selector in config.extra_options:
        config.options.setdefault(selector, config.extra_options.pop(selector))
    selected = credential_option(config)
    for name in secret_option_names(config):
        extra_value = config.extra_options.pop(name, None)
        value = config.options.pop(name, extra_value)
        if name == selected and value is not None and config.tcp_endpoint is not None:
            config.tcp_endpoint.password = value


def without_secret_options(config: ConnectionConfig, options: dict[str, Any]) -> dict[str, Any]:
    names = secret_option_names(config)
    return {key: value for key, value in options.items() if key not in names}


def public_connection_url(config: ConnectionConfig) -> str | None:
    url = config.connection_url
    if not url or config.db_type not in _CREDENTIAL_MODES:
        return url
    parsed = urlsplit(url)
    secret_names = secret_option_names(config) | {'password'}
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if key not in secret_names]
    return urlunsplit(parsed._replace(netloc=parsed.netloc.rsplit('@', 1)[-1], query=urlencode(query)))
