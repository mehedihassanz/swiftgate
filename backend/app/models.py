"""SQLAlchemy models for SwiftGate.

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


class User(Base):
    """A registered platform user — signs up, manages their own keys, sees their usage."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Credits in USD cents (avoids float precision issues)
    credits_cents: Mapped[int] = mapped_column(Integer, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # API keys belonging to this user
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="user")


class ApiKey(Base):
    """A user API key with optional spend limits."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(20))  # "sg-...abc" for display
    name: Mapped[str] = mapped_column(String(200), default="default")
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Link to registered user (nullable for admin-created legacy keys)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    user: Mapped["User | None"] = relationship("User", back_populates="api_keys")

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


class Agent(Base):
    """An AI agent tracked by SwiftGate for budget orchestration.

    Agents are identified by agent_id (from API requests). Each agent has
    its own budget, status, and spend tracking — independent of API keys.

    This enables multi-agent workflows where each agent gets a capped budget,
    with automatic kill-switches when limits are exceeded.
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="unnamed-agent")

    # Budget (in cents to avoid float issues)
    budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spend_cents: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)

    # Status — "active" allows requests, "paused" blocks new requests
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Options: "active", "paused", "killed", "budget_exceeded"

    # Kill-switch metadata
    killed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    killed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Budget reset cycle
    budget_reset_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Alert thresholds (percentages at which alerts fire)
    alert_thresholds: Mapped[str] = mapped_column(String(100), default="50,80,100")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    last_active: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Associated API key (optional — agents can be shared across keys)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True, index=True)


class AgentEvent(Base):
    """An event in an agent's execution trace.

    Records the flow of a multi-agent workflow: each LLM call, tool use,
    and handoff between agents. This builds the observability layer.
    """

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(200), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    # "llm_call", "tool_call", "tool_result", "handoff", "error", "budget_alert"

    # What was this event?
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    usage_record_id: Mapped[int | None] = mapped_column(ForeignKey("usage_records.id"), nullable=True)

    # Cost of this event (cents)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Trace info for multi-agent workflows
    parent_agent_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    # Event metadata
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob

    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)


class QualityScore(Base):
    """Empirically measured quality score per (model, task_type).

    Three tiers of quality signals:
      - implicit: user retries, continues conversation, abandons
      - explicit: thumbs up/down, regenerate requests
      - automated: LLM-as-judge evaluator scores (sampled 1% of requests)

    The rolling weighted average feeds the quality-aware router.
    This is the second data flywheel: more requests → better quality data →
    better routing → better outputs → more requests.
    """

    __tablename__ = "quality_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(200), index=True)
    task_type: Mapped[str] = mapped_column(String(50), index=True)

    # Score 0-10
    score: Mapped[float] = mapped_column(Numeric(3, 2))

    # Signal source: "implicit", "explicit", "automated"
    signal_source: Mapped[str] = mapped_column(String(20), default="implicit")

    # Link to the usage record that generated this score
    usage_record_id: Mapped[int | None] = mapped_column(ForeignKey("usage_records.id"), nullable=True)

    # What signal triggered this? e.g. "user_retry", "thumbs_up", "thumbs_down",
    # "conversation_continued", "llm_judge", "regenerate"
    signal_type: Mapped[str] = mapped_column(String(50))

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)


class RoutingRule(Base):
    """Configurable routing rules — maps request patterns to model choices.

    Enables natural-language-like routing without the NL parsing:
    "use cheapest for coding tasks" or "use Claude for production code"
    """

    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    # Condition: what triggers this rule
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_cost_per_request_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_quality_score: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)

    # Action: what to do when this rule matches
    strategy: Mapped[str] = mapped_column(String(50), default="balanced")
    # "cheapest", "fastest", "balanced", "quality", "specific_model"
    target_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower = checked first

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class CacheEntry(Base):
    """Semantic cache entry for LLM responses.

    Stores responses keyed by a normalized hash of the prompt. When a
    semantically similar request arrives, the cached response is served
    without calling the upstream provider — zero cost, instant response.

    Two matching modes:
      - exact: SHA-256 hash of normalized messages (zero false positives)
      - semantic: token-level Jaccard similarity above threshold (or embedding cosine)

    Privacy: entries are per-api_key by default (no cross-user leakage).
    Shared mode can be enabled per-key for collaborative caching.
    """

    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Normalized content hash (SHA-256 of normalized message content)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    # What was cached
    model_id: Mapped[str] = mapped_column(String(200), index=True)
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # The original request (for similarity comparison)
    messages_json: Mapped[str] = mapped_column(Text)

    # The cached response
    response_json: Mapped[str] = mapped_column(Text)

    # Token set for Jaccard similarity (pipe-delimited sorted unique tokens)
    token_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cost that was saved by this cache hit (cents)
    saved_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    saved_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # How many times this entry has been served from cache
    hit_count: Mapped[int] = mapped_column(Integer, default=0)

    # Privacy scoping
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True, index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)

    # TTL
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

