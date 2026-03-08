"""Credentials storage command handler."""

from __future__ import annotations

from typing import Any

from .router import register_command_handler


def _migrate_credentials(
    app: Any,
    old_service: Any,
    new_service: Any,
) -> tuple[int, int]:
    """Migrate credentials from old service to new service.

    Returns:
        Tuple of (migrated_count, error_count).
    """
    migrated = 0
    errors = 0

    for conn in getattr(app, "connections", []):
        name = getattr(conn, "name", None)
        if not name:
            continue

        # Migrate database password
        try:
            db_pw = old_service.get_password(name)
            if db_pw:
                new_service.set_password(name, db_pw)
                migrated += 1
        except Exception:
            errors += 1

        # Migrate SSH password
        try:
            ssh_pw = old_service.get_ssh_password(name)
            if ssh_pw:
                new_service.set_ssh_password(name, ssh_pw)
                migrated += 1
        except Exception:
            errors += 1

    return migrated, errors


def _handle_credentials_command(app: Any, cmd: str, args: list[str]) -> bool:
    if cmd != "credentials":
        return False

    from sqlit.domains.connections.app.credentials import (
        ALLOW_PLAINTEXT_CREDENTIALS_SETTING,
        KeyringCredentialsService,
        PlaintextFileCredentialsService,
        build_credentials_service,
        is_keyring_usable,
        reset_credentials_service,
    )

    value = args[0].lower() if args else ""

    if value == "plaintext":
        settings = app.services.settings_store.load_all()
        was_plaintext = settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING) is True

        # Try to migrate from keyring if switching
        migrated = 0
        if not was_plaintext and is_keyring_usable():
            try:
                old_service = KeyringCredentialsService()
                new_service = PlaintextFileCredentialsService()
                migrated, _ = _migrate_credentials(app, old_service, new_service)
            except Exception:
                pass  # Migration is best-effort

        # Enable plaintext storage
        settings[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = True
        app.services.settings_store.save_all(settings)

        # Rebuild credentials service
        reset_credentials_service()
        app.services.credentials_service = build_credentials_service(app.services.settings_store)
        if hasattr(app.services.connection_store, "set_credentials_service"):
            app.services.connection_store.set_credentials_service(app.services.credentials_service)

        msg = "Credentials will be stored as plaintext in ~/.sqlit/ (protected folder)"
        if migrated > 0:
            msg += f" ({migrated} password(s) migrated from keyring)"
        app.notify(msg)
        return True

    if value == "keyring":
        from sqlit.shared.core.store import CONFIG_DIR

        settings = app.services.settings_store.load_all()
        was_plaintext = settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING) is True

        if not is_keyring_usable():
            app.notify("Keyring unavailable. Cannot switch to keyring storage.", severity="warning")
            return True

        # Try to migrate from plaintext if switching
        migrated = 0
        if was_plaintext:
            try:
                old_service = PlaintextFileCredentialsService()
                new_service = KeyringCredentialsService()
                migrated, _ = _migrate_credentials(app, old_service, new_service)
            except Exception:
                pass  # Migration is best-effort

            # Clear plaintext credentials file after migration
            try:
                creds_file = CONFIG_DIR / "credentials.json"
                if creds_file.exists():
                    creds_file.unlink()
            except Exception:
                pass  # Best-effort cleanup

        # Switch to keyring
        settings[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = False
        app.services.settings_store.save_all(settings)

        # Rebuild credentials service
        reset_credentials_service()
        app.services.credentials_service = build_credentials_service(app.services.settings_store)
        if hasattr(app.services.connection_store, "set_credentials_service"):
            app.services.connection_store.set_credentials_service(app.services.credentials_service)

        msg = "Credentials will be stored in system keyring"
        if migrated > 0:
            msg += f" ({migrated} password(s) migrated from plaintext)"
        app.notify(msg)
        return True

    if not value:
        # Show current status
        settings = app.services.settings_store.load_all()
        allow_plaintext = settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING)
        keyring_ok = is_keyring_usable()

        if allow_plaintext:
            app.notify("Credentials: plaintext (~/.sqlit/credentials.json)")
        elif keyring_ok:
            app.notify("Credentials: system keyring")
        else:
            app.notify("Credentials: keyring unavailable, passwords not persisted", severity="warning")
        return True

    app.notify("Usage: :credentials [plaintext|keyring]", severity="warning")
    return True


register_command_handler(_handle_credentials_command)
