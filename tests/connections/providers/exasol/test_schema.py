"""Tests for the Exasol schema's conditional credential-field visibility.

Pins the rule that only the selected authentication method's credential fields
are shown: pyexasol's login branches on token truthiness, so a form that can
collect a password and a token at the same time silently changes the auth path.
No driver is involved - these are pure predicate evaluations.
"""

from __future__ import annotations

import pytest

from sqlit.domains.connections.providers.exasol.schema import SCHEMA

CREDENTIAL_FIELDS = ("username", "password", "access_token", "refresh_token")
UNCONDITIONAL_FIELDS = ("server", "port", "authenticator", "schema")
AUTHENTICATORS = ("password", "access_token", "refresh_token")


def _visible_fields(values: dict) -> set[str]:
    """Names the form shows for these values; no predicate means always visible."""
    return {field.name for field in SCHEMA.fields if field.visible_when is None or field.visible_when(values)}


def _credential_visibility(values: dict) -> dict[str, bool]:
    visible = _visible_fields(values)
    return {name: name in visible for name in CREDENTIAL_FIELDS}


def test_password_authenticator_shows_username_and_password() -> None:
    assert _credential_visibility({"authenticator": "password"}) == {
        "username": True,
        "password": True,
        "access_token": False,
        "refresh_token": False,
    }


def test_access_token_authenticator_shows_only_the_access_token() -> None:
    assert _credential_visibility({"authenticator": "access_token"}) == {
        "username": False,
        "password": False,
        "access_token": True,
        "refresh_token": False,
    }


def test_refresh_token_authenticator_shows_only_the_refresh_token() -> None:
    assert _credential_visibility({"authenticator": "refresh_token"}) == {
        "username": False,
        "password": False,
        "access_token": False,
        "refresh_token": True,
    }


def test_absent_authenticator_falls_back_to_password() -> None:
    # Each predicate defaults its lookup to "password", so an empty form is
    # indistinguishable from an explicit password selection.
    assert _visible_fields({}) == _visible_fields({"authenticator": "password"})


def test_unrecognised_authenticator_shows_no_credential_fields() -> None:
    # The predicates compare for equality rather than negating each other, so an
    # unknown value hides all three methods instead of leaking one of them.
    assert _credential_visibility({"authenticator": "kerberos"}) == {
        "username": False,
        "password": False,
        "access_token": False,
        "refresh_token": False,
    }


def test_unconditional_fields_carry_no_predicate() -> None:
    fields = {field.name: field for field in SCHEMA.fields}
    for name in UNCONDITIONAL_FIELDS:
        assert fields[name].visible_when is None, f"{name} must not be conditional"


@pytest.mark.parametrize("authenticator", AUTHENTICATORS)
def test_unconditional_fields_stay_visible_under_every_authenticator(authenticator: str) -> None:
    visible = _visible_fields({"authenticator": authenticator})
    for name in UNCONDITIONAL_FIELDS:
        assert name in visible
