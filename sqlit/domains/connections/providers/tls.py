"""TLS helpers for database adapters."""

from __future__ import annotations

from typing import Any

TLS_MODE_DEFAULT = "default"
TLS_MODE_DISABLE = "disable"
TLS_MODE_REQUIRE = "require"
TLS_MODE_VERIFY_CA = "verify-ca"
TLS_MODE_VERIFY_FULL = "verify-full"

TLS_MODES = {
    TLS_MODE_DEFAULT,
    TLS_MODE_DISABLE,
    TLS_MODE_REQUIRE,
    TLS_MODE_VERIFY_CA,
    TLS_MODE_VERIFY_FULL,
}


def normalize_tls_mode(value: Any) -> str:
    mode = str(value).lower() if value else TLS_MODE_DEFAULT
    return mode if mode in TLS_MODES else TLS_MODE_DEFAULT


def get_tls_mode(config: Any) -> str:
    return normalize_tls_mode(config.get_option("tls_mode", TLS_MODE_DEFAULT))


def tls_mode_verifies_cert(mode: str) -> bool:
    return mode in {TLS_MODE_VERIFY_CA, TLS_MODE_VERIFY_FULL}


def tls_mode_verifies_hostname(mode: str) -> bool:
    return mode == TLS_MODE_VERIFY_FULL


def get_tls_files(config: Any) -> tuple[str, str, str, str]:
    def _get_value(key: str) -> str:
        value = config.get_option(key, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return ""

    return (
        _get_value("tls_ca"),
        _get_value("tls_cert"),
        _get_value("tls_key"),
        _get_value("tls_key_password"),
    )
