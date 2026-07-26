"""Exception hierarchy for the SwiftGate SDK."""

from __future__ import annotations

from typing import Any, Optional


class SwiftGateError(Exception):
    """Base exception for all SwiftGate SDK errors."""


class APIError(SwiftGateError):
    """Raised when the API returns an error or the request fails.

    Attributes:
        message: Human-readable error message.
        request: The original httpx request (if available).
    """

    def __init__(
        self,
        message: str,
        *,
        request: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.request = request


class APIConnectionError(APIError):
    """Raised when the SDK cannot reach the SwiftGate backend."""


class APIStatusError(APIError):
    """Raised when the API responds with a non-2xx status code.

    Attributes:
        response: The httpx.Response.
        status_code: The HTTP status code.
        body: The parsed response body (if JSON), else raw text.
    """

    def __init__(
        self,
        message: str,
        *,
        response: Any,
        body: Any = None,
    ) -> None:
        super().__init__(message, request=getattr(response, "request", None))
        self.response = response
        self.status_code = getattr(response, "status_code", None)
        self.body = body


class AuthenticationError(APIStatusError):
    """401 — invalid or missing API key."""


class NotFoundError(APIStatusError):
    """404 — resource not found."""


class RateLimitError(APIStatusError):
    """429 — rate limit exceeded."""


class ServerError(APIStatusError):
    """5xx — SwiftGate server error."""


def _make_status_error(response: Any) -> APIStatusError:
    """Build the appropriate exception subclass from an httpx response."""
    status_code = response.status_code
    try:
        body = response.json()
        message = (
            body.get("detail")
            or body.get("message")
            or body.get("error")
            or str(body)
        )
    except Exception:
        body = response.text
        message = response.text or "empty response body"

    cls_map = {
        401: AuthenticationError,
        403: AuthenticationError,
        404: NotFoundError,
        429: RateLimitError,
    }
    cls = cls_map.get(status_code)
    if cls is None and 500 <= status_code < 600:
        cls = ServerError
    if cls is None:
        cls = APIStatusError

    return cls(f"SwiftGate API error {status_code}: {message}", response=response, body=body)
