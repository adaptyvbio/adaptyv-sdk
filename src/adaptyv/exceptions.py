"""Exceptions for Adaptyv Lab SDK.

Exception hierarchy:
    AdaptyvLabError (base)
    ├── AuthenticationError (401, invalid API key)
    ├── APIError (HTTP errors with status_code, response_body, request context)
    │   ├── NotFoundError (404, resource not found)
    │   └── RateLimitError (429, rate limit exceeded with retry_after)
    ├── ValidationError (invalid input parameters)
    └── PermissionDeniedError (API key lacks create_experiment permission)
"""

from __future__ import annotations


class AdaptyvLabError(Exception):
    """Base exception for all SDK errors."""

    pass


class AuthenticationError(AdaptyvLabError):
    """API key is missing or invalid."""

    pass


class APIError(AdaptyvLabError):
    """HTTP error from Foundry API.

    Attributes:
        status_code: HTTP status code
        response_body: Parsed JSON response body (if available)
        request_id: Server request ID for support debugging (from headers)
        request_path: API path that was called
        retryable: Whether this error is safe to retry
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        response_body: dict | None = None,
        *,
        request_id: str | None = None,
        request_path: str | None = None,
    ):
        self.status_code = status_code
        self.response_body = response_body
        self.request_id = request_id
        self.request_path = request_path

        # Build message with context
        parts = [f"API error {status_code}: {message}"]
        if request_id:
            parts.append(f"(request_id: {request_id})")
        if request_path:
            parts.append(f"[{request_path}]")

        super().__init__(" ".join(parts))

    @property
    def retryable(self) -> bool:
        """Whether this error is safe to retry.

        Returns True for server errors (5xx) and rate limits (429).
        """
        return self.status_code == 429 or self.status_code >= 500


class NotFoundError(APIError):
    """Resource not found (404)."""

    def __init__(
        self,
        resource: str,
        resource_id: str,
        *,
        request_id: str | None = None,
        request_path: str | None = None,
    ):
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(
            404,
            f"{resource} '{resource_id}' not found",
            request_id=request_id,
            request_path=request_path,
        )


class RateLimitError(APIError):
    """Rate limit exceeded (429).

    Attributes:
        retry_after: Seconds to wait before retrying (from Retry-After header)
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after: float | None = None,
        request_id: str | None = None,
        request_path: str | None = None,
    ):
        self.retry_after = retry_after
        retry_hint = f" (retry after {retry_after}s)" if retry_after else ""
        super().__init__(
            429,
            f"{message}{retry_hint}",
            request_id=request_id,
            request_path=request_path,
        )


class ValidationError(AdaptyvLabError):
    """Invalid request parameters."""

    pass


class PermissionDeniedError(AdaptyvLabError):
    """API key lacks required permissions.

    This typically occurs when trying to create experiments with an API key
    that doesn't have the create_experiment permission or when the account
    isn't activated for experiment creation.
    """

    pass
