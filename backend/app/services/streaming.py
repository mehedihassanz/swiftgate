"""Streaming SSE parser — extracts token usage from streamed responses.

Most OpenAI-compatible providers send the final token usage in the last
SSE chunk (the one with finish_reason set, or a separate "usage" field).

This module processes the SSE stream in real-time, passing chunks through
to the client while extracting usage data for billing.

Public API:
    StreamingUsageTracker — accumulates token counts from SSE chunks
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StreamingUsageTracker:
    """Tracks token usage from an SSE stream.

    Attach to a stream by calling .process_chunk() on each SSE data line.
    After the stream ends, .get_usage() returns the final token counts.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str | None = None
    chunks_seen: int = 0
    # For counting completion tokens manually if usage not provided
    content_chunks: int = 0
    # Collect model id from first chunk
    model: str | None = None

    def process_chunk(self, data: str) -> None:
        """Process one SSE data line (without the 'data: ' prefix).

        Looks for usage info in the chunk. Most providers include it in
        the final chunk or in a separate field.
        """
        self.chunks_seen += 1

        if not data or data.strip() == "[DONE]":
            return

        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return

        # Extract model from first chunk
        if not self.model and "model" in chunk:
            self.model = chunk["model"]

        # Check for usage in this chunk (OpenAI sends it in the final chunk
        # when stream_options.include_usage is set)
        if "usage" in chunk and chunk["usage"]:
            usage = chunk["usage"]
            self.prompt_tokens = usage.get("prompt_tokens", self.prompt_tokens)
            self.completion_tokens = usage.get("completion_tokens", self.completion_tokens)
            self.total_tokens = usage.get("total_tokens", self.total_tokens)

        # Track choices for finish_reason and manual token counting
        choices = chunk.get("choices", [])
        if choices:
            choice = choices[0]
            if choice.get("finish_reason"):
                self.finish_reason = choice["finish_reason"]

            # Count content chunks as a fallback for estimating tokens
            delta = choice.get("delta", {})
            if delta.get("content"):
                self.content_chunks += 1

    def get_usage(self) -> dict:
        """Get final usage estimate. If provider didn't send usage data,
        estimate completion tokens from content chunks (~1 token per 4 chars
        across all chunks)."""
        if self.completion_tokens == 0 and self.content_chunks > 0:
            # Rough estimate: average ~3 tokens per content chunk
            # (deltas typically contain 1-5 tokens each)
            self.completion_tokens = self.content_chunks * 3

        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens

        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "finish_reason": self.finish_reason,
            "chunks_seen": self.chunks_seen,
            "estimated": self.completion_tokens == 0 or (
                self.content_chunks > 0 and self.prompt_tokens == 0
            ),
        }


def add_stream_usage_option(body: dict) -> dict:
    """Add stream_options.include_usage to the request body.

    This tells OpenAI-compatible providers to include token usage in the
    final SSE chunk. Works with OpenAI, DeepInfra, Together, Groq, etc.

    Anthropic handles this differently (usage is in every message_start event).
    """
    if body.get("stream"):
        body.setdefault("stream_options", {})
        body["stream_options"].setdefault("include_usage", True)
    return body
