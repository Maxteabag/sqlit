"""Styles for the connection configuration screen."""

CONNECTION_SCREEN_CSS = """
ConnectionScreen {
    align: center middle;
    background: transparent;
}

#connection-dialog {
    width: 62;
    height: auto;
    max-height: 38;
    border: solid $primary;
    background: $surface;
    padding: 1;
    border-title-align: left;
    border-title-color: $primary;
    border-title-background: $surface;
    border-title-style: bold;
    border-subtitle-align: right;
    border-subtitle-color: $primary;
    border-subtitle-background: $surface;
    border-subtitle-style: bold;
}

#connection-title {
    display: none;
}

#connection-dialog Input, #connection-dialog Select {
    margin-bottom: 0;
}

.field-container {
    position: relative;
    height: auto;
    border: solid $panel;
    background: $surface;
    padding: 0;
    margin-top: 0;
    border-title-align: left;
    border-title-color: $text-muted;
    border-title-background: $surface;
    border-title-style: none;
}

.field-container.hidden {
    display: none;
}

.field-container.invalid {
    border: solid $error;
    border-title-color: $error;
}

.field-container.focused {
    border: solid $primary;
    border-title-color: $primary;
}

.field-container.invalid.focused {
    border: solid $error;
    border-title-color: $error;
}

.field-container Input {
    border: none;
    height: 1;
    padding: 0;
    background: $surface;
}

.field-container Input:focus {
    border: none;
    background-tint: $foreground 5%;
}

.field-container Select {
    border: none;
    background: $surface;
    padding: 0;
}

.field-container .select-field {
    border: none;
    background: $surface;
    padding: 0;
}

#connection-tabs {
    height: 1fr;
}

TabbedContent {
    height: 1fr;
}

TabbedContent > ContentSwitcher {
    height: 1fr;
}

TabPane {
    height: 1fr;
    min-height: 18;
    overflow-y: auto;
}

Tab:disabled {
    text-style: strike;
}

Tab.has-error {
    color: $error;
}

#dynamic-fields-general {
    height: auto;
}

.field-group {
    height: auto;
}

.field-group.hidden {
    display: none;
}

.field-row {
    height: auto;
    width: 100%;
}

.field-flex {
    width: 1fr;
    height: auto;
}

.field-fixed {
    width: 10;
    height: auto;
    margin-left: 1;
}

.select-field {
    height: auto;
    max-height: 6;
    padding: 0;
    margin-bottom: 0;
}

.select-field > .option-list--option {
    padding: 0 1;
}

.error-text {
    color: $error;
    height: auto;
}

.error-text.hidden {
    display: none;
}

#test-status {
    height: auto;
    color: $text-muted;
    margin-top: 0;
}

#test-status.success {
    color: $success;
}

.file-field-row {
    width: 100%;
    height: 1;
}

.file-field-row Input {
    width: 1fr;
}

.browse-button {
    width: 5;
    min-width: 5;
    height: 1;
    border: none;
    margin-left: 1;
    padding: 0;
}
"""
