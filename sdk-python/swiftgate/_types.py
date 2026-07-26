"""Shared type definitions for the SwiftGate SDK."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict  # type: ignore

# A single chat message in OpenAI format.
Message = Dict[str, Any]

# Body for predict/compare/chat endpoints.
Messages = List[Message]

# Headers dict.
Headers = Dict[str, str]

# Query parameters.
Query = Dict[str, Any]

# JSON body.
Body = Union[Dict[str, Any], List[Any]]


class PredictRequest(TypedDict, total=False):
    """Request body for POST /v1/predict."""

    model: str
    messages: Messages
    max_tokens: int


class ChatCompletionRequest(TypedDict, total=False):
    """Request body for POST /v1/chat/completions (OpenAI-compatible)."""

    model: str
    messages: Messages
    stream: bool
    agent_id: Optional[str]
    cost_prediction: bool
    max_tokens: Optional[int]
    temperature: Optional[float]
