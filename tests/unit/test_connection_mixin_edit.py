from __future__ import annotations

from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.ui.mixins.connection import ConnectionMixin
from sqlit.domains.explorer.domain.tree_nodes import ConnectionNode


def test_get_connection_config_from_data_accepts_connection_node() -> None:
    mixin = ConnectionMixin()
    config = ConnectionConfig(
        name="NumberNinja",
        db_type="supabase",
        endpoint=TcpEndpoint(),
    )
    node = ConnectionNode(config=config)

    assert mixin._get_connection_config_from_data(node) is config
