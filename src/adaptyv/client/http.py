"""Shared async HTTP client with connection pooling.

This module provides a singleton async HTTP client that maintains connection pooling
across the application, reducing SSL handshake overhead and improving latency.
"""

from __future__ import annotations

import asyncio
import atexit
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from types import TracebackType

# Default configuration
DEFAULT_TIMEOUT = 300.0  # 5 minutes for long-running operations
DEFAULT_MAX_CONNECTIONS = 20
DEFAULT_MAX_KEEPALIVE = 10

# Singleton client instance
_async_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_async_client(
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_connections: int = DEFAULT_MAX_CONNECTIONS,
    max_keepalive_connections: int = DEFAULT_MAX_KEEPALIVE,
) -> httpx.AsyncClient:
    """Get or create the shared async HTTP client.

    The client is created lazily on first use and reused for subsequent requests.
    Connection pooling reduces latency by reusing TCP connections and avoiding
    repeated SSL handshakes.

    Args:
        timeout: Request timeout in seconds (only used on first call)
        max_connections: Maximum number of connections in pool
        max_keepalive_connections: Maximum keepalive connections

    Returns:
        Shared httpx.AsyncClient instance
    """
    global _async_client

    if _async_client is None:
        async with _client_lock:
            # Double-check after acquiring lock
            if _async_client is None:
                limits = httpx.Limits(
                    max_connections=max_connections,
                    max_keepalive_connections=max_keepalive_connections,
                )
                _async_client = httpx.AsyncClient(
                    timeout=timeout,
                    limits=limits,
                    http2=True,  # Enable HTTP/2 for better multiplexing
                )

    return _async_client


async def close_async_client() -> None:
    """Close the shared async client.

    Should be called during application shutdown to release resources.
    """
    global _async_client

    if _async_client is not None:
        async with _client_lock:
            if _async_client is not None:
                await _async_client.aclose()
                _async_client = None


def _sync_close() -> None:
    """Synchronous cleanup for atexit handler."""
    global _async_client
    if _async_client is not None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create one to close
            asyncio.run(close_async_client())
        else:
            # Schedule close in running loop
            loop.create_task(close_async_client())


# Register cleanup on interpreter shutdown
atexit.register(_sync_close)


class AsyncHTTPSession:
    """Context manager for scoped async HTTP sessions.

    Use this when you need a dedicated client with specific configuration
    that shouldn't use the shared pool.

    Example:
        async with AsyncHTTPSession(timeout=60.0) as client:
            response = await client.get("https://example.com")
    """

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        self._timeout = timeout
        self._max_connections = max_connections
        self._base_url = base_url
        self._headers = headers
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        limits = httpx.Limits(max_connections=self._max_connections)
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            limits=limits,
            base_url=self._base_url or "",
            headers=self._headers or {},
            http2=True,
        )
        return self._client

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def reset_async_client() -> None:
    """Reset the shared async client (for testing).

    This clears the cached client so the next call to get_async_client()
    will create a fresh instance. Useful in test fixtures.
    """
    global _async_client
    _async_client = None


__all__ = [
    "get_async_client",
    "close_async_client",
    "reset_async_client",
    "AsyncHTTPSession",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_CONNECTIONS",
]
