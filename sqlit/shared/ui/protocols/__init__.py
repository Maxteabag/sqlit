"""Protocol definitions for mixin type safety."""

from __future__ import annotations

from typing import Protocol

from sqlit.shared.ui.protocols.autocomplete import AutocompleteProtocol
from sqlit.shared.ui.protocols.connections import ConnectionsProtocol
from sqlit.shared.ui.protocols.core import TextualAppProtocol
from sqlit.shared.ui.protocols.explorer import ExplorerProtocol
from sqlit.shared.ui.protocols.lifecycle import LifecycleProtocol
from sqlit.shared.ui.protocols.metadata import MetadataHelpersProtocol
from sqlit.shared.ui.protocols.mixins import (
    AutocompleteMixinHost,
    ConnectionMixinHost,
    QueryMixinHost,
    ResultsFilterMixinHost,
    ResultsMixinHost,
    TreeFilterMixinHost,
    TreeMixinHost,
    UINavigationMixinHost,
)
from sqlit.shared.ui.protocols.query import QueryProtocol
from sqlit.shared.ui.protocols.results import ResultsProtocol
from sqlit.shared.ui.protocols.screens import ThemeScreenAppProtocol
from sqlit.shared.ui.protocols.startup import StartupProtocol
from sqlit.shared.ui.protocols.ui_navigation import UINavigationProtocol
from sqlit.shared.ui.protocols.vim import VimModeProtocol
from sqlit.shared.ui.protocols.widgets import WidgetAccessProtocol


class AppProtocol(
    TextualAppProtocol,
    WidgetAccessProtocol,
    MetadataHelpersProtocol,
    ConnectionsProtocol,
    VimModeProtocol,
    ExplorerProtocol,
    QueryProtocol,
    AutocompleteProtocol,
    ResultsProtocol,
    UINavigationProtocol,
    StartupProtocol,
    LifecycleProtocol,
    Protocol,
):
    """Composite protocol for the SQLit Textual App."""

    pass


__all__ = [
    "AppProtocol",
    "AutocompleteMixinHost",
    "AutocompleteProtocol",
    "ConnectionMixinHost",
    "ConnectionsProtocol",
    "ExplorerProtocol",
    "LifecycleProtocol",
    "MetadataHelpersProtocol",
    "QueryMixinHost",
    "QueryProtocol",
    "ResultsFilterMixinHost",
    "ResultsMixinHost",
    "ResultsProtocol",
    "StartupProtocol",
    "TextualAppProtocol",
    "ThemeScreenAppProtocol",
    "TreeFilterMixinHost",
    "TreeMixinHost",
    "UINavigationMixinHost",
    "UINavigationProtocol",
    "VimModeProtocol",
    "WidgetAccessProtocol",
]
