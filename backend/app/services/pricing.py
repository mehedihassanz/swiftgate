"""Model pricing registry — seeds the database with real provider pricing.

All prices are per-token in USD. To convert to per-1M-tokens, multiply by 1,000,000.

Sources:
  - OpenRouter /api/v1/models (live, July 2026)
  - DeepInfra, Together, Anthropic, OpenAI pricing pages

This is SwiftGate's core data asset — the more accurate and comprehensive
this registry is, the better our cost predictions.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Model, Provider

logger = logging.getLogger(__name__)


# ─── Provider definitions ──────────────────────────────────────────────

PROVIDERS = [
    {
        "name": "openai",
        "display_name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "priority": 10,
    },
    {
        "name": "anthropic",
        "display_name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "priority": 10,
    },
    {
        "name": "deepinfra",
        "display_name": "DeepInfra",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "api_key_env": "DEEPINFRA_API_KEY",
        "priority": 20,
    },
    {
        "name": "together",
        "display_name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": "TOGETHER_API_KEY",
        "priority": 20,
    },
    {
        "name": "google",
        "display_name": "Google AI",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key_env": "GOOGLE_API_KEY",
        "priority": 15,
    },
    {
        "name": "mistral",
        "display_name": "Mistral AI",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "priority": 20,
    },
    {
        "name": "deepseek",
        "display_name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "priority": 15,
    },
    {
        "name": "xai",
        "display_name": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1",
        "api_key_env": "XAI_API_KEY",
        "priority": 15,
    },
    {
        "name": "cohere",
        "display_name": "Cohere",
        "base_url": "https://api.cohere.com/v1",
        "api_key_env": "COHERE_API_KEY",
        "priority": 20,
    },
    {
        "name": "perplexity",
        "display_name": "Perplexity AI",
        "base_url": "https://api.perplexity.ai/v1",
        "api_key_env": "PERPLEXITY_API_KEY",
        "priority": 20,
    },
    {
        "name": "moonshot",
        "display_name": "Moonshot AI (Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "priority": 20,
    },
    {
        "name": "zhipu",
        "display_name": "Zhipu (GLM)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPU_API_KEY",
        "priority": 20,
    },
    {
        "name": "novita",
        "display_name": "Novita AI",
        "base_url": "https://api.novita.ai/v3/openai",
        "api_key_env": "NOVITA_API_KEY",
        "priority": 25,
    },
    {
        "name": "fireworks",
        "display_name": "Fireworks AI",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "api_key_env": "FIREWORKS_API_KEY",
        "priority": 20,
    },
    {
        "name": "groq",
        "display_name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "priority": 15,
    },
    {
        "name": "minimax",
        "display_name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "priority": 25,
    },
    {
        "name": "tencent",
        "display_name": "Tencent Hunyuan",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "api_key_env": "TENCENT_API_KEY",
        "priority": 25,
    },
    {
        "name": "bytedance",
        "display_name": "ByteDance Doubao",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key_env": "BYTEDANCE_API_KEY",
        "priority": 25,
    },
]


# ─── Model pricing data (per-token USD) ────────────────────────────────
# prompt_price / completion_price / cached_price are per SINGLE token.
# E.g. $10/1M tokens → 0.00001 per token

MODELS = [
    # ── Anthropic (Claude) ──────────────────────────────────────────────
    {
        "model_id": "claude-opus-5",
        "display_name": "Claude Opus 5",
        "provider": "anthropic",
        "tokenizer": "anthropic",
        "prompt_price": "0.000005",      # $5/1M
        "completion_price": "0.000025",   # $25/1M
        "cached_price": "0.00000125",     # $1.25/1M (75% off)
        "context_window": 200000,
        "max_output": 32000,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 9.5, "speed_score": 35, "category": "frontier",
    },
    {
        "model_id": "claude-opus-5-fast",
        "display_name": "Claude Opus 5 Fast",
        "provider": "anthropic",
        "tokenizer": "anthropic",
        "prompt_price": "0.00001",        # $10/1M
        "completion_price": "0.00005",     # $50/1M
        "cached_price": "0.0000025",
        "context_window": 200000, "max_output": 16000,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 9.3, "speed_score": 55, "category": "frontier",
    },
    {
        "model_id": "claude-sonnet-4-5",
        "display_name": "Claude Sonnet 4.5",
        "provider": "anthropic",
        "tokenizer": "anthropic",
        "prompt_price": "0.000003",       # $3/1M
        "completion_price": "0.000015",    # $15/1M
        "cached_price": "0.0000003",
        "context_window": 200000, "max_output": 16000,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 8.8, "speed_score": 65, "category": "frontier",
    },
    {
        "model_id": "claude-haiku-4",
        "display_name": "Claude Haiku 4",
        "provider": "anthropic",
        "tokenizer": "anthropic",
        "prompt_price": "0.0000008",      # $0.80/1M
        "completion_price": "0.000004",    # $4/1M
        "cached_price": "0.00000008",
        "context_window": 200000, "max_output": 8192,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 8.0, "speed_score": 90, "category": "fast",
    },

    # ── OpenAI ──────────────────────────────────────────────────────────
    {
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "provider": "openai",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000025",      # $2.50/1M
        "completion_price": "0.00001",     # $10/1M
        "cached_price": "0.00000125",
        "context_window": 128000, "max_output": 16384,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 8.7, "speed_score": 60, "category": "frontier",
    },
    {
        "model_id": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "provider": "openai",
        "tokenizer": "tiktoken",
        "prompt_price": "0.00000015",     # $0.15/1M
        "completion_price": "0.0000006",   # $0.60/1M
        "cached_price": "0.000000075",
        "context_window": 128000, "max_output": 16384,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 7.5, "speed_score": 95, "category": "fast",
    },
    {
        "model_id": "o1",
        "display_name": "OpenAI o1",
        "provider": "openai",
        "tokenizer": "tiktoken",
        "prompt_price": "0.000015",       # $15/1M
        "completion_price": "0.00006",     # $60/1M
        "cached_price": "0.0000075",
        "context_window": 200000, "max_output": 100000,
        "supports_tools": False, "supports_vision": True, "supports_json": False,
        "quality_score": 9.2, "speed_score": 15, "category": "reasoning",
    },

    # ── DeepSeek (via DeepInfra — cheapest) ─────────────────────────────
    {
        "model_id": "deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash",
        "provider": "deepinfra",
        "tokenizer": "llama",
        "prompt_price": "0.00000009",     # $0.09/1M — cheapest serious model
        "completion_price": "0.00000018",  # $0.18/1M
        "cached_price": "0.000000018",     # $0.018/1M (7% of base)
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 7.8, "speed_score": 85, "category": "cheap",
    },
    {
        "model_id": "deepseek-v4-pro",
        "display_name": "DeepSeek V4 Pro",
        "provider": "deepinfra",
        "tokenizer": "llama",
        "prompt_price": "0.0000013",      # $1.30/1M
        "completion_price": "0.0000026",   # $2.60/1M
        "cached_price": "0.0000001",
        "context_window": 128000, "max_output": 16384,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.5, "speed_score": 55, "category": "reasoning",
    },
    {
        "model_id": "deepseek-v3-turbo",
        "display_name": "DeepSeek V3 Turbo",
        "provider": "deepinfra",
        "tokenizer": "llama",
        "prompt_price": "0.0000004",      # $0.40/1M
        "completion_price": "0.0000013",   # $1.30/1M
        "cached_price": "0.00000005",
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.0, "speed_score": 75, "category": "cheap",
    },

    # ── Meta Llama (via Together) ───────────────────────────────────────
    {
        "model_id": "llama-4-70b",
        "display_name": "Llama 4 70B",
        "provider": "together",
        "tokenizer": "llama",
        "prompt_price": "0.00000088",     # $0.88/1M
        "completion_price": "0.00000088",
        "cached_price": "0.000000088",
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 8.0, "speed_score": 70, "category": "cheap",
    },

    # ── GLM / Zhipu ─────────────────────────────────────────────────────
    {
        "model_id": "glm-5-2",
        "display_name": "GLM-5.2 (Zhipu)",
        "provider": "zhipu",
        "tokenizer": "qwen",
        "prompt_price": "0.0000014",      # $1.40/1M
        "completion_price": "0.0000044",   # $4.40/1M
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 8.4, "speed_score": 60, "category": "frontier",
    },

    # ── Google ──────────────────────────────────────────────────────────
    {
        "model_id": "gemini-2-5-pro",
        "display_name": "Gemini 2.5 Pro",
        "provider": "google",
        "tokenizer": "tiktoken",  # approximate
        "prompt_price": "0.00000125",     # $1.25/1M
        "completion_price": "0.000005",    # $5/1M
        "cached_price": "0.0000003125",
        "context_window": 1000000, "max_output": 8192,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 8.9, "speed_score": 55, "category": "frontier",
    },

    # ── Mistral ─────────────────────────────────────────────────────────
    {
        "model_id": "mistral-large-2",
        "display_name": "Mistral Large 2",
        "provider": "mistral",
        "tokenizer": "tiktoken",  # approximate
        "prompt_price": "0.000002",       # $2/1M
        "completion_price": "0.000006",    # $6/1M
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.2, "speed_score": 65, "category": "frontier",
    },

    # ── Mistral variants ────────────────────────────────────────────────
    {
        "model_id": "mistral-small",
        "display_name": "Mistral Small",
        "provider": "mistral",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000002",      # $0.20/1M
        "completion_price": "0.0000006",   # $0.60/1M
        "cached_price": None,
        "context_window": 32000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 7.5, "speed_score": 95, "category": "cheap",
    },
    {
        "model_id": "codestral",
        "display_name": "Codestral",
        "provider": "mistral",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000003",
        "completion_price": "0.0000009",
        "cached_price": None,
        "context_window": 256000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.0, "speed_score": 90, "category": "coding",
    },
    {
        "model_id": "mistral-nemo",
        "display_name": "Mistral NeMo",
        "provider": "mistral",
        "tokenizer": "tiktoken",
        "prompt_price": "0.00000015",
        "completion_price": "0.00000015",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": False, "supports_vision": False, "supports_json": False,
        "quality_score": 7.0, "speed_score": 95, "category": "cheap",
    },

    # ── xAI (Grok) ──────────────────────────────────────────────────────
    {
        "model_id": "grok-4",
        "display_name": "Grok 4",
        "provider": "xai",
        "tokenizer": "tiktoken",
        "prompt_price": "0.000005",        # $5/1M
        "completion_price": "0.000015",     # $15/1M
        "cached_price": None,
        "context_window": 256000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.7, "speed_score": 55, "category": "frontier",
    },
    {
        "model_id": "grok-4-fast",
        "display_name": "Grok 4 Fast",
        "provider": "xai",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000002",
        "completion_price": "0.0000011",
        "cached_price": None,
        "context_window": 100000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.2, "speed_score": 85, "category": "fast",
    },
    {
        "model_id": "grok-3-mini",
        "display_name": "Grok 3 Mini",
        "provider": "xai",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000003",
        "completion_price": "0.0000005",
        "cached_price": None,
        "context_window": 100000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 7.3, "speed_score": 90, "category": "cheap",
    },

    # ── Cohere ──────────────────────────────────────────────────────────
    {
        "model_id": "command-r-plus",
        "display_name": "Command R+",
        "provider": "cohere",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000025",
        "completion_price": "0.00001",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.3, "speed_score": 60, "category": "frontier",
    },
    {
        "model_id": "command-r",
        "display_name": "Command R",
        "provider": "cohere",
        "tokenizer": "tiktoken",
        "prompt_price": "0.00000015",
        "completion_price": "0.0000006",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 7.8, "speed_score": 85, "category": "cheap",
    },
    {
        "model_id": "command-r7b",
        "display_name": "Command R7B",
        "provider": "cohere",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000000375",
        "completion_price": "0.00000015",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 6.8, "speed_score": 98, "category": "cheap",
    },

    # ── Perplexity ──────────────────────────────────────────────────────
    {
        "model_id": "llama-3.1-sonar-huge",
        "display_name": "Sonar Huge (online)",
        "provider": "perplexity",
        "tokenizer": "llama",
        "prompt_price": "0.000005",
        "completion_price": "0.00001",
        "cached_price": None,
        "context_window": 127000, "max_output": 8192,
        "supports_tools": False, "supports_vision": False, "supports_json": False,
        "quality_score": 8.5, "speed_score": 50, "category": "frontier",
    },
    {
        "model_id": "llama-3.1-sonar-large",
        "display_name": "Sonar Large (online)",
        "provider": "perplexity",
        "tokenizer": "llama",
        "prompt_price": "0.0000009",
        "completion_price": "0.0000009",
        "cached_price": None,
        "context_window": 127000, "max_output": 8192,
        "supports_tools": False, "supports_vision": False, "supports_json": False,
        "quality_score": 8.0, "speed_score": 70, "category": "frontier",
    },

    # ── Moonshot (Kimi) ─────────────────────────────────────────────────
    {
        "model_id": "moonshot-v1-128k",
        "display_name": "Kimi K2 128K",
        "provider": "moonshot",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000014",
        "completion_price": "0.0000028",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.2, "speed_score": 60, "category": "frontier",
    },
    {
        "model_id": "moonshot-v1-32k",
        "display_name": "Kimi K2 32K",
        "provider": "moonshot",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000007",
        "completion_price": "0.0000008",
        "cached_price": None,
        "context_window": 32000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 7.8, "speed_score": 80, "category": "cheap",
    },

    # ── MiniMax ─────────────────────────────────────────────────────────
    {
        "model_id": "minimax-m3",
        "display_name": "MiniMax M3",
        "provider": "minimax",
        "tokenizer": "tiktoken",
        "prompt_price": "0.0000007",
        "completion_price": "0.0000028",
        "cached_price": None,
        "context_window": 1_000_000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.1, "speed_score": 55, "category": "frontier",
    },

    # ── Tencent Hunyuan ─────────────────────────────────────────────────
    {
        "model_id": "hunyuan-pro",
        "display_name": "Hunyuan Pro",
        "provider": "tencent",
        "tokenizer": "tiktoken",
        "prompt_price": "0.000004",
        "completion_price": "0.000012",
        "cached_price": None,
        "context_window": 28000, "max_output": 4096,
        "supports_tools": False, "supports_vision": False, "supports_json": True,
        "quality_score": 7.8, "speed_score": 65, "category": "frontier",
    },

    # ── ByteDance Doubao ────────────────────────────────────────────────
    {
        "model_id": "doubao-pro-128k",
        "display_name": "Doubao Pro 128K",
        "provider": "bytedance",
        "tokenizer": "tiktoken",
        "prompt_price": "0.00000011",
        "completion_price": "0.00000028",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": False, "supports_vision": False, "supports_json": True,
        "quality_score": 7.5, "speed_score": 85, "category": "cheap",
    },

    # ── Groq (ultra-fast inference) ─────────────────────────────────────
    {
        "model_id": "llama-3.3-70b-versatile",
        "display_name": "Llama 3.3 70B (Groq)",
        "provider": "groq",
        "tokenizer": "llama",
        "prompt_price": "0.00000059",
        "completion_price": "0.00000079",
        "cached_price": None,
        "context_window": 128000, "max_output": 32768,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 8.0, "speed_score": 100, "category": "fast",
    },
    {
        "model_id": "llama-3.1-8b-instant",
        "display_name": "Llama 3.1 8B Instant (Groq)",
        "provider": "groq",
        "tokenizer": "llama",
        "prompt_price": "0.00000005",
        "completion_price": "0.00000008",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 6.8, "speed_score": 100, "category": "fast",
    },

    # ── Novita AI ───────────────────────────────────────────────────────
    {
        "model_id": "gpt-oss-120b",
        "display_name": "GPT-OSS 120B",
        "provider": "novita",
        "tokenizer": "tiktoken",
        "prompt_price": "0.00000005",      # $0.05/1M — ultra cheap
        "completion_price": "0.00000025",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": False, "supports_json": True,
        "quality_score": 7.5, "speed_score": 80, "category": "cheap",
    },

    # ── Fireworks AI ────────────────────────────────────────────────────
    {
        "model_id": "firework-llama4-scout",
        "display_name": "Llama 4 Scout (Fireworks)",
        "provider": "fireworks",
        "tokenizer": "llama",
        "prompt_price": "0.00000011",
        "completion_price": "0.0000003",
        "cached_price": None,
        "context_window": 128000, "max_output": 8192,
        "supports_tools": True, "supports_vision": True, "supports_json": True,
        "quality_score": 7.8, "speed_score": 90, "category": "cheap",
    },
]


async def seed_database(db: AsyncSession, overwrite_prices: bool = False) -> dict[str, Any]:
    """Seed providers and models. Idempotent — safe to call on every startup.

    By default, does NOT overwrite existing model prices (respects admin overrides).
    Set overwrite_prices=True to force-update pricing (used by POST /admin/seed).
    """
    providers_seeded = 0
    providers_skipped = 0
    models_seeded = 0
    models_updated = 0

    # ── Seed providers ──────────────────────────────────────────────────
    provider_map: dict[str, Provider] = {}

    existing_providers = await db.execute(select(Provider))
    for p in existing_providers.scalars().all():
        provider_map[p.name] = p

    for pdata in PROVIDERS:
        name = pdata["name"]
        if name in provider_map:
            # Update existing
            p = provider_map[name]
            p.display_name = pdata["display_name"]
            p.base_url = pdata["base_url"]
            p.api_key_env = pdata["api_key_env"]
            p.priority = pdata["priority"]
            providers_skipped += 1
        else:
            p = Provider(**pdata)
            db.add(p)
            providers_seeded += 1

    await db.flush()

    # Build name→id map
    provider_id_map: dict[str, int] = {}
    all_providers = await db.execute(select(Provider))
    for p in all_providers.scalars().all():
        provider_id_map[p.name] = p.id

    # ── Seed models ─────────────────────────────────────────────────────
    existing_models = await db.execute(select(Model))
    model_map: dict[str, Model] = {m.model_id: m for m in existing_models.scalars().all()}

    for mdata_orig in MODELS:
        mdata = dict(mdata_orig)  # copy so we don't mutate the original
        provider_name = mdata.pop("provider")
        model_id = mdata["model_id"]

        if model_id in model_map:
            # Update pricing only if overwrite_prices is True (startup doesn't overwrite admin overrides)
            if overwrite_prices:
                m = model_map[model_id]
                m.prompt_price = Decimal(mdata["prompt_price"])
                m.completion_price = Decimal(mdata["completion_price"])
                m.cached_price = Decimal(mdata["cached_price"]) if mdata.get("cached_price") else None
                m.context_window = mdata["context_window"]
                m.max_output = mdata["max_output"]
                m.supports_tools = mdata["supports_tools"]
                m.supports_vision = mdata["supports_vision"]
                m.supports_json = mdata["supports_json"]
                m.quality_score = mdata["quality_score"]
                m.speed_score = mdata["speed_score"]
                m.category = mdata["category"]
                models_updated += 1
        else:
            prompt_price = Decimal(mdata.pop("prompt_price"))
            completion_price = Decimal(mdata.pop("completion_price"))
            cached_price_raw = mdata.pop("cached_price", None)
            cached_price = Decimal(cached_price_raw) if cached_price_raw else None
            m = Model(
                provider_id=provider_id_map[provider_name],
                prompt_price=prompt_price,
                completion_price=completion_price,
                cached_price=cached_price,
                **mdata,
            )
            db.add(m)
            models_seeded += 1

    await db.flush()

    logger.info(
        f"Database seeded: {providers_seeded} new providers, {providers_skipped} existing, "
        f"{models_seeded} new models, {models_updated} updated"
    )
    return {
        "providers_seeded": providers_seeded,
        "providers_updated": providers_skipped,
        "models_seeded": models_seeded,
        "models_updated": models_updated,
        "total_models": len(MODELS),
    }


# ─── Quality seed data ─────────────────────────────────────────────────
# Initial quality signals to populate the leaderboard so it's not empty.
# These represent baseline community consensus — real empirical data
# from actual users will override these over time via the data flywheel.

QUALITY_SEEDS = [
    # (model_id, task_type, score, signal_type)
    # ── Code generation ──
    ("claude-opus-5", "code", 9.6, "seed_expert"),
    ("claude-sonnet-4-5", "code", 9.2, "seed_expert"),
    ("gpt-4o", "code", 8.9, "seed_expert"),
    ("o1", "code", 9.4, "seed_expert"),
    ("deepseek-v4-pro", "code", 8.7, "seed_expert"),
    ("codestral", "code", 8.5, "seed_expert"),
    ("glm-5-2", "code", 8.3, "seed_expert"),

    # ── Chat / general ──
    ("claude-opus-5", "chat", 9.5, "seed_expert"),
    ("gpt-4o", "chat", 8.8, "seed_expert"),
    ("claude-sonnet-4-5", "chat", 8.7, "seed_expert"),
    ("gemini-2-5-pro", "chat", 8.6, "seed_expert"),
    ("grok-4", "chat", 8.5, "seed_expert"),
    ("mistral-large-2", "chat", 8.0, "seed_expert"),

    # ── Reasoning ──
    ("o1", "reasoning", 9.7, "seed_expert"),
    ("claude-opus-5", "reasoning", 9.4, "seed_expert"),
    ("deepseek-v4-pro", "reasoning", 8.8, "seed_expert"),
    ("gemini-2-5-pro", "reasoning", 8.5, "seed_expert"),

    # ── Fast / cheap tier ──
    ("claude-haiku-4", "chat", 8.2, "seed_expert"),
    ("gpt-4o-mini", "chat", 7.6, "seed_expert"),
    ("deepseek-v4-flash", "code", 7.9, "seed_expert"),
    ("grok-4-fast", "chat", 8.0, "seed_expert"),
    ("command-r", "chat", 7.8, "seed_expert"),
]


async def seed_quality_scores(db: AsyncSession) -> int:
    """Seed initial quality scores so the leaderboard isn't empty.

    These are expert baseline estimates. Real user feedback (explicit +
    implicit + automated LLM-judge) will accumulate and override these
    via the weighted quality index.
    """
    from app.models import QualityScore

    # Check if already seeded
    existing = await db.execute(
        select(QualityScore).where(QualityScore.signal_type == "seed_expert").limit(1)
    )
    if existing.scalar_one_or_none():
        return 0  # Already seeded

    count = 0
    for model_id, task_type, score, signal_type in QUALITY_SEEDS:
        qs = QualityScore(
            model_id=model_id,
            task_type=task_type,
            score=score,
            signal_source="automated",  # seeds are "automated" tier (highest weight)
            signal_type=signal_type,
        )
        db.add(qs)
        count += 1

    await db.flush()
    logger.info(f"Seeded {count} quality scores")
    return count
