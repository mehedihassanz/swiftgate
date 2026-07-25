"""Application configuration — reads from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


@dataclass
class Settings:
    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:///./swiftgate.db"
    )

    # Redis (for real-time spend tracking + budget enforcement)
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Core
    ENV: str = os.environ.get("ENV", "development")
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8000"))

    # Provider API keys (BYOK from gateway operator)
    # These are the keys SwiftGate uses to call upstream providers.
    # Users can also bring their own keys (BYOK mode).
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    DEEPINFRA_API_KEY: str = os.environ.get("DEEPINFRA_API_KEY", "")
    TOGETHER_API_KEY: str = os.environ.get("TOGETHER_API_KEY", "")
    GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
    MISTRAL_API_KEY: str = os.environ.get("MISTRAL_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")

    # Gateway margin (our markup on tokens — e.g. 0.01 = 1%)
    TOKEN_MARGIN: float = float(os.environ.get("TOKEN_MARGIN", "0.01"))

    # Default routing strategy
    DEFAULT_ROUTING: str = os.environ.get("DEFAULT_ROUTING", "balanced")
    # Options: "cheapest", "fastest", "balanced", "quality"

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.DATABASE_URL


settings = Settings()
