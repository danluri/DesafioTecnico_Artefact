"""Runtime configuration that keeps local and Docker database paths explicit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path("data/emporio.db")
DEVELOPMENT_PRINCIPAL_HMAC_SECRET = "development-only-change-me"
MINIMUM_PRINCIPAL_HMAC_SECRET_LENGTH = 32


@dataclass(frozen=True, slots=True)
class OptionalIntegrationConfig:
    market_enabled: bool = False
    mcp_enabled: bool = False

    @classmethod
    def from_env(cls) -> "OptionalIntegrationConfig":
        def flag(name: str) -> bool:
            return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}
        return cls(flag("EMPORIO_MARKET_ENABLED"), flag("EMPORIO_MCP_ENABLED"))


class IntegrationFactory:
    """Explicit seam for optional adapters; credentials are never required by P0."""

    @staticmethod
    def config() -> OptionalIntegrationConfig:
        return OptionalIntegrationConfig.from_env()


def database_path(explicit: str | Path | None = None) -> Path:
    """Resolve only the configured SQLite path; no directories are created here."""
    return Path(explicit or os.getenv("EMPORIO_DB_PATH") or DEFAULT_DB_PATH)


def principal_binding_secret(explicit: str | None = None) -> bytes:
    """Return the HMAC secret, rejecting unsafe configuration in production."""
    value = explicit if explicit is not None else os.getenv("EMPORIO_PRINCIPAL_HMAC_SECRET")
    environment = os.getenv("EMPORIO_ENV", "development").strip().lower()
    if value is None:
        if environment == "production":
            raise ValueError("EMPORIO_PRINCIPAL_HMAC_SECRET is required in production")
        value = DEVELOPMENT_PRINCIPAL_HMAC_SECRET
    if not value:
        raise ValueError("EMPORIO_PRINCIPAL_HMAC_SECRET must not be empty")
    if environment == "production" and len(value) < MINIMUM_PRINCIPAL_HMAC_SECRET_LENGTH:
        raise ValueError(
            "EMPORIO_PRINCIPAL_HMAC_SECRET must contain at least "
            f"{MINIMUM_PRINCIPAL_HMAC_SECRET_LENGTH} characters in production"
        )
    return value.encode("utf-8")

