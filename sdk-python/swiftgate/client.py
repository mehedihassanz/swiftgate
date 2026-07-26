"""Async HTTP client for the SwiftGate API."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from ._exceptions import APIConnectionError, _make_status_error
from ._types import Message

DEFAULT_BASE_URL = "https://backend-production-41a7.up.railway.app"
DEFAULT_TIMEOUT = 120.0


class SwiftGateClient:
    """Async client for the SwiftGate AI model gateway.

    Usage::

        import asyncio
        from swiftgate import SwiftGateClient

        async def main():
            client = SwiftGateClient(base_url="http://localhost:8000")
            result = await client.predict(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
            )
            print(result)
            await client.close()

        asyncio.run(main())
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._default_headers(),
        )

    def _default_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Any = None,
    ) -> Any:
        try:
            resp = await self._client.request(
                method, path, json=json_body, params=params
            )
        except httpx.ConnectError as e:
            raise APIConnectionError(f"Cannot connect to {self.base_url}: {e}")
        except httpx.TimeoutException as e:
            raise APIConnectionError(f"Request timed out: {e}")

        if resp.status_code >= 400:
            raise _make_status_error(resp)

        if resp.status_code == 204:
            return None

        # Check if this is SSE (streaming)
        ct = resp.headers.get("content-type", "")
        if "text/event-stream" in ct:
            return resp  # caller handles streaming
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # ─── Core: Cost Prediction ──────────────────────────────────────────

    async def predict(
        self,
        *,
        model: str,
        messages: List[Message],
        max_tokens: Optional[int] = None,
        tools: Any = None,
    ) -> Dict[str, Any]:
        """Predict the cost of a request before sending it."""
        body: Dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if tools is not None:
            body["tools"] = tools
        return await self._request("POST", "/v1/predict", json_body=body)

    async def compare(
        self,
        *,
        messages: List[Message],
        max_tokens: Optional[int] = None,
        max_budget_cents: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Compare models for a prompt."""
        body: Dict[str, Any] = {"messages": messages}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if max_budget_cents is not None:
            body["max_budget_cents"] = max_budget_cents
        return await self._request("POST", "/v1/compare", json_body=body)

    # ─── Core: Chat (OpenAI-compatible) ─────────────────────────────────

    async def chat(
        self,
        *,
        model: str,
        messages: List[Message],
        stream: bool = False,
        agent_id: Optional[str] = None,
        cost_prediction: bool = True,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Any = None,
        extra_body: Any = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request through the gateway."""
        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "cost_prediction": cost_prediction,
        }
        if agent_id:
            body["agent_id"] = agent_id
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if tools is not None:
            body["tools"] = tools
        if extra_body:
            body.update(extra_body)
        return await self._request("POST", "/v1/chat/completions", json_body=body)

    async def chat_stream(self, **kwargs: Any) -> AsyncIterator[str]:
        """Stream a chat completion. Yields SSE chunks."""
        kwargs["stream"] = True
        resp = await self._request("POST", "/v1/chat/completions", json_body=kwargs)
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                yield line[6:]

    # ─── Models ─────────────────────────────────────────────────────────

    async def list_models(self) -> Dict[str, Any]:
        """List all available models."""
        return await self._request("GET", "/v1/models")

    async def pareto(self) -> Dict[str, Any]:
        """Get Pareto-optimal models."""
        return await self._request("GET", "/v1/pareto")

    # ─── Quality ────────────────────────────────────────────────────────

    async def quality_feedback(
        self,
        *,
        model_id: str,
        rating: int,
        task_type: str = "chat",
        signal_type: str = "explicit_rating",
        usage_record_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Submit quality feedback (1-10 rating)."""
        return await self._request(
            "POST",
            "/v1/quality/feedback",
            json_body={
                "model_id": model_id,
                "rating": rating,
                "task_type": task_type,
                "signal_type": signal_type,
                "usage_record_id": usage_record_id,
            },
        )

    async def quality_route(
        self,
        *,
        messages: List[Message],
        max_budget_cents: Optional[int] = None,
        min_quality: float = 0.0,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """Get quality-per-dollar routing recommendation."""
        return await self._request(
            "POST",
            "/v1/quality/route",
            json_body={
                "messages": messages,
                "max_budget_cents": max_budget_cents,
                "min_quality": min_quality,
                "top_n": top_n,
            },
        )

    async def quality_leaderboard(
        self, *, task_type: str = "chat", min_samples: int = 0
    ) -> Dict[str, Any]:
        """Get the quality leaderboard."""
        return await self._request(
            "GET",
            "/v1/quality/leaderboard",
            params={"task_type": task_type, "min_samples": min_samples},
        )

    async def get_quality(self, model_id: str, task_type: str = "chat") -> Dict[str, Any]:
        """Get quality index for a model."""
        return await self._request(
            "GET", f"/v1/quality/{model_id}", params={"task_type": task_type}
        )

    # ─── Cache ──────────────────────────────────────────────────────────

    async def cache_stats(self) -> Dict[str, Any]:
        """Get semantic cache statistics."""
        return await self._request("GET", "/v1/cache/stats")

    async def cache_invalidate(
        self, *, model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Invalidate cache entries."""
        return await self._request(
            "DELETE", "/v1/cache", params={"model_id": model_id} if model_id else None
        )

    # ─── PII ────────────────────────────────────────────────────────────

    async def pii_detect(self, *, text: str) -> Dict[str, Any]:
        """Detect PII in text."""
        return await self._request("POST", "/v1/pii/detect", json_body={"text": text})

    async def pii_redact(self, *, messages: List[Message]) -> Dict[str, Any]:
        """Redact PII from messages."""
        return await self._request(
            "POST", "/v1/pii/redact", json_body={"messages": messages}
        )

    async def pii_patterns(self) -> Dict[str, Any]:
        """List active PII detection patterns."""
        return await self._request("GET", "/v1/pii/patterns")

    # ─── Agents ─────────────────────────────────────────────────────────

    async def register_agent(
        self,
        *,
        agent_id: str,
        name: str = "unnamed-agent",
        budget_cents: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Register a new agent."""
        return await self._request(
            "POST",
            "/v1/agents",
            json_body={
                "agent_id": agent_id,
                "name": name,
                "budget_cents": budget_cents,
            },
        )

    async def list_agents(self, *, status: Optional[str] = None) -> Dict[str, Any]:
        """List all agents."""
        return await self._request(
            "GET", "/v1/agents", params={"status": status} if status else None
        )

    async def kill_agent(self, agent_id: str) -> Dict[str, Any]:
        """Kill an agent."""
        return await self._request("POST", f"/v1/agents/{agent_id}/kill")

    async def pause_agent(self, agent_id: str) -> Dict[str, Any]:
        """Pause an agent."""
        return await self._request("POST", f"/v1/agents/{agent_id}/pause")

    async def resume_agent(self, agent_id: str) -> Dict[str, Any]:
        """Resume an agent."""
        return await self._request("POST", f"/v1/agents/{agent_id}/resume")

    async def reset_agent_budget(self, agent_id: str) -> Dict[str, Any]:
        """Reset an agent's spend counter."""
        return await self._request("POST", f"/v1/agents/{agent_id}/reset")

    # ─── Usage & Stats ──────────────────────────────────────────────────

    async def usage(
        self,
        *,
        limit: int = 50,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get usage records."""
        params: Dict[str, Any] = {"limit": limit}
        if agent_id:
            params["agent_id"] = agent_id
        return await self._request("GET", "/v1/usage", params=params)

    async def stats(self) -> Dict[str, Any]:
        """Get aggregate statistics."""
        return await self._request("GET", "/v1/stats")
