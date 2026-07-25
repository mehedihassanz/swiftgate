"""SQLAlchemy models for NeuralWatt.

Core entities:
  - Model         : a model in our catalog (pricing, capabilities, tokenizer type)
  - ApiKey        : a user API key with spend limits
  - UsageRecord   : per-request token + cost record (the analytics goldmine)
  - Provider      : upstream inference provider config
  - BudgetAlert   : triggered when spend crosses thresholds
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Provider(Base):
    """An upstream inference provider (OpenAI, Anthropic, DeepInfra, etc.)."""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # "openai", "anthropic"
    display_name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(2048))
    api_key_env: Mapped[str] = mapped_column(String(200))  # env var name for the key
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower = preferred
    avg_latency_ms: Mapped[int] = mapped_column(Integer, default=0)  # rolling avg
    uptime_pct: Mapped[float] = mapped_column(default=99.9)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Model(Base):
    """A model in our catalog with pricing and capability metadata."""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The model ID users specify in API calls (e.g. "claude-opus-5", "deepseek-v4-flash")
    model_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)

    # Tokenizer to use for this model
    tokenizer: Mapped[str] = mapped_column(String(50), default="tiktoken")
    # Options: "tiktoken", "anthropic", "llama", "qwen", "char4"

    # Pricing per token (in USD, stored as Decimal for precision)
    prompt_price: Mapped[Decimal] = mapped_column(Numeric(12, 8))     # $/token input
    completion_price: Mapped[Decimal] = mapped_column(Numeric(12, 8))  # $/token output
    cached_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)

    # Capabilities
    context_window: Mapped[int] = mapped_column(Integer, default=4096)
    max_output: Mapped[int] = mapped_column(Integer, default=4096)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_json: Mapped[bool] = mapped_column(Boolean, default=False)

    # Quality score (0-10, updated from A/B testing + user feedback)
    quality_score: Mapped[float] = mapped_column(default=7.0)
    # Speed score (tokens/sec baseline)
    speed_score: Mapped[float] = mapped_column(default=50.0)

    # Routing metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str] = mapped_column(String(50), default="general")
    # "frontier", "fast", "cheap", "reasoning", "vision", "coding"

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    provider: Mapped["Provider"] = relationship()


class ApiKey(Base):
    """A user API key with optional spend limits."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(20))  # "nw-...abc" for display
    name: Mapped[str] = mapped_column(String(200), default="default")
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Spend limits (in USD cents to avoid float issues)
    monthly_budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_request_limit_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Per-agent budget (for agent-native workflows)
    agent_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Total spend tracking (refreshed from usage_records)
    total_spend_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)


class UsageRecord(Base):
    """Per-request token usage + cost record. The analytics goldmine."""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), index=True, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    # What was requested
    model_requested: Mapped[str] = mapped_column(String(200))
    model_served: Mapped[str] = mapped_column(String(200))  # may differ if routed

    # Token counts
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Cost breakdown (in cents)
    prompt_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    completion_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Performance
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # time to first token
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    was_predicted: Mapped[bool] = mapped_column(Boolean, default=False)
    prediction_error_pct: Mapped[float | None] = mapped_column(nullable=True)
    routing_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    was_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success, error, timeout

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)

    # Request metadata (for analytics)
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # "chat", "code", "reasoning", "vision", "tool_use", "embedding"


class BudgetAlert(Base):
    """Triggered when spend crosses a threshold."""

    __tablename__ = "budget_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    threshold_pct: Mapped[int] = mapped_column(Integer)  # 50, 80, 90, 100
    spend_cents: Mapped[int] = mapped_column(Integer)
    budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
