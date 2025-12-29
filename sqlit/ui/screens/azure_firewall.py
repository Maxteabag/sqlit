"""Azure SQL firewall rule creation screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from ...widgets import Dialog
from ..spinner import Spinner


class AzureFirewallScreen(ModalScreen[bool]):
    """Modal screen to add an Azure SQL firewall rule."""

    BINDINGS = [
        Binding("y", "add_rule", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    CSS = """
    AzureFirewallScreen {
        align: center middle;
        background: transparent;
    }

    #firewall-dialog {
        width: 60;
        height: auto;
        max-height: 16;
    }

    #firewall-message {
        margin-bottom: 1;
    }

    #firewall-details {
        color: $text-muted;
        margin-bottom: 1;
    }

    #firewall-status {
        color: $warning;
    }
    """

    def __init__(
        self,
        server_name: str,
        resource_group: str,
        subscription_id: str | None,
        ip_address: str,
    ):
        super().__init__()
        self.server_name = server_name
        self.resource_group = resource_group
        self.subscription_id = subscription_id
        self.ip_address = ip_address
        self._adding = False
        self._spinner: Spinner | None = None

    def compose(self) -> ComposeResult:
        shortcuts = [("Yes", "y"), ("No", "n")]
        with Dialog(id="firewall-dialog", title="Firewall Rule Required", shortcuts=shortcuts):
            yield Static(
                f"Your IP address [bold]{self.ip_address}[/] is not allowed to access this server.",
                id="firewall-message",
            )
            yield Static(
                f"Server: [bold]{self.server_name}[/]\n"
                f"Resource Group: {self.resource_group}",
                id="firewall-details",
            )
            yield Static(
                "Add a firewall rule to allow access?",
                id="firewall-prompt",
            )
            yield Static("", id="firewall-status")

    def _update_spinner_status(self, frame: str) -> None:
        """Update status with spinner frame."""
        status = self.query_one("#firewall-status", Static)
        status.update(f"[yellow]{frame}[/] [dim]Adding firewall rule...[/]")

    def action_add_rule(self) -> None:
        if self._adding:
            return
        self._adding = True
        self._spinner = Spinner(self, on_tick=self._update_spinner_status)
        self._spinner.start()
        self.run_worker(self._add_rule_worker, thread=True)

    def _add_rule_worker(self) -> None:
        from ...services.cloud_detector import add_azure_firewall_rule

        success, message = add_azure_firewall_rule(
            server_name=self.server_name,
            resource_group=self.resource_group,
            ip_address=self.ip_address,
            subscription_id=self.subscription_id,
        )
        self.app.call_from_thread(self._on_rule_added, success, message)

    def _on_rule_added(self, success: bool, message: str) -> None:
        if self._spinner:
            self._spinner.stop()
        if success:
            self.notify(message)
            self.notify("Retrying connection...", severity="information")
            self.dismiss(True)
        else:
            status = self.query_one("#firewall-status", Static)
            status.update(f"[red]{message}[/]")
            self._adding = False

    def action_cancel(self) -> None:
        if self._spinner:
            self._spinner.stop()
        self.dismiss(False)
