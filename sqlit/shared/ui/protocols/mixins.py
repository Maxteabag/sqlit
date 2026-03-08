"""Composite protocols for individual mixin hosts."""

from __future__ import annotations

from typing import Protocol

from sqlit.shared.ui.protocols.autocomplete import AutocompleteProtocol
from sqlit.shared.ui.protocols.connections import ConnectionsProtocol
from sqlit.shared.ui.protocols.core import TextualAppProtocol
from sqlit.shared.ui.protocols.explorer import ExplorerProtocol
from sqlit.shared.ui.protocols.lifecycle import LifecycleProtocol
from sqlit.shared.ui.protocols.metadata import MetadataHelpersProtocol
from sqlit.shared.ui.protocols.query import QueryProtocol
from sqlit.shared.ui.protocols.results import ResultsProtocol
from sqlit.shared.ui.protocols.ui_navigation import UINavigationProtocol
from sqlit.shared.ui.protocols.vim import VimModeProtocol
from sqlit.shared.ui.protocols.widgets import WidgetAccessProtocol


class ConnectionMixinHost(
    TextualAppProtocol,
    WidgetAccessProtocol,
    ConnectionsProtocol,
    MetadataHelpersProtocol,
    ExplorerProtocol,
    AutocompleteProtocol,
    ResultsProtocol,
    UINavigationProtocol,
    QueryProtocol,
    LifecycleProtocol,
    Protocol,
):
    """Host protocol for connection-related mixins."""

    pass


class QueryMixinHost(
    TextualAppProtocol,
    WidgetAccessProtocol,
    ConnectionsProtocol,
    MetadataHelpersProtocol,
    ExplorerProtocol,
    ResultsProtocol,
    AutocompleteProtocol,
    QueryProtocol,
    UINavigationProtocol,
    VimModeProtocol,
    LifecycleProtocol,
    Protocol,
):
    """Host protocol for query mixins."""

    pass


class AutocompleteMixinHost(
    TextualAppProtocol,
    WidgetAccessProtocol,
    ConnectionsProtocol,
    MetadataHelpersProtocol,
    AutocompleteProtocol,
    VimModeProtocol,
    UINavigationProtocol,
    Protocol,
):
    """Host protocol for autocomplete mixins."""

    pass


class TreeMixinHost(
    TextualAppProtocol,
    WidgetAccessProtocol,
    ConnectionsProtocol,
    MetadataHelpersProtocol,
    ExplorerProtocol,
    AutocompleteProtocol,
    ResultsProtocol,
    QueryProtocol,
    UINavigationProtocol,
    LifecycleProtocol,
    Protocol,
):
    """Host protocol for explorer tree mixins."""

    pass


class TreeFilterMixinHost(
    WidgetAccessProtocol,
    ExplorerProtocol,
    UINavigationProtocol,
    Protocol,
):
    """Host protocol for tree filter mixins."""

    pass


class ResultsMixinHost(
    TextualAppProtocol,
    WidgetAccessProtocol,
    ResultsProtocol,
    QueryProtocol,
    UINavigationProtocol,
    VimModeProtocol,
    Protocol,
):
    """Host protocol for results mixins."""

    pass


class ResultsFilterMixinHost(
    TextualAppProtocol,
    WidgetAccessProtocol,
    ResultsProtocol,
    UINavigationProtocol,
    Protocol,
):
    """Host protocol for results filter mixins."""

    pass


class UINavigationMixinHost(
    TextualAppProtocol,
    WidgetAccessProtocol,
    ConnectionsProtocol,
    ResultsProtocol,
    QueryProtocol,
    AutocompleteProtocol,
    UINavigationProtocol,
    VimModeProtocol,
    Protocol,
):
    """Host protocol for UI navigation mixins."""

    pass
