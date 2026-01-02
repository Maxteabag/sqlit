"""Docker detection helpers for providers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class DockerCredentials:
    user: str | None
    password: str | None
    database: str | None


@dataclass(frozen=True)
class DockerDetector:
    image_patterns: tuple[str, ...]
    env_vars: dict[str, tuple[str, ...]]
    default_user: str | None = None
    default_database: str | None = None
    preferred_host: str = "localhost"
    default_user_requires_password: bool = False
    post_process: Callable[[DockerCredentials, Mapping[str, str]], DockerCredentials] | None = None

    def match_image(self, image_name: str) -> bool:
        image_lower = image_name.lower()
        return any(pattern in image_lower for pattern in self.image_patterns)

    def get_credentials(self, env_vars: dict[str, str]) -> DockerCredentials:
        def get_first(values: tuple[str, ...]) -> str | None:
            for key in values:
                if key in env_vars:
                    return env_vars[key]
            return None

        user = get_first(self.env_vars.get("user", ()))
        password = get_first(self.env_vars.get("password", ()))
        database = get_first(self.env_vars.get("database", ())) or self.default_database
        if not user and self.default_user is not None and (not self.default_user_requires_password or password):
            user = self.default_user
        if not database:
            database = self.default_database
        creds = DockerCredentials(user=user, password=password, database=database)
        if self.post_process:
            return self.post_process(creds, env_vars)
        return creds
