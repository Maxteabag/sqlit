"""Custom exceptions for the database layer."""


class MissingDriverError(ConnectionError):
    """Exception raised when a required database driver package is not installed."""

    def __init__(
        self,
        driver_name: str,
        extra_name: str,
        package_name: str,
        *,
        module_name: str | None = None,
        import_error: str | None = None,
    ):
        self.driver_name = driver_name
        self.extra_name = extra_name
        self.package_name = package_name
        self.module_name = module_name
        self.import_error = import_error
        super().__init__(f"Missing driver for {driver_name}")
