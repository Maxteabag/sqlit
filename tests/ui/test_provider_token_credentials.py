"""Connection forms must preserve protected token credentials without extra prompts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from sqlit.domains.connections.providers.registry import get_supported_db_types
from tests.ui.conftest import ConnectionScreenTestApp
from tests.unit.test_provider_credential_aliases import CASES, config_for


@pytest.mark.parametrize(('provider', 'selector', 'mode', 'field'), CASES)
async def test_token_form_round_trip_and_test_connection(provider, selector, mode, field, monkeypatch):
    if provider not in get_supported_db_types():
        pytest.skip('Provider is not part of this branch')
    cfg = config_for(provider, selector, mode, field)
    app = ConnectionScreenTestApp(config=cfg, editing=True)
    async with app.run_test(size=(120, 45)) as pilot:
        screen = app.screen
        await pilot.pause()
        assert screen.query_one(f'#field-{field}').value == 'SYNTHETIC_SECRET'
        screen.query_one(f'#field-{field}').value = 'EDITED_SECRET'
        await pilot.pause()
        tested = []
        monkeypatch.setattr(screen, '_driver_status_controller', lambda: SimpleNamespace(missing_driver_error=None))
        monkeypatch.setattr(screen, '_run_test', tested.append)
        screen.action_test_connection()
        assert len(tested) == 1, 'Token auth opened an unrelated password prompt'
        assert tested[0].get_option(field) == 'EDITED_SECRET'
        assert field not in tested[0].options
        assert tested[0].tcp_endpoint.password == 'EDITED_SECRET'
