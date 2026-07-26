"""Synchronous wrapper for SwiftGateClient.

Provides a simple sync interface for users who don't want asyncio.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import SwiftGateClient
from ._types import Message


class SwiftGateSyncClient:
    """Synchronous wrapper around the async SwiftGateClient.

    Usage::

        from swiftgate import SwiftGateSyncClient

        client = SwiftGateSyncClient(base_url="http://localhost:8000")
        result = client.predict(model="gpt-4o", messages=[{"role":"user","content":"Hi"}])
        client.close()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self._async = SwiftGateClient(base_url=base_url, api_key=api_key, timeout=timeout)
        import asyncio

        self._loop = asyncio.new_event_loop()
        import asyncio as _a

        self._run = self._loop.run_until_complete

    def _call(self, coro: Any) -> Any:
        return self._run(coro)

    def close(self) -> None:
        self._run(self._async.close())
        self._loop.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Mirror all async methods as sync ──

    def predict(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.predict(**kwargs))

    def compare(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.compare(**kwargs))

    def chat(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.chat(**kwargs))

    def list_models(self) -> Dict[str, Any]:
        return self._call(self._async.list_models())

    def pareto(self) -> Dict[str, Any]:
        return self._call(self._async.pareto())

    def quality_feedback(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.quality_feedback(**kwargs))

    def quality_route(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.quality_route(**kwargs))

    def quality_leaderboard(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.quality_leaderboard(**kwargs))

    def get_quality(self, model_id: str, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.get_quality(model_id, **kwargs))

    def cache_stats(self) -> Dict[str, Any]:
        return self._call(self._async.cache_stats())

    def cache_invalidate(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.cache_invalidate(**kwargs))

    def pii_detect(self, *, text: str) -> Dict[str, Any]:
        return self._call(self._async.pii_detect(text=text))

    def pii_redact(self, *, messages: List[Message]) -> Dict[str, Any]:
        return self._call(self._async.pii_redact(messages=messages))

    def pii_patterns(self) -> Dict[str, Any]:
        return self._call(self._async.pii_patterns())

    def register_agent(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.register_agent(**kwargs))

    def list_agents(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.list_agents(**kwargs))

    def kill_agent(self, agent_id: str) -> Dict[str, Any]:
        return self._call(self._async.kill_agent(agent_id))

    def usage(self, **kwargs: Any) -> Dict[str, Any]:
        return self._call(self._async.usage(**kwargs))

    def stats(self) -> Dict[str, Any]:
        return self._call(self._async.stats())
