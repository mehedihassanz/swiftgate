"""Tokenizer engine — exact token counting for cost prediction.

Automatically routes to the right tokenizer based on model family.
Uses tiktoken for OpenAI, anthropic tokenizer for Claude, and
HuggingFace tokenizers for Llama/Qwen/GLM.

For models without a dedicated tokenizer, falls back to char-based heuristic.

Public API:
    count_tokens(messages, model_id) -> int
    get_tokenizer(model_id) -> Tokenizer
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.services.pricing import MODELS

logger = logging.getLogger(__name__)

# Build model_id → tokenizer type map
_TOKENIZER_MAP: dict[str, str] = {}
for m in MODELS:
    _TOKENIZER_MAP[m["model_id"]] = m.get("tokenizer", "tiktoken")


class CharTokenizer:
    """Fallback tokenizer — ~4 chars per token heuristic."""

    def encode(self, text: str) -> list[int]:
        # Return a fake list of "token" ids (just for length counting)
        return list(range(max(1, len(text) // 4)))

    def encode_batch(self, texts: list[str]) -> list[list[int]]:
        return [self.encode(t) for t in texts]


def _extract_text(messages: list[dict[str, Any]]) -> str:
    """Extract all text content from chat messages."""
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg.get("content"), str):
            parts.append(msg["content"])
        elif isinstance(msg.get("content"), list):
            # Multi-modal content (text + images)
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
        # Tool calls / function calls have structured content
        if msg.get("role") == "tool" and msg.get("content"):
            parts.append(str(msg["content"]))
    return " ".join(parts)


@lru_cache(maxsize=1)
def _get_tiktoken_encoder():
    """Get the tiktoken encoder for OpenAI models (o200k for GPT-4o+)."""
    try:
        import tiktoken
        return tiktoken.encoding_for_model("gpt-4o")
    except ImportError:
        logger.warning("tiktoken not installed, falling back to char tokenizer")
        return CharTokenizer()
    except Exception as e:
        logger.warning(f"tiktoken init failed: {e}, falling back to char tokenizer")
        return CharTokenizer()


@lru_cache(maxsize=1)
def _get_anthropic_encoder():
    """Get the Anthropic tokenizer."""
    try:
        import anthropic
        # The anthropic SDK has a tokenizer
        client = anthropic.Anthropic(api_key="dummy")  # doesn't need a real key for counting
        return client
    except ImportError:
        logger.warning("anthropic SDK not installed, using tiktoken approximation")
        return _get_tiktoken_encoder()
    except Exception:
        return _get_tiktoken_encoder()


@lru_cache(maxsize=8)
def _get_hf_tokenizer(model_family: str):
    """Load a HuggingFace tokenizer for open-source models."""
    try:
        from transformers import AutoTokenizer
        # Map model family to HF repo
        hf_repos = {
            "llama": "meta-llama/Meta-Llama-3-8B",
            "qwen": "Qwen/Qwen2-7B",
            "mistral": "mistralai/Mistral-7B-v0.3",
        }
        repo = hf_repos.get(model_family, "meta-llama/Meta-Llama-3-8B")
        return AutoTokenizer.from_pretrained(repo, trust_remote_code=True)
    except ImportError:
        logger.warning(f"transformers not installed, using char fallback for {model_family}")
        return CharTokenizer()
    except Exception as e:
        logger.warning(f"HF tokenizer load failed for {model_family}: {e}")
        return CharTokenizer()


def get_token_count(messages: list[dict[str, Any]], model_id: str) -> int:
    """Count tokens for a list of chat messages.

    Args:
        messages: OpenAI-format chat messages [{role, content}, ...]
        model_id: The model to count tokens for (determines tokenizer)

    Returns:
        Exact (or closely approximated) token count including message overhead.
    """
    text = _extract_text(messages)

    tokenizer_type = _TOKENIZER_MAP.get(model_id, "tiktoken")

    # Count tokens
    if tokenizer_type == "tiktoken":
        encoder = _get_tiktoken_encoder()
        raw_tokens = len(encoder.encode(text))
    elif tokenizer_type == "anthropic":
        client = _get_anthropic_encoder()
        try:
            raw_tokens = client.count_tokens(text)
        except Exception:
            encoder = _get_tiktoken_encoder()
            raw_tokens = len(encoder.encode(text))
    elif tokenizer_type in ("llama", "qwen", "mistral"):
        tokenizer = _get_hf_tokenizer(tokenizer_type)
        raw_tokens = len(tokenizer.encode(text))
    else:
        # Char-based fallback
        raw_tokens = max(1, len(text) // 4)

    # Add message formatting overhead (~4 tokens per message for role tags)
    message_overhead = len(messages) * 4

    # Add tool definition overhead if tools are present
    # (we can't see the tools here — caller should add ~100-500 tokens for tools)

    return raw_tokens + message_overhead


def estimate_output_tokens(
    model_id: str,
    task_type: str = "chat",
    max_tokens: int | None = None,
) -> int:
    """Estimate how many output tokens a request will produce.

    Uses historical averages per model+task. Falls back to heuristics.

    Args:
        model_id: The model being called
        task_type: "chat", "code", "reasoning", "vision", "tool_use"
        max_tokens: The max_tokens parameter from the request

    Returns:
        Estimated output token count.
    """
    if max_tokens and max_tokens < 50:
        return max_tokens

    # Historical averages (per model category + task type)
    # These are seeded estimates — they get refined over time from real usage data
    HISTORICAL_AVG = {
        ("frontier", "chat"): 450,
        ("frontier", "code"): 800,
        ("frontier", "reasoning"): 2500,
        ("frontier", "vision"): 350,
        ("frontier", "tool_use"): 600,
        ("fast", "chat"): 250,
        ("fast", "code"): 500,
        ("fast", "reasoning"): 800,
        ("fast", "tool_use"): 350,
        ("cheap", "chat"): 300,
        ("cheap", "code"): 600,
        ("cheap", "reasoning"): 1200,
        ("reasoning", "chat"): 1800,
        ("reasoning", "reasoning"): 4000,
        ("reasoning", "code"): 2000,
    }

    # Find model category
    model_category = "fast"  # default
    for m in MODELS:
        if m["model_id"] == model_id:
            model_category = m.get("category", "fast")
            break

    estimated = HISTORICAL_AVG.get((model_category, task_type), 400)

    # Cap at max_tokens if specified
    if max_tokens:
        estimated = min(estimated, max_tokens)

    return estimated


def classify_task(messages: list[dict[str, Any]]) -> str:
    """Classify the task type from the messages.

    Simple heuristic based on content keywords. Gets refined over time.
    """
    text = _extract_text(messages).lower()

    if any(kw in text for kw in ["code", "function", "debug", "error", "stack trace", "implement"]):
        return "code"
    if any(kw in text for kw in ["think", "reason", "analyze", "explain why", "step by step"]):
        return "reasoning"
    if any(kw in text for kw in ["image", "picture", "screenshot", "diagram"]):
        return "vision"
    if any(kw in text for kw in ["json", "parse", "extract", "format as"]):
        return "tool_use"

    return "chat"
