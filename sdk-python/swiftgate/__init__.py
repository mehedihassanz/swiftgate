"""SwiftGate Python SDK.

Async-first client for the SwiftGate AI model gateway with cost intelligence.

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

For synchronous code::

    from swiftgate import SwiftGateSyncClient

    client = SwiftGateSyncClient(base_url="http://localhost:8000")
    result = client.predict(model="gpt-4o", messages=[{"role": "user", "content": "Hi"}])
"""

from .client import SwiftGateClient
from .sync import SwiftGateSyncClient
from ._exceptions import (
    SwiftGateError,
    APIError,
    APIStatusError,
    APIConnectionError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

__all__ = [
    "SwiftGateClient",
    "SwiftGateSyncClient",
    "SwiftGateError",
    "APIError",
    "APIStatusError",
    "APIConnectionError",
    "AuthenticationError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "__version__",
]

__version__ = "0.1.0"
