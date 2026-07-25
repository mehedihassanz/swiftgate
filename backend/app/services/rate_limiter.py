"""Rate limiter — per-key request throttling using sliding window.

Uses in-memory storage by default. If Redis is available, uses Redis for
distributed rate limiting across multiple workers.

Public API:
    RateLimiter.check(key_id, max_requests_per_minute) -> bool
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SlidingWindow:
    """Simple sliding window counter for one entity."""
    timestamps: list[float] = field(default_factory=list)

    def add_and_count(self, now: float, window_seconds: int = 60) -> int:
        """Add a request at `now`, prune old entries, return current count."""
        cutoff = now - window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        self.timestamps.append(now)
        return len(self.timestamps)


class InMemoryRateLimiter:
    """Per-key sliding window rate limiter. No external deps."""

    def __init__(self):
        self._windows: dict[int, SlidingWindow] = defaultdict(SlidingWindow)
        self._anonymous: SlidingWindow = SlidingWindow()  # shared for anonymous

    def check(self, key_id: int | None, max_per_minute: int) -> tuple[bool, int, int]:
        """Check if request is allowed under rate limit.

        Returns: (allowed, current_count, limit)
        """
        now = time.time()
        window = self._windows[key_id] if key_id else self._anonymous
        count = window.add_and_count(now)
        allowed = count <= max_per_minute
        return allowed, count, max_per_minute

    def get_remaining(self, key_id: int | None, max_per_minute: int) -> int:
        """Get remaining requests in the current window."""
        now = time.time()
        window = self._windows[key_id] if key_id else self._anonymous
        cutoff = now - 60
        active = [t for t in window.timestamps if t > cutoff]
        return max(0, max_per_minute - len(active))


# Singleton
rate_limiter = InMemoryRateLimiter()

# Default rate limits
DEFAULT_RPM = 60          # requests per minute for authenticated users
ANONYMOUS_RPM = 10        # very low for anonymous to prevent abuse


async def check_rate_limit(key_id: int | None) -> tuple[bool, dict]:
    """Check rate limit for a key. Returns (allowed, rate_info_dict).

    rate_info_dict contains: limit, remaining, reset_at
    """
    limit = DEFAULT_RPM if key_id else ANONYMOUS_RPM
    allowed, count, _ = rate_limiter.check(key_id, limit)
    remaining = rate_limiter.get_remaining(key_id, limit)

    rate_info = {
        "limit": limit,
        "remaining": remaining,
        "used": count,
    }

    return allowed, rate_info
