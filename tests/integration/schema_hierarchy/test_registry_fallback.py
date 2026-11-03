"""Every registered provider participates in the explorer capability contract.

This integrates the real provider registry and tree builder without connecting
to cloud accounts. It is fallback/dispatch coverage, not live database evidence.
"""

from types import SimpleNamespace

import pytest
from textual.widgets import Tree

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.catalog import get_provider, get_supported_db_types
from sqlit.domains.explorer.domain.tree_nodes import ConnectionNode, SchemaNode
from sqlit.domains.explorer.ui.tree import builder, loaders


@pytest.mark.parametrize("name", get_supported_db_types())
def test_every_provider_routes_hierarchy_by_declared_capability(name, monkeypatch):
    provider = get_provider(name)
    config = ConnectionConfig.from_dict({"name": "Capability check", "db_type": name})
    tree = Tree("root")
    parent = tree.root.add("Connection", data=ConnectionNode(config))
    host = SimpleNamespace(current_provider=provider, services=SimpleNamespace(settings_store={"explorer_hierarchy": "schema"}))
    loaded = []
    monkeypatch.setattr(loaders, "load_folder_async", lambda *args: loaded.append(args))
    builder.add_database_object_nodes(host, parent, None)
    if provider.capabilities.supports_schema_grouping:
        assert name in {"postgresql", "mssql", "snowflake", "supabase"}
        assert len(loaded) == 1 and loaded[0][2].folder_type == "schemas"
    else:
        assert not loaded
        assert not any(isinstance(n.data, SchemaNode) for n in parent.children)
        assert len(parent.children) == len(provider.explorer_nodes.get_root_folders(provider.capabilities))
