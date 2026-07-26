"""Application configuration — reads from environment variables.

Optionally loads .env file if present (via python-dotenv).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Load .env file if present (silent no-op if file doesn't exist)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


@dataclass
class Settings:
    # Database — Railway injects DATABASE_URL when Postgres plugin is attached.
    # Without it, fall back to SQLite (ephemeral on Railway — data lost on redeploy).
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:///./swiftgate.db"
    )

    # Redis — Railway injects REDIS_URL when Redis plugin is attached.
    # Without it, rate limiter falls back to in-memory.
    REDIS_URL: str = os.environ.get("REDIS_URL", "")

    # Core — Railway injects PORT. Default to 8000 for local dev.
    ENV: str = os.environ.get("ENV", "development")
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8000"))

    # Admin auth (required in production)
    ADMIN_KEY: str = os.environ.get("ADMIN_KEY", "")

    # CORS — comma-separated allowlist. Use "*" for development only.
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

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

    # Semantic cache
    CACHE_ENABLED: bool = _get_bool("CACHE_ENABLED", True)
    CACHE_SEMANTIC_MATCH: bool = _get_bool("CACHE_SEMANTIC_MATCH", True)  # Jaccard similarity
    CACHE_SHARED_DEFAULT: bool = _get_bool("CACHE_SHARED_DEFAULT", False)  # cross-user caching
    CACHE_TTL_HOURS: int = int(os.environ.get("CACHE_TTL_HOURS", "24"))

    # PII redaction
    PII_REDACTION_ENABLED: bool = _get_bool("PII_REDACTION_ENABLED", False)
    PII_REHYDRATE_RESPONSE: bool = _get_bool("PII_REHYDRATE_RESPONSE", True)  # restore PII in response

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.DATABASE_URL


settings = Settings()
